"""Inscription et desinscription des etudiants a un sondage."""

import os
import re

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlmodel import delete, func, select, Session
from database import SessionDep
from models import Respondent, Survey, User
from schemas import SurveyStudentsAdd
from security import can_manage_survey, require_roles

api_router = APIRouter(tags=["API"], prefix="/api")


@api_router.get("/surveys/{survey_id}/students")
def get_survey_students(
    survey_id: int,
    request: Request,
    session: SessionDep,
):
    """Retourne les étudiants associés à un sondage géré par l'utilisateur."""
    _, error = _get_survey_for_student_management(survey_id, request, session)
    if error:
        return error

    return _get_survey_students_payload(session, survey_id)


@api_router.post("/surveys/{survey_id}/students")
def add_survey_students(
    survey_id: int,
    body: SurveyStudentsAdd,
    request: Request,
    session: SessionDep,
):
    """Ajoute un ou plusieurs étudiants à un sondage."""
    _, error = _get_survey_for_student_management(survey_id, request, session)
    if error:
        return error

    allowed_domains = {
        domain.strip().casefold()
        for domain in os.environ.get(
            "ALLOWED_DOMAINS", "epf.fr,epfedu.fr"
        ).split(",")
        if domain.strip()
    }
    email_pattern = re.compile(
        r"^[a-zA-Z0-9._-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    )

    emails = []
    invalid_emails = []
    for raw_email in body.emails:
        email = raw_email.strip().casefold()
        domain = email.rsplit("@", 1)[-1] if "@" in email else ""
        if not email_pattern.fullmatch(email) or domain not in allowed_domains:
            if raw_email.strip():
                invalid_emails.append(raw_email.strip())
            continue
        if email not in emails:
            emails.append(email)

    if invalid_emails:
        return JSONResponse(
            content={
                "error": "Adresse(s) e-mail invalide(s) ou domaine non autorisé : "
                + ", ".join(invalid_emails)
            },
            status_code=422,
        )
    if not emails:
        return JSONResponse(
            content={"error": "Saisissez au moins une adresse e-mail."},
            status_code=400,
        )

    try:
        existing_users = session.exec(
            select(User).where(func.lower(User.mail).in_(emails))
        ).all()
        users_by_mail = {
            user.mail.casefold(): user for user in existing_users if user.mail
        }

        selected_users = []
        created_users_count = 0
        for email in emails:
            db_user = users_by_mail.get(email)
            if db_user is None:
                db_user = User(mail=email)
                session.add(db_user)
                session.flush()
                users_by_mail[email] = db_user
                created_users_count += 1
            selected_users.append(db_user)

        user_ids = [user.user_id for user in selected_users]
        existing_respondent_ids = set(
            session.exec(
                select(Respondent.user_id).where(
                    Respondent.survey_id == survey_id,
                    Respondent.user_id.in_(user_ids),
                )
            ).all()
        )

        added_count = 0
        for db_user in selected_users:
            if db_user.user_id in existing_respondent_ids:
                continue
            session.add(
                Respondent(
                    survey_id=survey_id,
                    user_id=db_user.user_id,
                    submission_date=None,
                )
            )
            added_count += 1

        session.commit()
    except Exception:
        session.rollback()
        return JSONResponse(
            content={"error": "Impossible d'ajouter les étudiants au sondage."},
            status_code=500,
        )

    result = _get_survey_students_payload(session, survey_id)
    result.update(
        {
            "message": "Liste des étudiants mise à jour.",
            "added_count": added_count,
            "already_assigned_count": len(emails) - added_count,
            "created_users_count": created_users_count,
        }
    )
    return result


@api_router.delete("/surveys/{survey_id}/students")
def remove_survey_student(
    survey_id: int,
    email: str,
    request: Request,
    session: SessionDep,
):
    """Retire un étudiant n'ayant pas encore répondu au sondage."""
    _, error = _get_survey_for_student_management(survey_id, request, session)
    if error:
        return error

    normalized_email = email.strip().casefold()
    respondent = session.exec(
        select(Respondent)
        .join(User, User.user_id == Respondent.user_id)
        .where(
            Respondent.survey_id == survey_id,
            func.lower(User.mail) == normalized_email,
        )
    ).first()
    if not respondent:
        return JSONResponse(
            content={"error": "Étudiant non associé à ce sondage."},
            status_code=409,
        )
    if respondent.submission_date is not None:
        return JSONResponse(
            content={
                "error": "Cet étudiant a déjà répondu et ne peut plus être retiré."
            },
            status_code=409,
        )

    try:
        session.delete(respondent)
        session.commit()
    except Exception as e:
        session.rollback()
        return JSONResponse(
            content={"error": "Impossible de retirer cet étudiant du sondage. ({e})"},
            status_code=500,
        )

    result = _get_survey_students_payload(session, survey_id)
    result["message"] = "Étudiant retiré du sondage."
    return result


def _get_survey_for_student_management(
    survey_id: int,
    request: Request,
    session: Session,
):
    """Retourne le sondage si l'utilisateur peut gérer ses étudiants."""
    auth_result = require_roles(request, session, ["admin", "program_manager"])
    if auth_result is None:
        return None, JSONResponse(
            content={"error": "Accès refusé."}, status_code=403
        )
    user,roles = auth_result

    survey = session.exec(
        select(Survey).where(Survey.survey_id == survey_id)
    ).first()
    if not survey:
        return None, JSONResponse(
            content={"error": "Sondage introuvable."}, status_code=404
        )

    if not can_manage_survey(roles, survey.program):
        return None, JSONResponse(
            content={"error": "Formation non autorisée pour votre rôle."},
            status_code=403,
        )

    return survey, None


def _get_survey_students_payload(session: Session, survey_id: int) -> dict:
    rows = session.exec(
        select(User.mail, Respondent.submission_date)
        .join(Respondent, Respondent.user_id == User.user_id)
        .where(Respondent.survey_id == survey_id)
        .order_by(User.mail)
    ).all()

    students = [
        {
            "mail": row[0],
            "has_answered": row[1] is not None,
        }
        for row in rows
        if row[0]
    ]
    return {
        "survey_id": survey_id,
        "count": len(students),
        "students": students,
    }
