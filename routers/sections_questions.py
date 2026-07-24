"""Administration des sections et des questions."""

from typing import Optional
from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse
from sqlmodel import delete, func, select
from core.auth import get_current_user
from core.database import SessionDep
from models import Answer, Question, Role, Section, Template, User

api_router = APIRouter(tags=["API"], prefix="/api")


# ┌─ API : CRUD Sections (admin only) ──────────────────────────────────┐
@api_router.post("/sections")
def create_section(
    request: Request,
    session: SessionDep,
    template_id: int = Form(...),
    name: Optional[str] = Form(None),
    order: int = Form(0),
    section_type: Optional[str] = Form(None),
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

    sec = Section(
        template_id=template_id,
        name=name or None,
        order=order,
        section_type=section_type or None,
    )
    try:
        session.add(sec)
        session.commit()
        session.refresh(sec)
    except Exception:
        session.rollback()
        return JSONResponse({"error": "Erreur lors de la création."}, status_code=500)

    return JSONResponse({"ok": True, "section_id": sec.section_id})


@api_router.put("/sections/{section_id}")
def update_section(
    request: Request,
    section_id: int,
    session: SessionDep,
    name: Optional[str] = Form(None),
    order: int = Form(0),
    section_type: Optional[str] = Form(None),
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

    sec = session.get(Section, section_id)
    if not sec:
        return JSONResponse({"error": "Section introuvable."}, status_code=404)

    tpl = session.get(Template, sec.template_id)
    if tpl and tpl.active:
        return JSONResponse({"error": "Désactivez le template avant de le modifier."}, status_code=409)

    sec.name = name or None
    sec.order = order
    sec.section_type = section_type or None
    try:
        session.add(sec)
        session.commit()
    except Exception:
        session.rollback()
        return JSONResponse({"error": "Erreur lors de la mise à jour."}, status_code=500)

    return JSONResponse({"ok": True})


@api_router.delete("/sections/{section_id}")
def delete_section(request: Request, section_id: int, session: SessionDep):
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

    sec = session.get(Section, section_id)
    if not sec:
        return JSONResponse({"error": "Section introuvable."}, status_code=404)

    tpl = session.get(Template, sec.template_id)
    if tpl and tpl.active:
        return JSONResponse({"error": "Désactivez le template avant de le modifier."}, status_code=409)

    questions = session.exec(select(Question).where(Question.section_id == section_id)).all()
    if questions:
        q_ids = [q.question_id for q in questions]
        has_answers = session.exec(
            select(Answer).where(Answer.question_id.in_(q_ids)).limit(1)
        ).first()
        if has_answers:
            return JSONResponse(
                {"error": "Cette section contient des questions ayant des réponses existantes."},
                status_code=409,
            )

    try:
        session.delete(sec)
        session.commit()
    except Exception:
        session.rollback()
        return JSONResponse({"error": "Erreur lors de la suppression."}, status_code=500)

    return JSONResponse({"ok": True})
# └────────────────────────────────────────────────────────────────────┘


# ┌─ API : CRUD Questions (admin only) ─────────────────────────────────┐
@api_router.post("/questions")
def create_question(
    request: Request,
    session: SessionDep,
    section_id: int = Form(...),
    question_type: Optional[str] = Form(None),
    language: Optional[str] = Form(None),
    text_fr: Optional[str] = Form(None),
    text_en: Optional[str] = Form(None),
    is_optional: int = Form(0),
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

    sec = session.get(Section, section_id)
    if not sec:
        return JSONResponse({"error": "Section introuvable."}, status_code=404)
    tpl = session.get(Template, sec.template_id)
    if tpl and tpl.active:
        return JSONResponse({"error": "Désactivez le template avant de le modifier."}, status_code=409)

    q = Question(
        section_id=section_id,
        question_type=question_type or None,
        language=language or None,
        text_fr=text_fr or None,
        text_en=text_en or None,
        is_optional=bool(is_optional),
    )
    try:
        session.add(q)
        session.commit()
        session.refresh(q)
    except Exception:
        session.rollback()
        return JSONResponse({"error": "Erreur lors de la création."}, status_code=500)

    return JSONResponse({"ok": True, "question_id": q.question_id})


@api_router.put("/questions/{question_id}")
def update_question(
    request: Request,
    question_id: int,
    session: SessionDep,
    question_type: Optional[str] = Form(None),
    language: Optional[str] = Form(None),
    text_fr: Optional[str] = Form(None),
    text_en: Optional[str] = Form(None),
    is_optional: int = Form(0),
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

    q = session.get(Question, question_id)
    if not q:
        return JSONResponse({"error": "Question introuvable."}, status_code=404)

    sec = session.get(Section, q.section_id)
    tpl = session.get(Template, sec.template_id) if sec else None
    if tpl and tpl.active:
        return JSONResponse({"error": "Désactivez le template avant de le modifier."}, status_code=409)

    in_use = session.exec(
        select(Answer).where(Answer.question_id == question_id).limit(1)
    ).first()
    if in_use:
        return JSONResponse(
            {"error": "Cette question a des réponses existantes et ne peut pas être modifiée."},
            status_code=409,
        )

    q.question_type = question_type or None
    q.language = language or None
    q.text_fr = text_fr or None
    q.text_en = text_en or None
    q.is_optional = bool(is_optional)
    try:
        session.add(q)
        session.commit()
    except Exception:
        session.rollback()
        return JSONResponse({"error": "Erreur lors de la mise à jour."}, status_code=500)

    return JSONResponse({"ok": True})


@api_router.delete("/questions/{question_id}")
def delete_question(request: Request, question_id: int, session: SessionDep):
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

    q = session.get(Question, question_id)
    if not q:
        return JSONResponse({"error": "Question introuvable."}, status_code=404)

    sec = session.get(Section, q.section_id)
    tpl = session.get(Template, sec.template_id) if sec else None
    if tpl and tpl.active:
        return JSONResponse({"error": "Désactivez le template avant de le modifier."}, status_code=409)

    in_use = session.exec(
        select(Answer).where(Answer.question_id == question_id).limit(1)
    ).first()
    if in_use:
        return JSONResponse(
            {"error": "Cette question a des réponses existantes et ne peut pas être supprimée."},
            status_code=409,
        )

    try:
        session.delete(q)
        session.commit()
    except Exception:
        session.rollback()
        return JSONResponse({"error": "Erreur lors de la suppression."}, status_code=500)

    return JSONResponse({"ok": True})
# └────────────────────────────────────────────────────────────────────┘
