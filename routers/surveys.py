"""Sondages : creation, lecture, modification, statut, suppression, export, visualisation."""

from typing import Dict
from datetime import datetime
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlmodel import Session, delete, func, select
from auth import get_current_user
from database import SessionDep
from models import Answer, Module, Option, Program, Question, Respondent, Section, Submission, Survey, User
from dependencies import logger, templates
from schemas import SurveyFullCreate, SurveySubmission
from security import _check_sondage_access_and_status, can_manage_survey, get_results_program_codes, parse_rprm_formations, require_roles
from helpers import delete_survey_with_relations
from sondage_loader import load_sondage_complet
from services.export_csv import generate_csv_response
from services.visualisation_data import bilingual_text, get_visualisation_context2

api_router = APIRouter(tags=["API"], prefix="/api")


# ┌─ API : Création d'un survey (accès restreint Admin + RP-RM) ────┐
@api_router.post("/surveys")
async def create_survey(
    request: Request,
    session: SessionDep,
    survey: SurveyFullCreate,
):
    """
    Crée un survey ET importe les étudiants en une seule transaction.
    Si l'import Excel échoue, le survey est annulé (ROLLBACK).
    """
    # ── Sécurité : vérifier que l'utilisateur est Admin ou RP-RM ──
    auth_result = require_roles(request, session, ["admin", "program_manager"])
    if auth_result is None:
        return JSONResponse(
            content={"error": "Accès refusé. Rôle Admin ou RP-RM requis."},
            status_code=403,
        )
    user,roles = auth_result

    # ── Sécurité : vérifier que la program est autorisée pour le RP-RM ──
    allowed_programs = []
    for role in roles:
        if role.startswith("program_manager"):
            allowed_programs.extend(parse_rprm_formations(role))

    if "admin" not in roles and survey.program not in allowed_programs:
        return JSONResponse(
            content={
                "error": f"Formation '{survey.program}' non autorisée pour votre rôle."
            },
            status_code=403,
        )

    equivalent_survey = session.exec(select(Survey).where(Survey.template_id==survey.template_id,
                    Survey.program==survey.program,
                    Survey.semester==survey.semester,
                    Survey.school_year==survey.school_year)).first()

    if equivalent_survey is not None:
        return JSONResponse(
            content={"error": "Un sondage existe déjà pour la même formation, même semestre, même année !"},
            status_code=403,
        )


    # ── Transaction unique : Survey + Modules + Users + Respondent ──
    nb_crees = 0
    nb_existants = 0
    nb_repondre_inseres = 0

    try:
        with session.begin_nested():
            with session.no_autoflush:
                # ── Étape 1 : Créer le survey ──

                new_survey = Survey(
                    template_id=survey.template_id,
                    program=survey.program,
                    semester=survey.semester,
                    school_year=survey.school_year,
                    status=0,
                )
                session.add(new_survey)
                session.flush()  # Pour obtenir survey_id généré

                survey_id = new_survey.survey_id

                # ── Étape 2 : Créer les modules ──
                for ue in survey.ues:
                    for module_data in ue.modules:
                        module_data.teachers = [t.title() for t in module_data.teachers] # Teacher Name always titled (Capitalize each word)
                        enseignant_str = (
                            ", ".join(module_data.teachers) 
                            if module_data.teachers
                            else None
                        )

                        new_module = Module(
                            name=module_data.name,
                            teacher=enseignant_str,
                            ue=ue.name,
                            one_teacher_in_list=module_data.one_teacher_in_list,
                            survey_id=survey_id,
                        )
                        session.add(new_module)

                # ── Étape 3 : Importer les étudiants (si fichier fourni) ──
                if survey.students:
                    email_to_user_id: Dict[str, int] = {}

                    existing_users = session.exec(select(User)).all()
                    existing_email_map = {
                        u.mail.lower(): u.user_id for u in existing_users if u.mail
                    }
                    logger.info(
                        "[SONDAGE+IMPORT] %d user(s) existant(s) en BDD",
                        len(existing_email_map),
                    )

                    max_id = max([u.user_id for u in existing_users] + [0])

                    for email in survey.students:
                        if email in existing_email_map:
                            email_to_user_id[email] = existing_email_map[email]
                            nb_existants += 1
                        else:
                            max_id += 1
                            new_user = User(
                                user_id=max_id,
                                mail=email,
                                role="student",
                            )
                            session.add(new_user)
                            email_to_user_id[email] = max_id
                            existing_email_map[email] = max_id
                            nb_crees += 1

                    logger.info(
                        "[SONDAGE+IMPORT] Users : %d créé(s), %d existant(s)",
                        nb_crees,
                        nb_existants,
                    )

                    user_ids = list(email_to_user_id.values())
                    if user_ids:
                        # On ne supprime PAS les anciennes affectations.
                        # Un étudiant peut être affecté à plusieurs sondages sur plusieurs années.
                        # On vérifie seulement si l'affectation existe déjà pour CE sondage.
                        existing_respondent_user_ids = session.exec(
                            select(Respondent.user_id).where(
                                # Respondent.template_id == survey.template_id,
                                Respondent.survey_id == survey_id,
                                Respondent.user_id.in_(user_ids),
                            )
                        ).all()

                        existing_respondent_user_ids = set(
                            existing_respondent_user_ids
                        )

                        # Insertion (INSERT) : ajouter uniquement les nouvelles affectations
                        for user_id in user_ids:
                            if user_id in existing_respondent_user_ids:
                                continue  # Déjà affecté à ce sondage, on ne fait rien
                            new_repondre = Respondent(
                                survey_id=survey_id,
                                user_id=user_id,
                                submission_date=None,
                            )
                            session.add(new_repondre)
                            nb_repondre_inseres += 1

                    logger.info(
                        "[SONDAGE+IMPORT] Respondent : %d affectation(s) ajoutée(s).",
                        nb_repondre_inseres,
                    )

        # Si on arrive ici, le COMMIT a été fait par le context manager
        logger.info("[SONDAGE+IMPORT] Transaction COMMIT réussie !")

    except Exception as e:
        logger.exception(
            "[SONDAGE+IMPORT] ERREUR — ROLLBACK : %s: %s",
            type(e).__name__,
            e,
        )
        return JSONResponse(
            content={"error": f"Erreur lors de la création du survey : {str(e)}"},
            status_code=500,
        )

    result = {
        "message": "Survey créé avec succès",
        "survey_id": survey_id,
    }
    if survey.students:
        result.update(
            {
                "nb_emails_lus": len(survey.students),
                "nb_users_crees": nb_crees,
                "nb_users_existants": nb_existants,
                "nb_repondre_inseres": nb_repondre_inseres,
            }
        )
    return result

# └────────────────────────────────────────────────────────────────┘


# ┌─ Page questionnaire ─────────────────────────────────────────────┐
@api_router.get("/surveys/{survey_id}", response_class=HTMLResponse)
def questionnaire_page(request: Request, survey_id: int, session: SessionDep):
    survey = session.exec(
        select(Survey).where(
            Survey.survey_id == survey_id,
        )
    ).first()

    if not survey:
        request.session["survey_redirect_error"] = "not_found"
        return RedirectResponse(url="/", status_code=303)

    user = get_current_user(request)
    user_email = user.get("email") if user else None
    if not user_email:
        return RedirectResponse(url="/", status_code=303)

    respondent = session.exec(
        select(Respondent)
        .join(User, User.user_id == Respondent.user_id)
        .where(
            Respondent.survey_id == survey_id,
            func.lower(User.mail) == user_email.casefold(),
        )
    ).first()
    if not respondent:
        request.session["survey_redirect_error"] = "access_denied"
        return RedirectResponse(url="/", status_code=303)

    program = session.exec(
        select(Program).where(Program.code == survey.program)
    ).first()


    # ── État du sondage ─────────────────────────────────────────────
    survey_is_closed = (survey.status != 1)

    # ── Vérifier si l'utilisateur connecté a déjà répondu ───────────
    user_has_answered = respondent.submission_date is not None

    # ── Chargement des données du questionnaire ─────────────────────
    sections = session.exec(
        select(Section)
        .where(Section.template_id == survey.template_id)
        .order_by(Section.order)
    ).all()

    questions = session.exec(
        select(Question)
        .join(Section,Section.section_id==Question.section_id)
        .where(Section.template_id == survey.template_id)
    ).all()

    options = session.exec(
        select(Option)
        .join(Question,Question.question_id==Option.question_id)
        .join(Section,Section.section_id==Question.section_id)
        .where(Section.template_id == survey.template_id)
    ).all()


    modules = session.exec(
        select(Module).where(Module.survey_id == survey_id)
    ).all()

    sections_data = []

    for sec in sections:
        sec_questions = [q for q in questions if q.section_id == sec.section_id]
        sec_questions.sort(key=lambda q: q.question_id)

        questions_data = []

        for q in sec_questions:
            q_options = [
                o
                for o in options
                if o.question_id == q.question_id
            ]
            q_options.sort(key=lambda o: o.option_id)
            option_items = [
                {
                    "option_id": o.option_id,
                    "text": bilingual_text(o.text_fr, o.text_en),
                    "text_fr": o.text_fr or "",
                    "text_en": o.text_en or "",
                    "value": o.text_fr or o.text_en or "",
                    "is_positive": (
                        None if o.is_positive is None else bool(o.is_positive)
                    ),
                }
                for o in q_options
            ]
            if q.question_type == "NPS" and not option_items:
                option_items = [
                    {
                        "option_id": None,
                        "text": str(score),
                        "text_fr": str(score),
                        "text_en": str(score),
                        "value": str(score),
                        "is_positive": None,
                    }
                    for score in range(0, 11)
                ]

            questions_data.append(
                {
                    "question_id": q.question_id,
                    "text": bilingual_text(q.text_fr, q.text_en),
                    "text_fr": q.text_fr or "",
                    "text_en": q.text_en or "",
                    "question_type": q.question_type,
                    "is_optional": bool(q.is_optional),
                    "category": sec.name,
                    "options": option_items,
                }
            )

        sections_data.append(
            {
                "section_id": sec.section_id,
                "name": sec.name,
                "questions": questions_data,
            }
        )

    module_section = next(
        (
            section
            for section in sections_data
            if section["name"] == "Module / Enseignant"
        ),
        None,
    )
    module_attendance_question = None
    if module_section:
        module_attendance_question = next(
            (
                question
                for question in module_section["questions"]
                if question["question_type"] == "QCU_Attendance"
            ),
            None,
        )

    modules_data = []

    for mod in modules:
        teachers = []
        if mod.teacher:
            teachers = [
                teacher.strip()
                for teacher in mod.teacher.split(",")
                if teacher.strip()
            ]

        modules_data.append(
            {
                "module_id": mod.module_id,
                "name": mod.name,
                "ue": mod.ue,
                "teachers": teachers,
                "one_teacher_in_list": bool(mod.one_teacher_in_list),
            }
        )

    # ── Grouper les modules par UE ───────────────────────────────────
    ues_data = {}

    for mod_data in modules_data:
        ue_name = mod_data["ue"] or "Sans UE"

        if ue_name not in ues_data:
            ues_data[ue_name] = {
                "name": ue_name,
                "modules": [],
            }

        ues_data[ue_name]["modules"].append(mod_data)

    ues_list = list(ues_data.values())
    return templates.TemplateResponse(
        request=request,
        name="survey.html",
        context={
            "request": request,
            "survey": {
                "template_id": survey.template_id,
                "survey_id": survey.survey_id,
                "campus": program.campus if program else "Campus non trouvé",
                "program": survey.program,
                "semester": survey.semester,
                "school_year": survey.school_year,
                "status": survey.status,
            },
            "program": {
                "code": program.code if program else survey.program,
                "name": program.name if program else survey.program,
            },
            "sections": sections_data,
            "modules": modules_data,
            "ues": ues_list,
            "module_section": module_section,
            "module_attendance_question": module_attendance_question,
            "survey_is_closed": survey_is_closed,
            "user_has_answered": user_has_answered,
            "user": user,
        },
    )

# └────────────────────────────────────────────────────────────────┘


# ┌─ API : Soumission des réponses du questionnaire ─────────────────┐
@api_router.post("/surveys/{survey_id}")
def submit_reponses(
    request: Request,
    survey_id: int,
    submission: SurveySubmission,
    session: SessionDep,
):
    # 1. Authentification : récupérer l'utilisateur connecté (Azure Entra ID)
    user = get_current_user(request)
    if not user:
        return JSONResponse(
            content={"error": "Authentification requise. Veuillez vous connecter."},
            status_code=401,
        )

    # 2. Résoudre l'user_id depuis l'email de l'utilisateur connecté
    db_user = session.exec(
        select(User).where(User.mail == user["email"].casefold())
    ).first()
    if not db_user:
        return JSONResponse(
            content={
                "error": "Utilisateur "
                + user["email"]
                + "non trouvé dans la base de données."
            },
            status_code=403,
        )

    # 3. Vérifier que le survey existe
    survey = session.exec(
        select(Survey).where(
            Survey.survey_id == survey_id,
        )
    ).first()
    if not survey:
        return JSONResponse(
            content={"error": "Survey introuvable."}, status_code=409
        )

    if survey.status == 0:
        return JSONResponse(
            content={"error": "Le sondage est fermé"}, status_code=403
        )

    # 4. Vérifier que cet élève est assigné à ce sondage (table Respondent)
    #    Règle stricte : pas de INSERT, UPDATE uniquement
    respondent = session.exec(
        select(Respondent).where(
            Respondent.survey_id == survey_id,
            Respondent.user_id == db_user.user_id,
        )
    ).first()
    if not respondent:
        return JSONResponse(
            content={
                "error": "Vous n'êtes pas autorisé ou assigné à répondre à ce sondage."
            },
            status_code=403,
        )

    # 5. Vérifier que l'élève n'a pas déjà soumis ses réponses
    if (
        respondent.submission_date != None
    ):  # submission_date NOT NULL = has_answered
        return JSONResponse(
            content={
                "error": "Vous avez déjà soumis vos réponses pour ce sondage."
            },
            status_code=409,
        )

    submitted_question_ids = {rep.question_id for rep in submission.answers}
    valid_question_ids = set()
    if submitted_question_ids:
        valid_question_ids = set(
            session.exec(
                select(Question.question_id)
                .join(Section, Section.section_id == Question.section_id)
                .where(
                    Section.template_id == survey.template_id,
                    Question.question_id.in_(submitted_question_ids),
                )
            ).all()
        )

    invalid_question_ids = submitted_question_ids - valid_question_ids
    if invalid_question_ids:
        return JSONResponse(
            content={
                "error": "Question(s) hors du questionnaire : "
                + ", ".join(map(str, sorted(invalid_question_ids)))
            },
            status_code=422,
        )

    submitted_option_ids = {
        rep.option_id for rep in submission.answers if rep.option_id is not None
    }
    options_by_id = {}
    if submitted_option_ids:
        option_rows = session.exec(
            select(Option).where(Option.option_id.in_(submitted_option_ids))
        ).all()
        options_by_id = {option.option_id: option for option in option_rows}

    for rep in submission.answers:
        if rep.option_id is None:
            continue
        option = options_by_id.get(rep.option_id)
        if option is None or option.question_id != rep.question_id:
            return JSONResponse(
                content={
                    "error": (
                        f"Option {rep.option_id} invalide pour la question "
                        f"{rep.question_id}."
                    )
                },
                status_code=422,
            )

    try:
        with session.begin_nested():
            # Création d'une soumission anonyme.
            # SQLite génère automatiquement submission_id via l'autoincrement.
            new_submission = Submission(
                survey_id=survey_id,
                created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            )
            session.add(new_submission)
            session.flush()  # Pour obtenir submission_id généré

            submission_id = new_submission.submission_id

            # Insérer chaque réponse individuelle dans la table answers
            for rep in submission.answers:
                selected_option = options_by_id.get(rep.option_id)
                new_reponse = Answer(
                    module_id=rep.module_id,
                    teacher=rep.teacher,
                    question_id=rep.question_id,
                    option_id=rep.option_id,
                    submission_id=submission_id,
                    value=(
                        selected_option.text_fr or selected_option.text_en
                        if selected_option
                        else rep.value
                    ),
                )
                session.add(new_reponse)

            # UPDATE de la ligne Respondent : marquer comme répondu
            respondent.submission_date = datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            session.add(respondent)

        # Commit de la transaction principale
        session.commit()

    except Exception as e:
        session.rollback()
        return JSONResponse(
            content={"error": f"Erreur lors de l'enregistrement : {str(e)}"},
            status_code=500,
        )

    return {
        "message": "Réponses enregistrées avec succès",
        # "user_id": db_user.user_id,
    }


@api_router.post("/surveys/{survey_id}/status")
def update_survey_status(
    survey_id: int,
    request: Request,
    session: SessionDep,
    status: int = Form(...),
):
    auth_result = require_roles(request, session, ["admin", "program_manager"])
    if auth_result is None:
        return JSONResponse(
            content={"error": "Accès refusé."},
            status_code=403,
        )
    user,roles = auth_result

    if status not in (0, 1):
        return JSONResponse(
            content={"error": "Statut invalide."},
            status_code=400,
        )

    survey = session.exec(
        select(Survey).where(Survey.survey_id == survey_id)
    ).first()

    if not survey:
        return JSONResponse(
            content={"error": "Sondage introuvable."},
            status_code=409,
        )

    allowed_programs = []
    for role in roles:
        if role.startswith("program_manager"):
            allowed_programs.extend(parse_rprm_formations(role))

    if (
        not "admin" in roles
        and allowed_programs
        and survey.program not in allowed_programs
    ):
        return JSONResponse(
            content={"error": "Formation non autorisée pour votre rôle."},
            status_code=403,
        )

    survey.status = status
    session.add(survey)
    session.flush()
    session.commit()

    return RedirectResponse(
        url=request.headers.get("referer","/").split('?')[0], # Referer without eventual parameters
        status_code=303,
    )



@api_router.delete("/surveys/{survey_id}")
@api_router.post("/surveys/{survey_id}/delete")
def delete_survey(
    survey_id: int,
    request: Request,
    session: SessionDep,
):
    auth_result = require_roles(request, session, ["admin", "program_manager"])
    if auth_result is None:
        return JSONResponse(
            content={"error": "Accès refusé."},
            status_code=403,
        )
    user,roles = auth_result

    survey = session.exec(
        select(Survey).where(Survey.survey_id == survey_id)
    ).first()
    if not survey:
        return JSONResponse(
            content={"error": "Sondage introuvable."},
            status_code=409,
        )

    if not can_manage_survey(roles, survey.program):
        return JSONResponse(
            content={"error": "Formation non autorisée pour votre rôle."},
            status_code=403,
        )

    try:
        delete_survey_with_relations(session, survey_id)
        session.commit()
    except Exception:
        session.rollback()
        return JSONResponse(
            content={"error": "Impossible de supprimer le sondage."},
            status_code=500,
        )

    dashboard_url = (
        "/dashboard/admin" if "admin" in roles else "/dashboard/program-manager"
    )
    if request.method == "DELETE":
        return {"message": "Sondage supprimé avec succès."}
    return RedirectResponse(url=dashboard_url, status_code=303)

# └────────────────────────────────────────────────────────────────┘

# ┌─ Route : Dashboards par rôle ────────────────────────────────────┐


@api_router.get("/surveys/{survey_id}/export")
def export_sondage_csv(request: Request, survey_id: int, session: SessionDep):
    user,roles = require_roles(
        request,
        session,
        ["admin", "program_manager", "campus_manager"],
    )
    if user is None:
        return JSONResponse(content={"error": "Accès refusé."}, status_code=403)

    allowed_programs = get_results_program_codes(session, roles)

    survey, error_or_warning, _, _ = _check_sondage_access_and_status(
        session, survey_id, roles, allowed_programs
    )
    if not survey:
        return JSONResponse(
            content={"error": error_or_warning["error"]},
            status_code=error_or_warning["status_code"],
        )

    # Utilisation de la BDD locale pour le loader sqlite3 natif
    survey_obj = load_sondage_complet(survey_id)

    resp = generate_csv_response(survey_obj)
    if isinstance(error_or_warning, str):
        resp.headers["X-Warning"] = "Sondage en cours - donnees partielles"

    return resp


@api_router.get("/surveys/{survey_id}/visualisation", response_class=HTMLResponse)
def visualisation_page(request: Request, survey_id: int, session: SessionDep):
    user,roles = require_roles(
        request,
        session,
        ["admin", "program_manager", "campus_manager"],
    )
    if user is None:
        return RedirectResponse(url="/")

    allowed_programs = get_results_program_codes(session, roles)

    survey, error_or_warning, respondents_count, answers_count = (
        _check_sondage_access_and_status(
            session, survey_id, roles, allowed_programs
        )
    )
    if not survey:
        return HTMLResponse(
            content=f"<h1>Erreur</h1><p>{error_or_warning['error']}</p>",
            status_code=error_or_warning["status_code"],
        )


    context = get_visualisation_context2(survey_id)
    context["user"] = user

    # URL de retour = page qui a envoyé l'utilisateur ici (dashboard admin,
    # program_manager, etc.). Si le referer est la page elle-même (rechargement)
    # ou absent, on retombe sur l'accueil.
    referer = request.headers.get("referer", "")
    current_path = str(request.url)
    context["back_url"] = referer if referer and referer != current_path else "/"

    return templates.TemplateResponse(
        request=request, name="visualisation.html", context=context
    )

# └───────────────────────────────────────────────────────────────────┘
