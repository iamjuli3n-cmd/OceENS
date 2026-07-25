"""Administration des fournisseurs LLM."""

import os
from fastapi import APIRouter, Request
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
