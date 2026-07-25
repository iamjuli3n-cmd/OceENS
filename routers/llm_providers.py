"""Administration des fournisseurs LLM."""

import os
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import func, select
from core.auth import get_current_user
from core.database import SessionDep
from models import LLMProvider, Prompt, Role, User
from core.dependencies import templates

backend_router = APIRouter(tags=["Backend"], prefix="/backend")


@backend_router.get("/providers", response_class=HTMLResponse)
def backend_providers(request: Request, session: SessionDep):
    """Liste tous les fournisseurs LLM avec statut des clés."""
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

    # Charger tous les fournisseurs
    providers = session.exec(select(LLMProvider).order_by(LLMProvider.provider_id)).all()

    # Pour chaque fournisseur, vérifier la clé d'env et compter les prompts qui l'utilisent
    provider_data = []
    for provider in providers:
        key_present = os.getenv(provider.api_key_env) is not None

        # Compter les prompts qui utilisent ce fournisseur
        prompt_count = session.exec(
            select(func.count(Prompt.prompt_id)).where(
                Prompt.provider_id == provider.provider_id
            )
        ).first() or 0

        provider_data.append({
            "provider": provider,
            "key_present": key_present,
            "prompt_count": prompt_count,
        })

    return templates.TemplateResponse("backend/providers.html", {
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

    return templates.TemplateResponse("backend/provider_form.html", {
        "request": request,
        "provider": None,
    })


# Whitelist pour api_key_env
ALLOWED_API_KEY_PATTERNS = ("LLM_", "_API_KEY")


def _validate_api_key_env(value: str) -> tuple[bool, str]:
    """Valide le nom de la variable d'environnement contre une whitelist."""
    if not value:
        return False, "La variable d'environnement est requise"

    if not value.replace("_", "").isalnum() or not value.isupper():
        return False, "Doit contenir uniquement des majuscules, chiffres et underscores"

    if not any(value.startswith(p) or value.endswith(p) for p in ALLOWED_API_KEY_PATTERNS):
        return False, f"Doit commencer par LLM_ ou finir par _API_KEY"

    # Interdire les variables sensibles
    forbidden = ("SECRET_KEY", "ENTRA_CLIENT_ID", "ENTRA_CLIENT_SECRET", "ENTRA_TENANT_ID")
    if value in forbidden:
        return False, f"La variable {value} est réservée au système"

    return True, ""


@backend_router.post("/providers/create")
def create_provider(
    request: Request,
    session: SessionDep,
    name: str = Form(...),
    api_type: str = Form(...),
    base_url: str = Form(...),
    api_key_env: str = Form(...),
    default_model: str = Form(""),
    is_active: bool = Form(False),
):
    """Crée un nouveau fournisseur LLM."""
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

    # Validation de api_key_env
    valid, error_msg = _validate_api_key_env(api_key_env)
    if not valid:
        return templates.TemplateResponse("backend/provider_form.html", {
            "request": request,
            "provider": None,
            "error": error_msg,
        }, status_code=400)

    # Vérifier que le nom est unique
    existing = session.exec(
        select(LLMProvider).where(LLMProvider.name == name)
    ).first()
    if existing:
        return templates.TemplateResponse("backend/provider_form.html", {
            "request": request,
            "provider": None,
            "error": f"Un fournisseur nommé '{name}' existe déjà",
        }, status_code=400)

    # Créer le fournisseur
    provider = LLMProvider(
        name=name,
        api_type=api_type,
        base_url=base_url.rstrip("/"),  # Retirer slash trailing
        api_key_env=api_key_env,
        default_model=default_model if default_model else None,
        is_active=is_active,
    )
    session.add(provider)
    session.commit()

    return RedirectResponse(url="/backend/providers?success=created", status_code=303)
