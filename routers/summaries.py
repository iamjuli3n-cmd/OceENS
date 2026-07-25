"""Declenchement et suppression des syntheses LLM."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel
from sqlmodel import delete, insert, select
from core.database import SessionDep
from models import Answer, Question, Submission, Summary
from core.dependencies import logger
from core.security import _check_sondage_access_and_status, parse_rprm_formations, require_roles

router = APIRouter(tags=["API"], prefix="/api")


class SummaryRequest(BaseModel):
    prompt_id: int


@router.post("/surveys/{survey_id}/generate-summaries")
def generate_summaries(request: Request, survey_id: int, request_data: SummaryRequest, session: SessionDep):
    auth_result = require_roles(
        request, session, ["admin", "program_manager", "facilitator"]
    )
    if auth_result is None:
        return JSONResponse(content={"error": "Accès refusé."}, status_code=403)
    user,roles = auth_result

    allowed_programs = []
    for role in roles:
        if role.startswith("program_manager"):
            allowed_programs.extend(parse_rprm_formations(role))

    survey, error_or_warning, _, _ = _check_sondage_access_and_status(
        session, survey_id, roles, allowed_programs
    )
    if not survey:
        return JSONResponse(
            content={"error": error_or_warning["error"]},
            status_code=error_or_warning["status_code"],
        )
    if survey.status == 2:
        return JSONResponse(
            content={"error": "Le sondage est déjà en cours de génération."},
            status_code=409,
        )
    if survey.status != 0:
        return JSONResponse(
            content={"error": "Le sondage n'est pas fermé."},
            status_code=409,
        )

    logger.info("GENERATE")


    try:
        prompt_id = request_data.prompt_id

        survey.status=2
        session.add(survey)

        answers = session.exec(select(Answer.module_id,Answer.teacher,Answer.question_id)
                .join(Submission,Submission.submission_id==Answer.submission_id)
                .join(Question,Question.question_id==Answer.question_id)
                .where(Submission.survey_id == survey_id, Question.question_type=="Question_ouverte")
                .group_by(Answer.question_id,Answer.module_id,Answer.teacher)
                ).all()

        if not answers:
            session.rollback()
            return JSONResponse(
                content={"error": "Aucune réponse dans ce sondage"},
                status_code=409,
            )


        rows_to_insert = [{"survey_id":survey_id, "module_id":a[0], "teacher":a[1], "question_id":a[2], "prompt_id":prompt_id, "http_status":0, "summary_text":None, "metadata_text":None} for a in answers]
        logger.info("Résumés à insérer : %s", rows_to_insert)

        session.exec(insert(Summary),params=rows_to_insert)
        session.commit()
    except Exception as e:
        session.rollback()
        return JSONResponse(
            content={"error": f"Impossible d'ajouter ces résumés. ({e})"},
            status_code=409,
        )

    return JSONResponse(content={"message":"everything's fine !"}, status_code=200)


@router.post("/surveys/{survey_id}/destroy-summaries")
def destroy_summaries(request: Request, survey_id: int, session: SessionDep):

    auth_result = require_roles(
        request, session, ["admin", "program_manager", "facilitator"]
    )
    if auth_result is None:
        return JSONResponse(content={"error": "Accès refusé."}, status_code=403)
    user,roles = auth_result

    allowed_programs = []
    for role in roles:
        if role.startswith("program_manager"):
            allowed_programs.extend(parse_rprm_formations(role))

    survey, error_or_warning, _, _ = _check_sondage_access_and_status(
        session, survey_id, roles, allowed_programs
    )
    if not survey:
        return JSONResponse(
            content={"error": error_or_warning["error"]},
            status_code=error_or_warning["status_code"],
        )

    logger.info("DESTROY")

    try:
        survey.status=0
        session.add(survey)


        session.exec(delete(Summary)
                .where(Summary.survey_id == survey_id)
                )
        session.commit()
    except Exception as e:
        session.rollback()
        return JSONResponse(
            content={"error": f"Impossible de retirer ces résumés. ({e})"},
            status_code=500,
        )

    return RedirectResponse(
        url=request.headers.get("referer","/").split('?')[0], # Referer without eventual parameters
        status_code=303,
    )
