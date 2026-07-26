"""Administration des fournisseurs LLM."""

import os
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from requests.exceptions import RequestException
from sqlmodel import func, select
from core.auth import get_current_user
from core.database import SessionDep
from models import LLMProvider, Prompt, Role, User
from core.dependencies import logger, templates
from services.llm_client import (
    ERROR_AUTH,
    ERROR_QUOTA,
    LLMConfigError,
    list_models,
    ping_generation,
)

backend_router = APIRouter(tags=["Backend"], prefix="/backend")


@backend_router.get("/providers", response_class=HTMLResponse)
def backend_providers(request: Request, session: SessionDep):
    """Liste tous les fournisseurs LLM avec statut des clÃ©s.

    Affiche une table avec:
    - Les infos de chaque fournisseur (nom, type API, URL, etc)
    - Indicateur: clÃ© d'env prÃ©sente dans le systÃ¨me ou pas
    - Nombre de prompts qui utilisent ce fournisseur
    - Boutons Ã‰diter/Supprimer (supprimer bloquÃ© si prompts utilisent ce fournisseur)
    """
    # 1. VÃ©rifier que l'utilisateur est connectÃ©
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/")

    # 2. RÃ©cupÃ©rer les rÃ´les de l'utilisateur depuis la base
    roles_query = session.exec(
        select(func.group_concat(Role.role))
        .join(User, Role.user_id == User.user_id, isouter=True)
        .where(User.mail == user["email"].casefold())
    ).first()
    roles = roles_query.split(",") if roles_query else ["student"]

    # 3. VÃ©rifier que c'est un admin - sinon le rediriger
    if "admin" not in roles:
        return RedirectResponse(url="/")

    # 4. Charger tous les fournisseurs depuis la base, triÃ©s par ID
    providers = session.exec(select(LLMProvider).order_by(LLMProvider.provider_id)).all()

    # 5. Pour chaque fournisseur, enrichir les donnÃ©es avec info utiles
    provider_data = []
    for provider in providers:
        # VÃ©rifier si la clÃ© d'env (ex: OPENAI_API_KEY) existe dans l'environnement
        # Important: on ne rÃ©cupÃ¨re jamais la VALEUR, juste son existence
        key_present = os.getenv(provider.api_key_env) is not None

        # Compter combien de prompts utilisent ce fournisseur
        # Utile pour empÃªcher la suppression si le fournisseur est rÃ©fÃ©rencÃ©
        prompt_count = session.exec(
            select(func.count(Prompt.prompt_id)).where(
                Prompt.provider_id == provider.provider_id
            )
        ).first() or 0

        # CrÃ©er un dict avec les infos enrichies pour le template
        provider_data.append({
            "provider": provider,  # L'objet fournisseur complet
            "key_present": key_present,  # BoolÃ©en: clÃ© prÃ©sente ou pas
            "prompt_count": prompt_count,  # Nombre: combien de prompts l'utilisent
        })

    # 6. Renvoyer le template HTML avec les donnÃ©es
    return templates.TemplateResponse(request, "backend/llm/providers.html", {
        "request": request,
        "providers": provider_data,
    })


@backend_router.get("/providers/new", response_class=HTMLResponse)
def backend_provider_new(request: Request, session: SessionDep):
    """Formulaire de crÃ©ation d'un nouveau fournisseur."""
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/")

    roles_query = session.exec(
        select(func.group_concat(Role.role))
        .join(User, Role.user_id == User.user_id, isouter=True)
        .where(User.mail == user["email"].casefold())
    ).first()
    roles = roles_query.split(",") if roles_query else ["student"]

    if "admin" not in roles:
        return RedirectResponse(url="/")

    return templates.TemplateResponse(request, "backend/llm/provider_form.html", {
        "request": request,
        "provider": None,
    })


# Whitelist pour api_key_env
ALLOWED_API_KEY_PATTERNS = ("LLM_", "_API_KEY")


def _validate_api_key_env(value: str) -> tuple[bool, str]:
    """Valide le nom de la variable d'environnement contre une whitelist.

    SÃ©curitÃ© critique: empÃªcher un admin malveillant de pointer un fournisseur
    vers une clÃ© sensible (SECRET_KEY, ENTRA_CLIENT_SECRET, etc) et la divulguer
    Ã  un serveur externe.

    La clÃ© elle-mÃªme n'est jamais affichÃ©e, mais si on la laisse l'admin pointer
    Ã  n'importe quelle variable, il pourrait voler les secrets du systÃ¨me.

    Retourne: (est_valide: bool, message_erreur: str)
    """
    # VÃ©rifier que la variable n'est pas vide
    if not value:
        return False, "La variable d'environnement est requise"

    # VÃ©rifier format: seulement majuscules, chiffres, underscores
    # "value.replace("_", "").isalnum()" = aprÃ¨s enlever underscores, c'est alphanumÃ©rique?
    # "not value.isupper()" = contient au moins une minuscule?
    if not value.replace("_", "").isalnum() or not value.isupper():
        return False, "Doit contenir uniquement des majuscules, chiffres et underscores"

    # VÃ©rifier que Ã§a commence par LLM_ OU finit par _API_KEY
    # Exemples acceptÃ©s: LLM_API_KEY, OPENAI_API_KEY, LLM_ANTHROPIC_KEY
    if not any(value.startswith(p) or value.endswith(p) for p in ALLOWED_API_KEY_PATTERNS):
        return False, f"Doit commencer par LLM_ ou finir par _API_KEY"

    # Blacklist: interdire les variables sensibles du systÃ¨me
    forbidden = ("SECRET_KEY", "ENTRA_CLIENT_ID", "ENTRA_CLIENT_SECRET", "ENTRA_TENANT_ID")
    if value in forbidden:
        return False, f"La variable {value} est rÃ©servÃ©e au systÃ¨me"

    # Tout est bon!
    return True, ""


@backend_router.post("/providers/create")
def create_provider(
    request: Request,
    session: SessionDep,
    name: str = Form(...),  # LibellÃ© du fournisseur (ex: "OpenAI")
    api_type: str = Form(...),  # Type: "ollama", "openai", ou "anthropic"
    base_url: str = Form(...),  # URL racine (ex: https://api.openai.com)
    api_key_env: str = Form(...),  # Nom var env (ex: OPENAI_API_KEY)
    default_model: str = Form(""),  # ModÃ¨le par dÃ©faut (optionnel)
    is_active: bool = Form(False),  # Fournisseur actif ou pas?
):
    """CrÃ©e un nouveau fournisseur LLM aprÃ¨s validation.

    Ã‰tapes:
    1. VÃ©rifier que l'utilisateur est auth et admin
    2. Valider api_key_env contre la whitelist de sÃ©curitÃ©
    3. VÃ©rifier que le nom est unique
    4. CrÃ©er l'objet et l'enregistrer en base
    5. Rediriger vers la liste avec message de succÃ¨s
    """
    # 1. AUTHENTIFICATION
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/")

    # RÃ©cupÃ©rer les rÃ´les
    roles_query = session.exec(
        select(func.group_concat(Role.role))
        .join(User, Role.user_id == User.user_id, isouter=True)
        .where(User.mail == user["email"].casefold())
    ).first()
    roles = roles_query.split(",") if roles_query else ["student"]

    # VÃ©rifier admin - sinon refuser avec 403 (Forbidden)
    if "admin" not in roles:
        return RedirectResponse(url="/", status_code=403)

    # 2. VALIDATION - api_key_env
    # Appeler la fonction de validation avec whitelist
    valid, error_msg = _validate_api_key_env(api_key_env)
    if not valid:
        # Si validation Ã©choue, renvoyer le formulaire avec le message d'erreur
        return templates.TemplateResponse(request, "backend/llm/provider_form.html", {
            "request": request,
            "provider": None,
            "error": error_msg,
        }, status_code=400)  # 400 = Bad Request

    # 3. VALIDATION - UnicitÃ© du nom
    # VÃ©rifier qu'aucun autre fournisseur n'a ce nom
    existing = session.exec(
        select(LLMProvider).where(LLMProvider.name == name)
    ).first()
    if existing:
        # Si le nom existe dÃ©jÃ , refuser la crÃ©ation
        return templates.TemplateResponse(request, "backend/llm/provider_form.html", {
            "request": request,
            "provider": None,
            "error": f"Un fournisseur nommÃ© '{name}' existe dÃ©jÃ ",
        }, status_code=400)

    # 4. CRÃ‰ATION
    # CrÃ©er l'objet LLMProvider avec les donnÃ©es du formulaire
    provider = LLMProvider(
        name=name,
        api_type=api_type,
        base_url=base_url.rstrip("/"),  # Normalisation: enlever le / Ã  la fin
        api_key_env=api_key_env,
        # Si default_model est vide, le mettre Ã  None (pas une chaÃ®ne vide)
        default_model=default_model if default_model else None,
        is_active=is_active,
    )
    # Ajouter Ã  la session et valider
    session.add(provider)
    session.commit()  # Persister en base

    # 5. REDIRECTION
    # Redirection 303 (See Other) vers la liste avec paramÃ¨tre de succÃ¨s
    # Le paramÃ¨tre ?success=created permet au template d'afficher un message
    return RedirectResponse(url="/backend/providers?success=created", status_code=303)


@backend_router.get("/providers/{provider_id}/edit", response_class=HTMLResponse)
def backend_provider_edit(request: Request, provider_id: int, session: SessionDep):
    """Formulaire d'Ã©dition d'un fournisseur existant.

    RÃ©utilise le mÃªme template que la crÃ©ation, mais en lui passant le
    fournisseur Ã  modifier (le template bascule alors en mode Ã©dition).
    """
    # 1. AUTHENTIFICATION + contrÃ´le admin
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/")

    roles_query = session.exec(
        select(func.group_concat(Role.role))
        .join(User, Role.user_id == User.user_id, isouter=True)
        .where(User.mail == user["email"].casefold())
    ).first()
    roles = roles_query.split(",") if roles_query else ["student"]

    if "admin" not in roles:
        return RedirectResponse(url="/")

    # 2. Charger le fournisseur ; introuvable â†’ retour Ã  la liste avec erreur
    provider = session.get(LLMProvider, provider_id)
    if not provider:
        return RedirectResponse(
            url="/backend/providers?error=introuvable", status_code=303
        )

    # 3. Afficher le formulaire prÃ©-rempli avec le fournisseur
    return templates.TemplateResponse(request, "backend/llm/provider_form.html", {
        "request": request,
        "provider": provider,
    })


@backend_router.post("/providers/{provider_id}/update")
def update_provider(
    request: Request,
    provider_id: int,
    session: SessionDep,
    name: str = Form(...),  # LibellÃ© du fournisseur (ex: "OpenAI")
    api_type: str = Form(...),  # Type: "ollama", "openai", ou "anthropic"
    base_url: str = Form(...),  # URL racine (ex: https://api.openai.com)
    api_key_env: str = Form(...),  # Nom var env (ex: OPENAI_API_KEY)
    default_model: str = Form(""),  # ModÃ¨le par dÃ©faut (optionnel)
    is_active: bool = Form(False),  # Fournisseur actif ou pas?
):
    """Met Ã  jour un fournisseur LLM existant aprÃ¨s validation.

    Ã‰tapes:
    1. VÃ©rifier que l'utilisateur est auth et admin
    2. Charger le fournisseur Ã  modifier
    3. Valider api_key_env contre la whitelist de sÃ©curitÃ©
    4. VÃ©rifier que le nom reste unique (hors ce fournisseur)
    5. Appliquer les modifications et sauvegarder
    6. Rediriger vers la liste avec message de succÃ¨s
    """
    # 1. AUTHENTIFICATION
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/")

    roles_query = session.exec(
        select(func.group_concat(Role.role))
        .join(User, Role.user_id == User.user_id, isouter=True)
        .where(User.mail == user["email"].casefold())
    ).first()
    roles = roles_query.split(",") if roles_query else ["student"]

    # VÃ©rifier admin - sinon refuser avec 403 (Forbidden)
    if "admin" not in roles:
        return RedirectResponse(url="/", status_code=403)

    # 2. Charger le fournisseur Ã  modifier
    provider = session.get(LLMProvider, provider_id)
    if not provider:
        return RedirectResponse(
            url="/backend/providers?error=introuvable", status_code=303
        )

    # 3. VALIDATION - api_key_env (mÃªme rÃ¨gle que la crÃ©ation)
    valid, error_msg = _validate_api_key_env(api_key_env)
    if not valid:
        return templates.TemplateResponse(request, "backend/llm/provider_form.html", {
            "request": request,
            "provider": provider,
            "error": error_msg,
        }, status_code=400)  # 400 = Bad Request

    # 4. VALIDATION - UnicitÃ© du nom, en excluant CE fournisseur
    #    (sinon on se bloquerait soi-mÃªme en gardant le mÃªme nom)
    existing = session.exec(
        select(LLMProvider).where(
            LLMProvider.name == name,
            LLMProvider.provider_id != provider_id,
        )
    ).first()
    if existing:
        return templates.TemplateResponse(request, "backend/llm/provider_form.html", {
            "request": request,
            "provider": provider,
            "error": f"Un autre fournisseur nommÃ© '{name}' existe dÃ©jÃ ",
        }, status_code=400)

    # 5. MISE Ã€ JOUR des champs
    provider.name = name
    provider.api_type = api_type
    provider.base_url = base_url.rstrip("/")  # Normalisation: enlever le / final
    provider.api_key_env = api_key_env
    provider.default_model = default_model if default_model else None
    provider.is_active = is_active
    session.add(provider)
    session.commit()  # Persister les modifications

    # 6. REDIRECTION vers la liste avec message de succÃ¨s
    return RedirectResponse(url="/backend/providers?success=updated", status_code=303)


@backend_router.post("/providers/{provider_id}/delete")
def delete_provider(request: Request, provider_id: int, session: SessionDep):
    """Supprime un fournisseur, sauf s'il est rÃ©fÃ©rencÃ© par un prompt (409).

    MÃªme principe de verrou que pour les prompts utilisÃ©s par des synthÃ¨ses :
    on refuse la suppression tant qu'au moins un prompt pointe sur ce
    fournisseur, pour ne pas casser la configuration de ces prompts.
    """
    # 1. AUTHENTIFICATION + contrÃ´le admin
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/")

    roles_query = session.exec(
        select(func.group_concat(Role.role))
        .join(User, Role.user_id == User.user_id, isouter=True)
        .where(User.mail == user["email"].casefold())
    ).first()
    roles = roles_query.split(",") if roles_query else ["student"]

    if "admin" not in roles:
        return RedirectResponse(url="/", status_code=403)

    # 2. Charger le fournisseur ; introuvable â†’ retour liste avec erreur
    provider = session.get(LLMProvider, provider_id)
    if not provider:
        return RedirectResponse(
            url="/backend/providers?error=introuvable", status_code=303
        )

    # 3. VERROU : refuser si au moins un prompt utilise ce fournisseur
    in_use = session.exec(
        select(Prompt).where(Prompt.provider_id == provider_id).limit(1)
    ).first()
    if in_use:
        return RedirectResponse(
            url="/backend/providers?error=utilise_par_prompt", status_code=303
        )

    # 4. SUPPRESSION
    session.delete(provider)
    session.commit()

    # 5. REDIRECTION vers la liste avec message de succÃ¨s
    return RedirectResponse(url="/backend/providers?success=deleted", status_code=303)


@backend_router.get("/providers/{provider_id}/test")
def test_provider(request: Request, provider_id: int, session: SessionDep):
    """Teste un fournisseur : liste ses modÃ¨les, puis vÃ©rifie qu'il peut gÃ©nÃ©rer.

    AppelÃ© en fetch depuis la liste. Deux Ã©tapes, car lister les modÃ¨les ne
    prouve rien sur la facturation : chez OpenAI comme chez Anthropic, GET
    /v1/models rÃ©pond encore parfaitement avec un solde Ã  zÃ©ro. On enchaÃ®ne donc
    sur un ping de gÃ©nÃ©ration d'un token, seul moyen de voir un crÃ©dit Ã©puisÃ©
    avant que le daemon ne le dÃ©couvre en pleine campagne de synthÃ¨ses.

    Renvoie {"ok": true, "count": N} si tout rÃ©pond, {"ok": false, "error": ...}
    sinon. Les causes de configuration (clÃ©, URL, exception) restent gÃ©nÃ©riques
    cÃ´tÃ© navigateur et dÃ©taillÃ©es dans les logs ; le crÃ©dit Ã©puisÃ©, lui, est
    annoncÃ© explicitement â€” c'est justement l'information dont l'administrateur
    a besoin, et elle ne rÃ©vÃ¨le aucun secret.
    """
    # 1. AUTHENTIFICATION + contrÃ´le admin
    user = get_current_user(request)
    if not user:
        return JSONResponse({"ok": False, "error": "Non authentifiÃ©."}, status_code=401)

    roles_query = session.exec(
        select(func.group_concat(Role.role))
        .join(User, Role.user_id == User.user_id, isouter=True)
        .where(User.mail == user["email"].casefold())
    ).first()
    roles = roles_query.split(",") if roles_query else ["student"]

    if "admin" not in roles:
        return JSONResponse({"ok": False, "error": "AccÃ¨s refusÃ©."}, status_code=403)

    # 2. Charger le fournisseur
    provider = session.get(LLMProvider, provider_id)
    if not provider:
        return JSONResponse({"ok": False, "error": "Fournisseur introuvable."}, status_code=404)

    # 3. Tenter de lister les modÃ¨les (test de connexion en lecture)
    try:
        models = list_models(provider)
    except LLMConfigError as error:
        # Mauvaise config (clÃ© absente/non autorisÃ©e, type d'API inconnu)
        logger.warning("Test fournisseur %s : config invalide : %s", provider.name, error)
        return JSONResponse(
            {"ok": False, "error": "Configuration invalide (voir les logs serveur)."}
        )
    except RequestException as error:
        # Serveur injoignable, timeout, rÃ©ponse HTTP en erreur
        logger.warning("Test fournisseur %s : serveur injoignable : %s", provider.name, error)
        return JSONResponse(
            {"ok": False, "error": "Serveur injoignable (voir les logs serveur)."}
        )
    except Exception:
        # Filet de sÃ©curitÃ© : rien ne doit fuiter vers le navigateur
        logger.exception("Test fournisseur %s : erreur inattendue", provider.name)
        return JSONResponse(
            {"ok": False, "error": "Erreur inattendue (voir les logs serveur)."}
        )

    # 4. Le fournisseur rÃ©pond. Reste Ã  savoir s'il accepte de gÃ©nÃ©rer : on
    #    ping le modÃ¨le par dÃ©faut, ou Ã  dÃ©faut le premier modÃ¨le exposÃ©.
    model = provider.default_model or (models[0] if models else None)
    if not model:
        return JSONResponse({
            "ok": True,
            "count": 0,
            "warning": "ConnectÃ©, mais aucun modÃ¨le Ã  tester : crÃ©dit non vÃ©rifiÃ©.",
        })

    try:
        ok, kind, message = ping_generation(provider, model)
    except LLMConfigError as error:
        logger.warning("Ping fournisseur %s : config invalide : %s", provider.name, error)
        return JSONResponse(
            {"ok": False, "error": "Configuration invalide (voir les logs serveur)."}
        )
    except RequestException as error:
        logger.warning("Ping fournisseur %s : serveur injoignable : %s", provider.name, error)
        return JSONResponse(
            {"ok": False, "error": "Serveur injoignable (voir les logs serveur)."}
        )
    except Exception:
        logger.exception("Ping fournisseur %s : erreur inattendue", provider.name)
        return JSONResponse(
            {"ok": False, "error": "Erreur inattendue (voir les logs serveur)."}
        )

    if not ok:
        logger.warning("Ping fournisseur %s (%s) : %s", provider.name, kind, message)
        # Une clÃ© refusÃ©e est un problÃ¨me de configuration : le message du
        # fournisseur peut citer la clÃ© envoyÃ©e, il reste donc dans les logs.
        # Les autres cas (crÃ©dit, dÃ©bit, modÃ¨le, panne) ne rÃ©vÃ¨lent rien et
        # gagnent Ã  Ãªtre affichÃ©s tels quels. `kind` permet au navigateur de
        # distinguer le crÃ©dit Ã©puisÃ©, bloquant, d'un dÃ©bit passager.
        client_error = (
            "ClÃ© d'API refusÃ©e par le fournisseur (voir les logs serveur)."
            if kind == ERROR_AUTH
            else message
        )
        return JSONResponse({"ok": False, "kind": kind, "error": client_error})

    # 5. SuccÃ¨s complet : la connexion rÃ©pond et le compte peut gÃ©nÃ©rer.
    return JSONResponse({"ok": True, "count": len(models), "model": model})
