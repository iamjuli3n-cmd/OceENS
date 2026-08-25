"""Administration des prompts LLM."""

from typing import Optional
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlmodel import delete, func, select
from core.auth import get_current_user
from core.database import SessionDep
from models import LLMProvider, Prompt, Role, Summary, Survey, User
from core.dependencies import templates

# Deux routeurs : /api pour les mutations (form/fetch), /backend pour les pages
api_router = APIRouter(tags=["API"], prefix="/api")
backend_router = APIRouter(tags=["Backend"], prefix="/backend")

# NB : chaque route ci-dessous répète le même contrôle d'accès admin :
#   1. get_current_user → connecté ?
#   2. group_concat des rôles → l'utilisateur est-il "admin" ?
#   3. sinon redirection vers l'accueil.


# ┌─ Pages : Gestion des prompts (admin only) ──────────────────────────┐
@backend_router.get("/prompts", response_class=HTMLResponse)
def backend_prompts(request: Request, session: SessionDep):
    """Page listant tous les prompts + les sondages qui les utilisent."""
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/")

    # Récupérer les rôles concaténés (voir note plus haut)
    roles_query = session.exec(
        select(func.group_concat(Role.role))
        .join(User, Role.user_id == User.user_id, isouter=True)
        .where(User.mail == user["email"].casefold())
    ).first()
    roles = roles_query.split(",") if roles_query else ["student"]

    if "admin" not in roles:
        return RedirectResponse(url="/")

    prompts = session.exec(select(Prompt).order_by(Prompt.prompt_id)).all()

    # Pour chaque prompt, liste des sondages distincts qui ont des synthèses utilisant ce prompt
    # (sert à afficher où le prompt est utilisé et à bloquer sa modification)
    prompt_surveys: dict = {}
    if prompts:
        rows = session.exec(
            select(Summary.prompt_id, Survey.program, Survey.school_year, Survey.semester)
            .join(Survey, Summary.survey_id == Survey.survey_id)
            .where(Summary.prompt_id.in_([p.prompt_id for p in prompts]))
            .distinct()
        ).all()
        for row in rows:
            pid = row[0]
            if pid not in prompt_surveys:
                prompt_surveys[pid] = []
            prompt_surveys[pid].append({
                "program": row[1],
                "school_year": row[2],
                "semester": row[3],
            })

    return templates.TemplateResponse(
        request=request,
        name="backend/prompts.html",
        context={
            "user": user,
            "prompts": prompts,
            "prompt_surveys": prompt_surveys,
            "success": request.query_params.get("success"),
            "error": request.query_params.get("error"),
        },
    )


@backend_router.get("/prompts/new", response_class=HTMLResponse)
def backend_prompt_new(request: Request, session: SessionDep):
    """Affiche le formulaire de création d'un prompt (prompt=None)."""
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

    # Fournisseurs actifs proposés dans le <select> du formulaire
    providers = session.exec(
        select(LLMProvider)
        .where(LLMProvider.is_active == True)
        .order_by(LLMProvider.name)
    ).all()

    return templates.TemplateResponse(
        request=request,
        name="backend/prompt_form.html",
        context={"user": user, "prompt": None, "providers": providers},
    )


@backend_router.get("/prompts/{prompt_id}/edit", response_class=HTMLResponse)
def backend_prompt_edit(request: Request, prompt_id: int, session: SessionDep):
    """Affiche le formulaire d'édition d'un prompt, sauf s'il est déjà utilisé.

    Un prompt référencé par des synthèses existantes est verrouillé : le
    modifier changerait le sens des synthèses déjà générées.
    """
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

    prompt = session.get(Prompt, prompt_id)
    if not prompt:
        return RedirectResponse(url="/backend/prompts?error=Prompt+introuvable.", status_code=303)

    # Verrou : refuser l'édition si au moins une synthèse utilise ce prompt
    in_use = session.exec(
        select(Summary).where(Summary.prompt_id == prompt_id).limit(1)
    ).first()
    if in_use:
        return RedirectResponse(
            url="/backend/prompts?error=Ce+prompt+est+utilisé+par+des+synthèses+existantes+et+ne+peut+pas+être+modifié.",
            status_code=303,
        )

    # Fournisseurs actifs proposés dans le <select> du formulaire
    providers = session.exec(
        select(LLMProvider)
        .where(LLMProvider.is_active == True)
        .order_by(LLMProvider.name)
    ).all()

    return templates.TemplateResponse(
        request=request,
        name="backend/prompt_form.html",
        context={"user": user, "prompt": prompt, "providers": providers},
    )

# └────────────────────────────────────────────────────────────────────┘


def _parse_provider_id(raw: Optional[str]) -> Optional[int]:
    """Convertit la valeur du <select> fournisseur en int ou None.

    Le formulaire envoie "" pour l'option « Par défaut » : on la traduit en
    None (repli sur le fournisseur par défaut côté daemon).
    """
    if not raw or not raw.strip():
        return None
    try:
        return int(raw)
    except ValueError:
        return None


# ┌─ API : CRUD Prompts via formulaires HTML (admin only) ──────────────┐
@api_router.post("/prompts")
def create_prompt(
    request: Request,
    session: SessionDep,
    description: Optional[str] = Form(None),
    model: Optional[str] = Form(None),
    prompt_text: Optional[str] = Form(None),
    provider_id: Optional[str] = Form(None),
):
    """Crée un prompt depuis le formulaire, puis redirige vers la liste."""
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/", status_code=303)

    roles_query = session.exec(
        select(func.group_concat(Role.role))
        .join(User, Role.user_id == User.user_id, isouter=True)
        .where(User.mail == user["email"].casefold())
    ).first()
    roles = roles_query.split(",") if roles_query else ["student"]

    if "admin" not in roles:
        return RedirectResponse(url="/", status_code=303)

    prompt = Prompt(
        description=description or None,
        model=model or None,
        prompt_text=prompt_text or None,
        provider_id=_parse_provider_id(provider_id),
    )
    try:
        session.add(prompt)
        session.commit()
    except Exception as e:
        session.rollback()
        return RedirectResponse(
            url=f"/backend/prompts/new?error=Erreur+lors+de+la+création.",
            status_code=303,
        )

    return RedirectResponse(url="/backend/prompts?success=Prompt+créé.", status_code=303)


@api_router.put("/prompts/{prompt_id}")
def update_prompt(
    request: Request,
    prompt_id: int,
    session: SessionDep,
    description: Optional[str] = Form(None),
    model: Optional[str] = Form(None),
    prompt_text: Optional[str] = Form(None),
    provider_id: Optional[str] = Form(None),
):
    """Met à jour un prompt, sauf s'il est déjà référencé par une synthèse (409)."""
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/", status_code=303)

    roles_query = session.exec(
        select(func.group_concat(Role.role))
        .join(User, Role.user_id == User.user_id, isouter=True)
        .where(User.mail == user["email"].casefold())
    ).first()
    roles = roles_query.split(",") if roles_query else ["student"]

    if "admin" not in roles:
        return RedirectResponse(url="/", status_code=303)

    prompt = session.get(Prompt, prompt_id)
    if not prompt:
        return RedirectResponse(
            url="/backend/prompts?error=Prompt+introuvable.", status_code=303
        )


    in_use = session.exec(
        select(Summary).where(Summary.prompt_id == prompt_id).limit(1)
    ).first()

    if in_use:
        return RedirectResponse(
            url="/backend/prompts?error=Ce+prompt+est+utilisé+par+des+synthèses+existantes+et+ne+peut+pas+être+modifié.",
            status_code=409,
        )

    prompt.description = description or None
    prompt.model = model or None
    prompt.prompt_text = prompt_text or None
    prompt.provider_id = _parse_provider_id(provider_id)

    try:
        session.add(prompt)
        session.commit()
    except Exception as e:
        session.rollback()
        return RedirectResponse(
            url=f"/backend/prompts/{prompt_id}/edit?error=Erreur+lors+de+la+mise+à+jour.",
            status_code=303,
        )

    return RedirectResponse(url="/backend/prompts?success=Prompt+modifié.", status_code=303)


@api_router.delete("/prompts/{prompt_id}")
def delete_prompt(request: Request, prompt_id: int, session: SessionDep):
    """Supprime un prompt, sauf s'il est référencé par une synthèse (409)."""
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Non authentifié."}, status_code=401)

    roles_query = session.exec(
        select(func.group_concat(Role.role))
        .join(User, Role.user_id == User.user_id, isouter=True)
        .where(User.mail == user["email"].casefold())
    ).first()
    roles = roles_query.split(",") if roles_query else ["student"]

    if "admin" not in roles:
        return JSONResponse({"error": "Accès refusé."}, status_code=403)

    prompt = session.get(Prompt, prompt_id)
    if not prompt:
        return JSONResponse({"error": "Prompt introuvable."}, status_code=404)

    in_use = session.exec(
        select(Summary).where(Summary.prompt_id == prompt_id).limit(1)
    ).first()
    if in_use:
        return JSONResponse(
            {"error": "Ce prompt est utilisé par des synthèses existantes et ne peut pas être supprimé."},
            status_code=409,
        )

    try:
        session.delete(prompt)
        session.commit()
    except Exception:
        session.rollback()
        return JSONResponse({"error": "Erreur lors de la suppression."}, status_code=500)

    return JSONResponse({"ok": True})

# └────────────────────────────────────────────────────────────────────┘
