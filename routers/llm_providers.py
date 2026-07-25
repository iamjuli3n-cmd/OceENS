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
from services.llm_client import LLMConfigError, list_models

backend_router = APIRouter(tags=["Backend"], prefix="/backend")


@backend_router.get("/providers", response_class=HTMLResponse)
def backend_providers(request: Request, session: SessionDep):
    """Liste tous les fournisseurs LLM avec statut des clés.

    Affiche une table avec:
    - Les infos de chaque fournisseur (nom, type API, URL, etc)
    - Indicateur: clé d'env présente dans le système ou pas
    - Nombre de prompts qui utilisent ce fournisseur
    - Boutons Éditer/Supprimer (supprimer bloqué si prompts utilisent ce fournisseur)
    """
    # 1. Vérifier que l'utilisateur est connecté
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/")

    # 2. Récupérer les rôles de l'utilisateur depuis la base
    roles_query = session.exec(
        select(func.group_concat(Role.role))
        .join(User, Role.user_id == User.user_id, isouter=True)
        .where(User.mail == user["email"].casefold())
    ).first()
    roles = roles_query.split(",") if roles_query else ["student"]

    # 3. Vérifier que c'est un admin - sinon le rediriger
    if "admin" not in roles:
        return RedirectResponse(url="/")

    # 4. Charger tous les fournisseurs depuis la base, triés par ID
    providers = session.exec(select(LLMProvider).order_by(LLMProvider.provider_id)).all()

    # 5. Pour chaque fournisseur, enrichir les données avec info utiles
    provider_data = []
    for provider in providers:
        # Vérifier si la clé d'env (ex: OPENAI_API_KEY) existe dans l'environnement
        # Important: on ne récupère jamais la VALEUR, juste son existence
        key_present = os.getenv(provider.api_key_env) is not None

        # Compter combien de prompts utilisent ce fournisseur
        # Utile pour empêcher la suppression si le fournisseur est référencé
        prompt_count = session.exec(
            select(func.count(Prompt.prompt_id)).where(
                Prompt.provider_id == provider.provider_id
            )
        ).first() or 0

        # Créer un dict avec les infos enrichies pour le template
        provider_data.append({
            "provider": provider,  # L'objet fournisseur complet
            "key_present": key_present,  # Booléen: clé présente ou pas
            "prompt_count": prompt_count,  # Nombre: combien de prompts l'utilisent
        })

    # 6. Renvoyer le template HTML avec les données
    return templates.TemplateResponse(request, "backend/providers.html", {
        "request": request,
        "providers": provider_data,
    })


@backend_router.get("/providers/new", response_class=HTMLResponse)
def backend_provider_new(request: Request, session: SessionDep):
    """Formulaire de création d'un nouveau fournisseur."""
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

    return templates.TemplateResponse(request, "backend/provider_form.html", {
        "request": request,
        "provider": None,
    })


# Whitelist pour api_key_env
ALLOWED_API_KEY_PATTERNS = ("LLM_", "_API_KEY")


def _validate_api_key_env(value: str) -> tuple[bool, str]:
    """Valide le nom de la variable d'environnement contre une whitelist.

    Sécurité critique: empêcher un admin malveillant de pointer un fournisseur
    vers une clé sensible (SECRET_KEY, ENTRA_CLIENT_SECRET, etc) et la divulguer
    à un serveur externe.

    La clé elle-même n'est jamais affichée, mais si on la laisse l'admin pointer
    à n'importe quelle variable, il pourrait voler les secrets du système.

    Retourne: (est_valide: bool, message_erreur: str)
    """
    # Vérifier que la variable n'est pas vide
    if not value:
        return False, "La variable d'environnement est requise"

    # Vérifier format: seulement majuscules, chiffres, underscores
    # "value.replace("_", "").isalnum()" = après enlever underscores, c'est alphanumérique?
    # "not value.isupper()" = contient au moins une minuscule?
    if not value.replace("_", "").isalnum() or not value.isupper():
        return False, "Doit contenir uniquement des majuscules, chiffres et underscores"

    # Vérifier que ça commence par LLM_ OU finit par _API_KEY
    # Exemples acceptés: LLM_API_KEY, OPENAI_API_KEY, LLM_ANTHROPIC_KEY
    if not any(value.startswith(p) or value.endswith(p) for p in ALLOWED_API_KEY_PATTERNS):
        return False, f"Doit commencer par LLM_ ou finir par _API_KEY"

    # Blacklist: interdire les variables sensibles du système
    forbidden = ("SECRET_KEY", "ENTRA_CLIENT_ID", "ENTRA_CLIENT_SECRET", "ENTRA_TENANT_ID")
    if value in forbidden:
        return False, f"La variable {value} est réservée au système"

    # Tout est bon!
    return True, ""


@backend_router.post("/providers/create")
def create_provider(
    request: Request,
    session: SessionDep,
    name: str = Form(...),  # Libellé du fournisseur (ex: "OpenAI")
    api_type: str = Form(...),  # Type: "ollama", "openai", ou "anthropic"
    base_url: str = Form(...),  # URL racine (ex: https://api.openai.com)
    api_key_env: str = Form(...),  # Nom var env (ex: OPENAI_API_KEY)
    default_model: str = Form(""),  # Modèle par défaut (optionnel)
    is_active: bool = Form(False),  # Fournisseur actif ou pas?
):
    """Crée un nouveau fournisseur LLM après validation.

    Étapes:
    1. Vérifier que l'utilisateur est auth et admin
    2. Valider api_key_env contre la whitelist de sécurité
    3. Vérifier que le nom est unique
    4. Créer l'objet et l'enregistrer en base
    5. Rediriger vers la liste avec message de succès
    """
    # 1. AUTHENTIFICATION
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/")

    # Récupérer les rôles
    roles_query = session.exec(
        select(func.group_concat(Role.role))
        .join(User, Role.user_id == User.user_id, isouter=True)
        .where(User.mail == user["email"].casefold())
    ).first()
    roles = roles_query.split(",") if roles_query else ["student"]

    # Vérifier admin - sinon refuser avec 403 (Forbidden)
    if "admin" not in roles:
        return RedirectResponse(url="/", status_code=403)

    # 2. VALIDATION - api_key_env
    # Appeler la fonction de validation avec whitelist
    valid, error_msg = _validate_api_key_env(api_key_env)
    if not valid:
        # Si validation échoue, renvoyer le formulaire avec le message d'erreur
        return templates.TemplateResponse(request, "backend/provider_form.html", {
            "request": request,
            "provider": None,
            "error": error_msg,
        }, status_code=400)  # 400 = Bad Request

    # 3. VALIDATION - Unicité du nom
    # Vérifier qu'aucun autre fournisseur n'a ce nom
    existing = session.exec(
        select(LLMProvider).where(LLMProvider.name == name)
    ).first()
    if existing:
        # Si le nom existe déjà, refuser la création
        return templates.TemplateResponse(request, "backend/provider_form.html", {
            "request": request,
            "provider": None,
            "error": f"Un fournisseur nommé '{name}' existe déjà",
        }, status_code=400)

    # 4. CRÉATION
    # Créer l'objet LLMProvider avec les données du formulaire
    provider = LLMProvider(
        name=name,
        api_type=api_type,
        base_url=base_url.rstrip("/"),  # Normalisation: enlever le / à la fin
        api_key_env=api_key_env,
        # Si default_model est vide, le mettre à None (pas une chaîne vide)
        default_model=default_model if default_model else None,
        is_active=is_active,
    )
    # Ajouter à la session et valider
    session.add(provider)
    session.commit()  # Persister en base

    # 5. REDIRECTION
    # Redirection 303 (See Other) vers la liste avec paramètre de succès
    # Le paramètre ?success=created permet au template d'afficher un message
    return RedirectResponse(url="/backend/providers?success=created", status_code=303)


@backend_router.get("/providers/{provider_id}/edit", response_class=HTMLResponse)
def backend_provider_edit(request: Request, provider_id: int, session: SessionDep):
    """Formulaire d'édition d'un fournisseur existant.

    Réutilise le même template que la création, mais en lui passant le
    fournisseur à modifier (le template bascule alors en mode édition).
    """
    # 1. AUTHENTIFICATION + contrôle admin
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

    # 2. Charger le fournisseur ; introuvable → retour à la liste avec erreur
    provider = session.get(LLMProvider, provider_id)
    if not provider:
        return RedirectResponse(
            url="/backend/providers?error=introuvable", status_code=303
        )

    # 3. Afficher le formulaire pré-rempli avec le fournisseur
    return templates.TemplateResponse(request, "backend/provider_form.html", {
        "request": request,
        "provider": provider,
    })


@backend_router.post("/providers/{provider_id}/update")
def update_provider(
    request: Request,
    provider_id: int,
    session: SessionDep,
    name: str = Form(...),  # Libellé du fournisseur (ex: "OpenAI")
    api_type: str = Form(...),  # Type: "ollama", "openai", ou "anthropic"
    base_url: str = Form(...),  # URL racine (ex: https://api.openai.com)
    api_key_env: str = Form(...),  # Nom var env (ex: OPENAI_API_KEY)
    default_model: str = Form(""),  # Modèle par défaut (optionnel)
    is_active: bool = Form(False),  # Fournisseur actif ou pas?
):
    """Met à jour un fournisseur LLM existant après validation.

    Étapes:
    1. Vérifier que l'utilisateur est auth et admin
    2. Charger le fournisseur à modifier
    3. Valider api_key_env contre la whitelist de sécurité
    4. Vérifier que le nom reste unique (hors ce fournisseur)
    5. Appliquer les modifications et sauvegarder
    6. Rediriger vers la liste avec message de succès
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

    # Vérifier admin - sinon refuser avec 403 (Forbidden)
    if "admin" not in roles:
        return RedirectResponse(url="/", status_code=403)

    # 2. Charger le fournisseur à modifier
    provider = session.get(LLMProvider, provider_id)
    if not provider:
        return RedirectResponse(
            url="/backend/providers?error=introuvable", status_code=303
        )

    # 3. VALIDATION - api_key_env (même règle que la création)
    valid, error_msg = _validate_api_key_env(api_key_env)
    if not valid:
        return templates.TemplateResponse(request, "backend/provider_form.html", {
            "request": request,
            "provider": provider,
            "error": error_msg,
        }, status_code=400)  # 400 = Bad Request

    # 4. VALIDATION - Unicité du nom, en excluant CE fournisseur
    #    (sinon on se bloquerait soi-même en gardant le même nom)
    existing = session.exec(
        select(LLMProvider).where(
            LLMProvider.name == name,
            LLMProvider.provider_id != provider_id,
        )
    ).first()
    if existing:
        return templates.TemplateResponse(request, "backend/provider_form.html", {
            "request": request,
            "provider": provider,
            "error": f"Un autre fournisseur nommé '{name}' existe déjà",
        }, status_code=400)

    # 5. MISE À JOUR des champs
    provider.name = name
    provider.api_type = api_type
    provider.base_url = base_url.rstrip("/")  # Normalisation: enlever le / final
    provider.api_key_env = api_key_env
    provider.default_model = default_model if default_model else None
    provider.is_active = is_active
    session.add(provider)
    session.commit()  # Persister les modifications

    # 6. REDIRECTION vers la liste avec message de succès
    return RedirectResponse(url="/backend/providers?success=updated", status_code=303)


@backend_router.post("/providers/{provider_id}/delete")
def delete_provider(request: Request, provider_id: int, session: SessionDep):
    """Supprime un fournisseur, sauf s'il est référencé par un prompt (409).

    Même principe de verrou que pour les prompts utilisés par des synthèses :
    on refuse la suppression tant qu'au moins un prompt pointe sur ce
    fournisseur, pour ne pas casser la configuration de ces prompts.
    """
    # 1. AUTHENTIFICATION + contrôle admin
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

    # 2. Charger le fournisseur ; introuvable → retour liste avec erreur
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

    # 5. REDIRECTION vers la liste avec message de succès
    return RedirectResponse(url="/backend/providers?success=deleted", status_code=303)


@backend_router.get("/providers/{provider_id}/test")
def test_provider(request: Request, provider_id: int, session: SessionDep):
    """Teste la connexion à un fournisseur en listant ses modèles (JSON).

    Appelé en fetch depuis la liste. Renvoie {"ok": true, "count": N} si le
    fournisseur répond, sinon {"ok": false, "error": "..."}. Le message
    d'erreur reste générique côté navigateur ; le détail (clé, URL, exception)
    n'est écrit que dans les logs serveur — jamais renvoyé au client.
    """
    # 1. AUTHENTIFICATION + contrôle admin
    user = get_current_user(request)
    if not user:
        return JSONResponse({"ok": False, "error": "Non authentifié."}, status_code=401)

    roles_query = session.exec(
        select(func.group_concat(Role.role))
        .join(User, Role.user_id == User.user_id, isouter=True)
        .where(User.mail == user["email"].casefold())
    ).first()
    roles = roles_query.split(",") if roles_query else ["student"]

    if "admin" not in roles:
        return JSONResponse({"ok": False, "error": "Accès refusé."}, status_code=403)

    # 2. Charger le fournisseur
    provider = session.get(LLMProvider, provider_id)
    if not provider:
        return JSONResponse({"ok": False, "error": "Fournisseur introuvable."}, status_code=404)

    # 3. Tenter de lister les modèles (test de connexion en lecture)
    try:
        models = list_models(provider)
    except LLMConfigError as error:
        # Mauvaise config (clé absente/non autorisée, type d'API inconnu)
        logger.warning("Test fournisseur %s : config invalide : %s", provider.name, error)
        return JSONResponse(
            {"ok": False, "error": "Configuration invalide (voir les logs serveur)."}
        )
    except RequestException as error:
        # Serveur injoignable, timeout, réponse HTTP en erreur
        logger.warning("Test fournisseur %s : serveur injoignable : %s", provider.name, error)
        return JSONResponse(
            {"ok": False, "error": "Serveur injoignable (voir les logs serveur)."}
        )
    except Exception:
        # Filet de sécurité : rien ne doit fuiter vers le navigateur
        logger.exception("Test fournisseur %s : erreur inattendue", provider.name)
        return JSONResponse(
            {"ok": False, "error": "Erreur inattendue (voir les logs serveur)."}
        )

    # 4. Succès : renvoyer le nombre de modèles disponibles
    return JSONResponse({"ok": True, "count": len(models)})
