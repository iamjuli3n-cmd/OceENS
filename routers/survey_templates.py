"""Administration des modeles de sondage."""

from typing import Optional
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlmodel import delete, func, select
from core.auth import get_current_user
from core.database import SessionDep
from models import Option, Question, Role, Section, Survey, Template, User
from core.dependencies import templates

api_router = APIRouter(tags=["API"], prefix="/api")
backend_router = APIRouter(tags=["Backend"], prefix="/backend")


# ┌─ Page : Gestion des templates (admin only) ─────────────────────────┐
@backend_router.get("/templates", response_class=HTMLResponse)
def backend_templates_page(request: Request, session: SessionDep):
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

    all_templates = session.exec(select(Template).order_by(Template.template_id)).all()
    all_sections  = session.exec(select(Section).order_by(Section.template_id, Section.order)).all()
    all_questions = session.exec(select(Question).order_by(Question.section_id, Question.question_id)).all()

    all_surveys = session.exec(
        select(Survey).order_by(Survey.template_id, Survey.survey_id)
    ).all()

    surveys_by_template: dict = {}
    for sv in all_surveys:
        surveys_by_template.setdefault(sv.template_id, []).append(sv)

    used_template_ids = set(surveys_by_template.keys())

    questions_by_section: dict = {}
    for q in all_questions:
        questions_by_section.setdefault(q.section_id, []).append(q)

    sections_by_template: dict = {}
    for sec in all_sections:
        sections_by_template.setdefault(sec.template_id, []).append(
            {"section": sec, "questions": questions_by_section.get(sec.section_id, [])}
        )

    templates_data = [
        {
            "template": tpl,
            "in_use": tpl.template_id in used_template_ids,
            "sections": sections_by_template.get(tpl.template_id, []),
            "surveys": surveys_by_template.get(tpl.template_id, []),
        }
        for tpl in all_templates
    ]

    return templates.TemplateResponse(
        request=request,
        name="backend/templates.html",
        context={
            "user": user,
            "templates_data": templates_data,
            "success": request.query_params.get("success"),
            "error": request.query_params.get("error"),
        },
    )
# └────────────────────────────────────────────────────────────────────┘


# ┌─ API : CRUD Templates (admin only) ─────────────────────────────────┐
@api_router.post("/templates")
def create_template(
    request: Request,
    session: SessionDep,
    name: Optional[str] = Form(None),
):
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

    tpl = Template(name=name or None)
    try:
        session.add(tpl)
        session.commit()
        session.refresh(tpl)
    except Exception:
        session.rollback()
        return JSONResponse({"error": "Erreur lors de la création."}, status_code=500)

    return JSONResponse({"ok": True, "template_id": tpl.template_id})


@api_router.put("/templates/{template_id}")
def update_template(
    request: Request,
    template_id: int,
    session: SessionDep,
    name: Optional[str] = Form(None),
):
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

    tpl = session.get(Template, template_id)
    if not tpl:
        return JSONResponse({"error": "Template introuvable."}, status_code=404)

    if tpl.active:
        return JSONResponse({"error": "Désactivez le template avant de le modifier."}, status_code=409)

    tpl.name = name or None
    try:
        session.add(tpl)
        session.commit()
    except Exception:
        session.rollback()
        return JSONResponse({"error": "Erreur lors de la mise à jour."}, status_code=500)

    return JSONResponse({"ok": True})


@api_router.delete("/templates/{template_id}")
def delete_template(request: Request, template_id: int, session: SessionDep):
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

    tpl = session.get(Template, template_id)
    if not tpl:
        return JSONResponse({"error": "Template introuvable."}, status_code=404)

    in_use = session.exec(
        select(Survey).where(Survey.template_id == template_id).limit(1)
    ).first()
    if in_use:
        return JSONResponse(
            {"error": "Ce template est utilisé par des sondages existants et ne peut pas être supprimé."},
            status_code=409,
        )

    try:
        # Suppression en cascade : questions → sections → template
        sections = session.exec(
            select(Section).where(Section.template_id == template_id)
        ).all()
        for sec in sections:
            questions = session.exec(
                select(Question).where(Question.section_id == sec.section_id)
            ).all()
            for q in questions:
                session.delete(q)
            session.delete(sec)
        session.delete(tpl)
        session.commit()
    except Exception:
        session.rollback()
        return JSONResponse({"error": "Erreur lors de la suppression."}, status_code=500)

    return JSONResponse({"ok": True})


@api_router.post("/templates/{template_id}/toggle-active")
def toggle_template_active(request: Request, template_id: int, session: SessionDep):
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

    tpl = session.get(Template, template_id)
    if not tpl:
        return JSONResponse({"error": "Template introuvable."}, status_code=404)

    tpl.active = not tpl.active
    try:
        session.add(tpl)
        session.commit()
    except Exception:
        session.rollback()
        return JSONResponse({"error": "Erreur lors de la mise à jour."}, status_code=500)

    return JSONResponse({"ok": True, "active": tpl.active})


@api_router.post("/templates/{template_id}/duplicate")
def duplicate_template(request: Request, template_id: int, session: SessionDep):
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

    original = session.get(Template, template_id)
    if not original:
        return JSONResponse({"error": "Template introuvable."}, status_code=404)

    try:
        # Nouveau template (inactif par défaut)
        new_tpl = Template(
            name=f"{original.name or 'Template'} (copie)",
            active=False,
        )
        session.add(new_tpl)
        session.flush()  # → new_tpl.template_id disponible

        sections = session.exec(
            select(Section)
            .where(Section.template_id == template_id)
            .order_by(Section.order)
        ).all()

        for sec in sections:
            new_sec = Section(
                template_id=new_tpl.template_id,
                name=sec.name,
                order=sec.order,
                section_type=sec.section_type,
            )
            session.add(new_sec)
            session.flush()  # → new_sec.section_id disponible

            questions = session.exec(
                select(Question)
                .where(Question.section_id == sec.section_id)
                .order_by(Question.question_id)
            ).all()

            for q in questions:
                new_q = Question(
                    section_id=new_sec.section_id,
                    question_type=q.question_type,
                    language=q.language,
                    text_fr=q.text_fr,
                    text_en=q.text_en,
                    is_optional=q.is_optional,
                )
                session.add(new_q)
                session.flush()  # → new_q.question_id disponible

                options = session.exec(
                    select(Option).where(Option.question_id == q.question_id)
                ).all()

                for opt in options:
                    session.add(Option(
                        question_id=new_q.question_id,
                        text_fr=opt.text_fr,
                        text_en=opt.text_en,
                        is_positive=opt.is_positive,
                    ))

        session.commit()
    except Exception:
        session.rollback()
        return JSONResponse({"error": "Erreur lors de la duplication."}, status_code=500)

    return JSONResponse({"ok": True, "template_id": new_tpl.template_id})

# └────────────────────────────────────────────────────────────────────┘
