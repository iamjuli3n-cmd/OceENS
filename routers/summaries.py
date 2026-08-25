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


# Corps de requête : le prompt LLM à utiliser pour la génération
class SummaryRequest(BaseModel):
    prompt_id: int


@router.post("/surveys/{survey_id}/generate-summaries")
def generate_summaries(request: Request, survey_id: int, request_data: SummaryRequest, session: SessionDep):
    """Prépare la file de synthèses LLM pour un sondage fermé.

    Ne génère pas les synthèses directement : insère des lignes `Summary` avec
    http_status=0 (en attente). C'est le daemon qui les traitera ensuite.
    Passe le sondage en status=2 (génération en cours) pour verrouiller.
    """
    # ── Sécurité : admin, RP ou animateur ──
    auth_result = require_roles(
        request, session, ["admin", "program_manager", "facilitator"]
    )
    if auth_result is None:
        return JSONResponse(content={"error": "Accès refusé."}, status_code=403)
    user,roles = auth_result

    # Filières autorisées pour cet utilisateur (périmètre RP)
    allowed_programs = []
    for role in roles:
        if role.startswith("program_manager"):
            allowed_programs.extend(parse_rprm_formations(role))

    # Vérifier accès au sondage + périmètre
    survey, error_or_warning, _, _ = _check_sondage_access_and_status(
        session, survey_id, roles, allowed_programs
    )
    if not survey:
        return JSONResponse(
            content={"error": error_or_warning["error"]},
            status_code=error_or_warning["status_code"],
        )
    # status 2 = déjà en cours de génération → refuser
    if survey.status == 2:
        return JSONResponse(
            content={"error": "Le sondage est déjà en cours de génération."},
            status_code=409,
        )
    # status 0 = fermé (requis) ; toute autre valeur = pas prêt
    if survey.status != 0:
        return JSONResponse(
            content={"error": "Le sondage n'est pas fermé."},
            status_code=409,
        )

    logger.info("GENERATE")


    try:
        prompt_id = request_data.prompt_id

        # Verrouiller le sondage en "génération en cours"
        survey.status=2
        session.add(survey)

        # Récupérer les combinaisons distinctes (module, enseignant, question)
        # pour lesquelles il existe des réponses ouvertes (verbatims) à synthétiser
        answers = session.exec(select(Answer.module_id,Answer.teacher,Answer.question_id)
                .join(Submission,Submission.submission_id==Answer.submission_id)
                .join(Question,Question.question_id==Answer.question_id)
                .where(Submission.survey_id == survey_id, Question.question_type=="Question_ouverte")
                .group_by(Answer.question_id,Answer.module_id,Answer.teacher)
                ).all()

        # Aucun verbatim → rien à synthétiser, on annule
        if not answers:
            session.rollback()
            return JSONResponse(
                content={"error": "Aucune réponse dans ce sondage"},
                status_code=409,
            )


        # Construire une ligne Summary par combinaison, en attente (http_status=0)
        rows_to_insert = [{"survey_id":survey_id, "module_id":a[0], "teacher":a[1], "question_id":a[2], "prompt_id":prompt_id, "http_status":0, "summary_text":None, "metadata_text":None} for a in answers]
        logger.info("Résumés à insérer : %s", rows_to_insert)

        # Insertion en masse dans la file de synthèses
        session.exec(insert(Summary),params=rows_to_insert)
        session.commit()
    except Exception as e:
        # En cas d'erreur, tout annuler pour ne pas laisser le sondage bloqué
        session.rollback()
        return JSONResponse(
            content={"error": f"Impossible d'ajouter ces résumés. ({e})"},
            status_code=409,
        )

    return JSONResponse(content={"message":"everything's fine !"}, status_code=200)


@router.post("/surveys/{survey_id}/destroy-summaries")
def destroy_summaries(request: Request, survey_id: int, session: SessionDep):
    """Supprime toutes les synthèses d'un sondage et le rouvre (status=0).

    Opération inverse de generate-summaries : vide la file `Summary` pour ce
    sondage et remet son statut à fermé.
    """
    # ── Sécurité : admin, RP ou animateur ──
    auth_result = require_roles(
        request, session, ["admin", "program_manager", "facilitator"]
    )
    if auth_result is None:
        return JSONResponse(content={"error": "Accès refusé."}, status_code=403)
    user,roles = auth_result

    # Filières autorisées (périmètre RP)
    allowed_programs = []
    for role in roles:
        if role.startswith("program_manager"):
            allowed_programs.extend(parse_rprm_formations(role))

    # Vérifier accès au sondage + périmètre
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
        # Remettre le sondage à l'état fermé
        survey.status=0
        session.add(survey)

        # Supprimer toutes les synthèses de ce sondage
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

    # Rediriger vers la page d'origine (referer sans ses paramètres éventuels)
    return RedirectResponse(
        url=request.headers.get("referer","/").split('?')[0], # Referer sans les paramètres éventuels
        status_code=303,
    )
