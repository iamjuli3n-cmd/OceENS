"""Pages HTML : accueil et dashboards par role."""

import re

from typing import List, Optional
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import case, func, select
from auth import get_current_user
from database import SessionDep
from models import Answer, Module, Option, Program, Prompt, Question, Respondent, Role, Submission, Summary, Survey, Template, User
from dependencies import templates
from security import VALID_ROLES, can_duplicate_survey, check_role, get_allowed_campuses, get_campus_manager_program_codes, get_results_program_codes, get_student_dashboard_redirect, parse_role_scopes, parse_rprm_formations, require_roles, role_to_dashboard_slug
from helpers import build_survey_prefill, filter_surveys, get_avg_stats, get_dashboard_navigation, get_stats_by_survey, teacher_sort_key

router = APIRouter(tags=["Pages"])
dashboard_router = APIRouter(tags=["Dashboard"], prefix="/dashboard")


# ┌─ Route : Page d'accueil (version app.py conservée) ──────────────┐
@router.get("/", response_class=HTMLResponse)
async def index(request: Request, session: SessionDep):
    """
    Page d'accueil. Si l'utilisateur est déjà connecté avec un rôle
    valide, redirection vers son dashboard. Sinon, affichage du login.
    """
    user = get_current_user(request)
    if user:
        # Déterminer les formations autorisées pour un RP-RM
        roles_query = session.exec(
            select(func.group_concat(Role.role))
            .join(User, Role.user_id == User.user_id, isouter=True)
            .where(User.mail == user["email"].casefold())
        ).first()
        if roles_query:
            roles = roles_query.split(",")
        else:
            roles = ["student"]
        slug = role_to_dashboard_slug(roles)
        dashboard_url = f"/dashboard/{slug}"
        survey_error = request.session.pop("survey_redirect_error", None)
        survey_error_query = {
            "access_denied": "survey_access",
            "not_found": "survey_not_found",
        }.get(survey_error)
        if survey_error_query:
            dashboard_url += f"?error={survey_error_query}"
        return RedirectResponse(url=dashboard_url)
    return templates.TemplateResponse(request=request, name="index.html")

# └────────────────────────────────────────────────────────────────┘

dashboard_router = APIRouter(tags=["Dashboard"], prefix="/dashboard")

api_router = APIRouter(tags=["API"], prefix="/api")

backend_router = APIRouter(tags=["Backend"], prefix="/backend")


# ┌─ Route : Paramétrage (accès restreint Admin + RP-RM) ──────────────┐
@dashboard_router.get("/survey-create", response_class=HTMLResponse)
def surveys_create(
    request: Request,
    session: SessionDep,
    duplicate_from: Optional[int] = None,
):
    # ── Sécurité : vérifier que l'utilisateur est Admin ou RP-RM ──
    auth_result = require_roles(request, session, ["admin", "program_manager"])
    if auth_result is None:
        # Utilisateur non connecté ou rôle insuffisant → redirection
        return RedirectResponse(url="/")
    user,roles = auth_result

    # Déterminer les formations autorisées pour un RP-RM
    allowed_programs = []
    for role in roles:
        if role.startswith("program_manager"):
            allowed_programs.extend(parse_rprm_formations(role))

    survey_prefill = None
    if duplicate_from is not None:
        # La duplication est réservée aux RP-RM, même si la page de
        # création classique reste aussi accessible aux admins.
        if not check_role(roles, ["program_manager","admin"]):
            return HTMLResponse(content="Accès refusé.", status_code=403)

        source_survey = session.exec(
            select(Survey).where(Survey.survey_id == duplicate_from)
        ).first()
        if source_survey is None:
            return HTMLResponse(content="Sondage source introuvable.", status_code=409)

        if not can_duplicate_survey(roles, source_survey.program):
            return HTMLResponse(content="Accès refusé.", status_code=403)

        source_modules = session.exec(
            select(Module)
            .where(Module.survey_id == source_survey.survey_id)
            .order_by(Module.module_id)
        ).all()
        survey_prefill = build_survey_prefill(source_survey, source_modules)

    # Admin pur (sans rôle program_manager) voit tous les templates,
    # les autres (rprm seul ou rprm+admin) ne voient que les actifs
    is_pure_admin = "admin" in roles and not any(
        r.startswith("program_manager") for r in roles
    )
    if is_pure_admin:
        survey_templates = session.exec(select(Template).order_by(Template.template_id)).all()
    else:
        survey_templates = session.exec(
            select(Template).where(Template.active == True).order_by(Template.template_id)
        ).all()

    # Extract all distinct school years
    school_years = session.exec(select(Survey.school_year).distinct()).all()

    # Extract all distinct teachers, scopés au périmètre du RPRM : un
    # admin (sans périmètre RPRM) voit tous les profs, un RPRM ne voit
    # que ceux déjà associés à des modules de ses formations.
    is_unrestricted_admin = (
        allowed_programs is None or allowed_programs == []
    ) and "admin" in roles
    # teacher_query = select(Module.teacher).distinct()
    # if not is_unrestricted_admin:
    #     teacher_query = teacher_query.join(
    #         Survey, Survey.survey_id == Module.survey_id
    #     ).where(Survey.program.in_(allowed_programs))
    # associated_teachers = session.exec(teacher_query).all()
    associated_teachers = session.exec(select(Module.teacher).distinct()).all()

    teachers = set()
    for at in associated_teachers:
        if not at:
            continue
        for teacher in at.split(","):
            teacher = teacher.strip().title()
            if teacher:
                teachers.add(teacher)

    if is_unrestricted_admin:
        programs_list = session.exec(select(Program)).all()
    else:
        programs_list = session.exec(
            select(Program).where(Program.code.in_(allowed_programs))
        ).all()

    campus = {}
    for program in programs_list:
        campus[program.code] = program.campus

    return templates.TemplateResponse(
        request=request,
        name="survey_create.html",
        context={
            "request": request,
            "survey_templates": survey_templates,
            "campus": campus,
            "programs": programs_list,
            "school_years": school_years,
            "teachers_list": sorted(teachers, key=teacher_sort_key),
            "survey_prefill": survey_prefill,
            "user": user,
        },
    )

# └────────────────────────────────────────────────────────────────┘


@dashboard_router.get("/student", response_class=HTMLResponse)
async def student_dashboard(request: Request, session: SessionDep):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/")

    roles_query = session.exec(
        select(func.group_concat(Role.role))
        .join(User, Role.user_id == User.user_id, isouter=True)
        .where(User.mail == user["email"].casefold())
    ).first()
    roles = roles_query.split(",") if roles_query else ["student"]

    dashboard_redirect = get_student_dashboard_redirect(roles)
    if dashboard_redirect:
        return RedirectResponse(url=dashboard_redirect)

    rows = session.exec(
        select(
            Survey.survey_id,
            Survey.program,
            Program.campus,
            Survey.semester,
            Survey.school_year,
            Survey.status,
            Respondent.submission_date,
        )
        .join(User, Respondent.user_id == User.user_id)
        .join(Survey, Respondent.survey_id == Survey.survey_id)
        .join(Program, Program.code == Survey.program, isouter=True)
        .where(User.mail == user["email"].casefold())
    ).all()

    surveys = []
    all_answered_or_closed = True
    for r in rows:
        surveys.append(
            {
                "survey_id": r[0],
                "program": r[1],
                "campus": r[2],
                "semester": r[3],
                "school_year": r[4],
                "is_closed": (r[5] != 1),
                "is_answered": (r[6] != None),
            }
        )
        if r[6] == None and r[5] != 0:
            all_answered_or_closed = False
    context = {
        "user": user,
        "surveys": surveys,
        "all_answered_or_closed": all_answered_or_closed,
        "dashboard_navigation": get_dashboard_navigation(roles, "student"),
    }
    return templates.TemplateResponse(
        request=request,
        name="dashboard/student.html",
        context=context,
    )


@dashboard_router.get("/program-manager", response_class=HTMLResponse)
async def program_manager_dashboard(
    request: Request,
    session: SessionDep,
    school_year: Optional[str] = None,
    semester: Optional[str] = None,
    program: Optional[str] = None,
):
    user = get_current_user(request)

    if not user:
        return RedirectResponse(url="/")

    roles_query = session.exec(
        select(func.group_concat(Role.role))
        .join(User, Role.user_id == User.user_id, isouter=True)
        .where(User.mail == user["email"].casefold())
    ).first()
    if roles_query:
        roles = roles_query.split(",")
    else:
        roles = ["student"]

    if not check_role(roles, ["program_manager", "admin"]):
        return RedirectResponse(url="/")

    allowed_programs = []
    for role in roles:
        if role.startswith("program_manager"):
            allowed_programs.extend(parse_rprm_formations(role))

    # # Admin sans restriction : voit toutes les filières
    # if (allowed_programs is None or allowed_programs == []) and ("admin" in roles):
    #     db_programs = session.exec(select(Program)).all()
    #     program_codes = [p.code for p in db_programs]

    # # RPRM : voit uniquement ses filières
    # else:
    program_codes = [
        p.code if hasattr(p, "code") else p for p in allowed_programs
    ]

    db_programs = session.exec(
        select(Program).where(Program.code.in_(program_codes))
    ).all()

    rows = session.exec(
        select(
            Survey.survey_id,
            Survey.program,
            Program.campus,
            Survey.semester,
            Survey.school_year,
            Survey.status,
            func.count(Respondent.user_id).label("respondents_count"),
            func.count(Respondent.submission_date).label("answers_count"),
        )
        .join(Program, Program.code == Survey.program, isouter=True)
        .join(Respondent, Survey.survey_id == Respondent.survey_id, isouter=True)
        .where(Survey.program.in_(program_codes))
        .group_by(Survey.survey_id)
        .order_by(Survey.survey_id.desc())
    ).all()
    db_programs = session.exec(select(Program)).all()
    program_name_by_code = {p.code: p.name for p in db_programs}

    submissions_rows = session.exec(
        select(
            Submission.survey_id,
            func.count(Submission.submission_id).label("submissions_count"),
        )
        .group_by(Submission.survey_id)
        .order_by(Submission.survey_id.desc())
    ).all()

    submissions_count = {r[0]:r[1] for r in submissions_rows}

    surveys = [
        {
            "survey_id": r[0],
            "program": r[1],
            "program_name": program_name_by_code.get(r[1], r[1]),
            "campus": r[2],
            "semester": r[3],
            "school_year": r[4],
            "is_closed": (r[5] != 1),
            "is_generating": (r[5] == 2),
            "respondents_count": r[6],
            "answers_count": r[7],
            "submissions_count": submissions_count[r[0]] if r[0] in submissions_count.keys() else 0,
        }
        for r in rows
    ]

    available_school_years = sorted(
        {s["school_year"] for s in surveys if s["school_year"]}, reverse=True
    )
    seen_codes: set = set()
    available_programs = []
    for s in surveys:
        if s["program"] and s["program"] not in seen_codes:
            seen_codes.add(s["program"])
            available_programs.append({"code": s["program"], "name": s["program_name"]})
    available_programs.sort(key=lambda p: p["name"])
    surveys = filter_surveys(surveys, school_year, semester, program)

    stats_by_survey = get_stats_by_survey(
        session, surveys
    )
    avg_stats = get_avg_stats(session, surveys)

    programs = [
        {
            "code": p.code,
            "name": p.name,
            "campus": p.campus,
        }
        for p in db_programs
    ]

    prompts = [
        {"prompt_id": p.prompt_id, "description": p.description} for p in  session.exec(select(Prompt)).all()
    ]

    summary_rows = session.exec(select(Summary.survey_id,func.count(Summary.summary_id),func.count(Summary.summary_text),func.sum(case(
   (
       Summary.http_status == 0,0
   ),
   (
       Summary.http_status == 200,0
   ),
   else_=1
))).group_by(Summary.survey_id)).all()

    summaries = { s[0]:
         {"summaries_count": s[1], "summaries_done": s[2], "summaries_error": s[3]} for s in  summary_rows }


    context = {
        "user": user,
        "surveys": surveys,
        "stats_by_survey": stats_by_survey,
        "avg_stats": avg_stats,
        "available_school_years": available_school_years,
        "available_programs": available_programs,
        "selected_school_year": school_year or "",
        "selected_semester": semester or "",
        "selected_program": program or "",
        "programs": programs,
        "allowed_programs":allowed_programs,
        "can_view_survey_students": True,
        "can_delete_survey": True,
        "can_update_survey_status": True,
        "can_duplicate_survey": True,
        "can_generate_summaries":True,
        "prompts":prompts,
        "summaries":summaries,
        "dashboard_navigation": get_dashboard_navigation(
            roles, "program-manager"
        ),
    }

    return templates.TemplateResponse(
        request=request,
        name="dashboard/program_manager.html",
        context=context,
    )


@dashboard_router.get("/campus-manager", response_class=HTMLResponse)
async def campus_manager_dashboard(
    request: Request,
    session: SessionDep,
    school_year: Optional[str] = None,
    semester: Optional[str] = None,
    program: Optional[str] = None,
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/")

    roles_query = session.exec(
        select(func.group_concat(Role.role))
        .join(User, Role.user_id == User.user_id, isouter=True)
        .where(User.mail == user["email"].casefold())
    ).first()
    roles = roles_query.split(",") if roles_query else ["student"]

    if not check_role(roles, ["campus_manager"]):
        return RedirectResponse(url="/")

    allowed_campuses = get_allowed_campuses(roles)
    program_codes = get_campus_manager_program_codes(session, roles)
    db_programs = session.exec(
        select(Program).where(Program.code.in_(program_codes))
    ).all()
    program_name_by_code = {
        program.code: program.name for program in db_programs
    }

    rows = session.exec(
        select(
            Survey.survey_id,
            Survey.program,
            Program.campus,
            Survey.semester,
            Survey.school_year,
            Survey.status,
            func.count(Respondent.user_id).label("respondents_count"),
            func.count(Respondent.submission_date).label("answers_count"),
        )
        .join(Program, Program.code == Survey.program, isouter=True)
        .join(Respondent, Survey.survey_id == Respondent.survey_id, isouter=True)
        .where(Survey.program.in_(program_codes))
        .group_by(Survey.survey_id)
        .order_by(Survey.survey_id.desc())
    ).all()

    survey_ids = [row[0] for row in rows]
    submissions_count = {}
    if survey_ids:
        submissions_rows = session.exec(
            select(
                Submission.survey_id,
                func.count(Submission.submission_id).label("submissions_count"),
            )
            .where(Submission.survey_id.in_(survey_ids))
            .group_by(Submission.survey_id)
        ).all()
        submissions_count = {row[0]: row[1] for row in submissions_rows}

    surveys = [
        {
            "survey_id": row[0],
            "program": row[1],
            "program_name": program_name_by_code.get(row[1], row[1]),
            "campus": row[2],
            "semester": row[3],
            "school_year": row[4],
            "is_closed": (row[5] != 1),
            "is_generating": (row[5] == 2),
            "respondents_count": row[6],
            "answers_count": row[7],
            "submissions_count": submissions_count.get(row[0], 0),
        }
        for row in rows
    ]

    available_school_years = sorted(
        {s["school_year"] for s in surveys if s["school_year"]}, reverse=True
    )
    seen_codes: set = set()
    available_programs = []
    for s in surveys:
        if s["program"] and s["program"] not in seen_codes:
            seen_codes.add(s["program"])
            available_programs.append({"code": s["program"], "name": s["program_name"]})
    available_programs.sort(key=lambda p: p["name"])
    # Campus manager : seulement les sondages fermés avec au moins un répondant
    surveys = [
        s for s in surveys
        if s["is_closed"] and s["respondents_count"] > 0
    ]
    surveys = filter_surveys(surveys, school_year, semester, program)

    stats_by_survey = get_stats_by_survey(
        session, surveys
    )
    avg_stats = get_avg_stats(session, surveys)

    context = {
        "user": user,
        "surveys": surveys,
        "stats_by_survey": stats_by_survey,
        "avg_stats": avg_stats,
        "available_school_years": available_school_years,
        "available_programs": available_programs,
        "selected_school_year": school_year or "",
        "selected_semester": semester or "",
        "selected_program": program or "",
        "allowed_campuses": allowed_campuses,
        "can_view_survey_students": False,
        "can_delete_survey": False,
        "can_update_survey_status": False,
        "can_duplicate_survey": False,
        "can_generate_summaries": False,
        "can_view_visualisation": True,
        "can_export_survey": True,
        "can_view_survey_link": False,
        "dashboard_navigation": get_dashboard_navigation(
            roles, "campus-manager"
        ),
    }

    return templates.TemplateResponse(
        request=request,
        name="dashboard/campus_manager.html",
        context=context,
    )


@dashboard_router.get("/teachers/analytics", response_class=HTMLResponse)
async def teachers_analytics(
    request: Request,
    session: SessionDep,
    school_year: Optional[str] = None,
    semester: Optional[str] = None,
    program: Optional[str] = None,
    teacher: Optional[str] = None,
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/")

    roles_query = session.exec(
        select(func.group_concat(Role.role))
        .join(User, Role.user_id == User.user_id, isouter=True)
        .where(User.mail == user["email"].casefold())
    ).first()
    roles = roles_query.split(",") if roles_query else ["student"]

    if not check_role(roles, ["campus_manager", "program_manager"]):
        return RedirectResponse(url="/")

    # Scope : union des programmes accessibles selon les rôles de l'utilisateur
    # (campus_manager → programmes du campus, program_manager → programmes assignés).
    program_codes = get_results_program_codes(session, roles)
    db_programs = session.exec(
        select(Program).where(Program.code.in_(program_codes))
    ).all()
    program_name_by_code = {p.code: p.name for p in db_programs}

    # Score de satisfaction par (prof, sondage) :
    # on filtre sur QCU_Satisfaction avec Answer.teacher renseigné
    # (ces réponses se trouvent dans les sections ME — évaluation de module/enseignant).
    rows = session.exec(
        select(
            Answer.teacher,
            Module.survey_id,
            Survey.program,
            Survey.school_year,
            Survey.semester,
            Survey.status,
            func.count(Answer.answer_id).label("total"),
            func.sum(case((Option.is_positive == 1, 1), else_=0)).label("positives"),
        )
        .join(Module, Module.module_id == Answer.module_id)
        .join(Survey, Survey.survey_id == Module.survey_id)
        .join(Submission, Submission.submission_id == Answer.submission_id)
        .join(Question, Question.question_id == Answer.question_id)
        .join(Option, Option.option_id == Answer.option_id)
        .where(
            Survey.program.in_(program_codes),
            Question.question_type == "QCU_Satisfaction",
            Answer.teacher.is_not(None),
            Answer.teacher != "",
        )
        .group_by(Answer.teacher, Module.survey_id)
        .order_by(Answer.teacher, Survey.school_year.desc(), Module.survey_id.desc())
    ).all()

    # Construction de la liste complète avant filtrage (pour les menus déroulants)
    selected_teacher = teacher or ""  # sauvegarder avant que la boucle réutilise le nom `teacher`
    teachers_raw: dict = {}
    for teacher, survey_id, prog, sy, sem, status, total, positives in rows:
        teacher_key = teacher.title() if teacher else teacher
        if teacher_key not in teachers_raw:
            teachers_raw[teacher_key] = {"name": teacher_key, "surveys": []}
        score = round(100 * positives / total, 1) if total and total > 0 else None
        teachers_raw[teacher_key]["surveys"].append(
            {
                "survey_id": survey_id,
                "program": prog,
                "program_name": program_name_by_code.get(prog, prog),
                "school_year": sy or "—",
                "semester": sem or "—",
                "is_closed": (status != 1),
                "score": score,
                "total_answers": int(total) if total else 0,
            }
        )

    all_surveys = [s for t in teachers_raw.values() for s in t["surveys"]]
    available_school_years = sorted(
        {s["school_year"] for s in all_surveys if s["school_year"] != "—"}, reverse=True
    )
    seen_codes: set = set()
    available_programs = []
    for s in all_surveys:
        if s["program"] and s["program"] not in seen_codes:
            seen_codes.add(s["program"])
            available_programs.append({"code": s["program"], "name": s["program_name"]})
    available_programs.sort(key=lambda p: p["name"])
    available_teachers = sorted(teachers_raw.keys(), key=teacher_sort_key)

    # Filtrage des surveys par enseignant ; on écarte les enseignants sans résultat
    filtered_teachers = []
    for t in teachers_raw.values():
        filtered_surveys = [
            s for s in t["surveys"]
            if (not school_year or s["school_year"] == school_year)
            and (not semester or s["semester"] == semester)
            and (not program or s["program"] == program)
            and (not selected_teacher or t["name"] == selected_teacher)
        ]
        if filtered_surveys:
            filtered_teachers.append({"name": t["name"], "surveys": filtered_surveys})

    sorted_teachers = sorted(filtered_teachers, key=lambda t: teacher_sort_key(t["name"]))

    context = {
        "user": user,
        "teachers": sorted_teachers,
        "available_school_years": available_school_years,
        "available_programs": available_programs,
        "available_teachers": available_teachers,
        "selected_school_year": school_year or "",
        "selected_semester": semester or "",
        "selected_program": program or "",
        "selected_teacher": selected_teacher,
        "dashboard_navigation": get_dashboard_navigation(roles, ""),
    }

    return templates.TemplateResponse(
        request=request,
        name="dashboard/teacher.html",
        context=context,
    )


@dashboard_router.get("/facilitator", response_class=HTMLResponse)
async def facilitator_dashboard(
    request: Request,
    session: SessionDep,
    school_year: Optional[str] = None,
    semester: Optional[str] = None,
    program: Optional[str] = None,
):
    user = get_current_user(request)

    if not user:
        return RedirectResponse(url="/")

    roles_query = session.exec(
        select(func.group_concat(Role.role))
        .join(User, Role.user_id == User.user_id, isouter=True)
        .where(User.mail == user["email"].casefold())
    ).first()
    if roles_query:
        roles = roles_query.split(",")
    else:
        roles = ["student"]

    if not check_role(roles, ["facilitator", "admin"]):
        return RedirectResponse(url="/")

    allowed_programs = []
    for role in roles:
        if role.startswith("facilitator"):
            allowed_programs.extend(parse_rprm_formations(role))

    # Admin sans restriction : voit toutes les filières
    # if (allowed_programs is None or allowed_programs == []) and ("admin" in roles):
    #     db_programs = session.exec(select(Program)).all()
    #     program_codes = [p.code for p in db_programs]

    # Facilitator : voit uniquement ses filières
    # else:
    program_codes = [
        p.code if hasattr(p, "code") else p for p in allowed_programs
    ]

    db_programs = session.exec(
        select(Program).where(Program.code.in_(program_codes))
    ).all()

    rows = session.exec(
        select(
            Survey.survey_id,
            Survey.program,
            Program.campus,
            Survey.semester,
            Survey.school_year,
            Survey.status,
            func.count(Respondent.user_id).label("respondents_count"),
            func.count(Respondent.submission_date).label("answers_count"),
        )
        .join(Program, Program.code == Survey.program, isouter=True)
        .join(Respondent, Survey.survey_id == Respondent.survey_id, isouter=True)
        .where(Survey.program.in_(program_codes))
        .group_by(Survey.survey_id)
        .order_by(Survey.survey_id.desc())
    ).all()
    db_programs = session.exec(select(Program)).all()
    program_name_by_code = {p.code: p.name for p in db_programs}

    submissions_rows = session.exec(
        select(
            Submission.survey_id,
            func.count(Submission.submission_id).label("submissions_count"),
        )
        .group_by(Submission.survey_id)
        .order_by(Submission.survey_id.desc())
    ).all()

    submissions_count = {r[0]:r[1] for r in submissions_rows}

    surveys = [
        {
            "survey_id": r[0],
            "program": r[1],
            "program_name": program_name_by_code.get(r[1], r[1]),
            "campus": r[2],
            "semester": r[3],
            "school_year": r[4],
            "is_closed": (r[5] != 1),
            "is_generating": (r[5] == 2),
            "respondents_count": r[6],
            "answers_count": r[7],
            "submissions_count": submissions_count[r[0]] if r[0] in submissions_count.keys() else 0,
        }
        for r in rows
    ]

    available_school_years = sorted(
        {s["school_year"] for s in surveys if s["school_year"]}, reverse=True
    )
    seen_codes: set = set()
    available_programs = []
    for s in surveys:
        if s["program"] and s["program"] not in seen_codes:
            seen_codes.add(s["program"])
            available_programs.append({"code": s["program"], "name": s["program_name"]})
    available_programs.sort(key=lambda p: p["name"])
    surveys = filter_surveys(surveys, school_year, semester, program)

    stats_by_survey = get_stats_by_survey(
        session, surveys
    )
    avg_stats = get_avg_stats(session, surveys)

    programs = [
        {
            "code": p.code,
            "name": p.name,
            "campus": p.campus,
        }
        for p in db_programs
    ]

    prompts = [
        {"prompt_id": p.prompt_id, "description": p.description} for p in  session.exec(select(Prompt)).all()
    ]

    summary_rows = session.exec(select(Summary.survey_id,func.count(Summary.summary_id),func.count(Summary.summary_text),func.sum(case(
   (
       Summary.http_status == 0,0
   ),
   (
       Summary.http_status == 200,0
   ),
   else_=1
))).group_by(Summary.survey_id)).all()

    summaries = { s[0]:
         {"summaries_count": s[1], "summaries_done": s[2], "summaries_error": s[3]} for s in  summary_rows }

    context = {
        "user": user,
        "surveys": surveys,
        "stats_by_survey": stats_by_survey,
        "avg_stats": avg_stats,
        "available_school_years": available_school_years,
        "available_programs": available_programs,
        "selected_school_year": school_year or "",
        "selected_semester": semester or "",
        "selected_program": program or "",
        "programs": programs,
        "allowed_programs":allowed_programs,
        "can_view_survey_students": True,
        "can_delete_survey": False,
        "can_update_survey_status": False,
        "can_duplicate_survey": False,
        "can_generate_summaries":True,
        "prompts":prompts,
        "summaries":summaries,
        "dashboard_navigation": get_dashboard_navigation(roles, "facilitator"),
    }

    return templates.TemplateResponse(
        request=request,
        name="dashboard/facilitator.html",
        context=context,
    )

def extract_name(email):
    local_part = email.split("@")[0]
    return " ".join(local_part.split(".")).title()

def extract_initials(email):
    local_part = email.split("@")[0]

    # (?:^|[.\-\@]) -> Non-capturing group: Match start of string OR a delimiter
    # ([a-zA-Z])    -> Capturing group: Match and "keep" the first letter found
    pattern = r"(?:^|[.\-\@])([a-zA-Z])"

    # Find all matches, join them, and convert to uppercase
    matches = re.findall(pattern, local_part)
    return "".join(matches).upper()


@dashboard_router.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    session: SessionDep,
    school_year: Optional[str] = None,
    semester: Optional[str] = None,
    program: Optional[str] = None,
):
    user = get_current_user(request)

    if not user:
        return RedirectResponse(url="/")

    roles_query = session.exec(
        select(func.group_concat(Role.role))
        .join(User, Role.user_id == User.user_id, isouter=True)
        .where(User.mail == user["email"].casefold())
    ).first()
    if roles_query:
        roles = roles_query.split(",")
    else:
        roles = ["student"]

    if not ("admin" in roles):
        return RedirectResponse(url="/")

    rows = session.exec(
        select(
            Survey.survey_id,
            Survey.program,
            Survey.semester,
            Survey.school_year,
            Survey.status,
            func.count(Respondent.user_id).label("respondents_count"),
            func.count(Respondent.submission_date).label("answers_count"),
        )
        .join(Respondent, Survey.survey_id == Respondent.survey_id, isouter=True)
        #        .where(Survey.program.in_(programs)) # Admin sees all
        .group_by(Survey.survey_id)
        .order_by(Survey.survey_id.desc())
    ).all()

    db_programs = session.exec(select(Program)).all()

    programs = [
        {"code": p.code, "name": p.name, "campus": p.campus} for p in db_programs
    ]
    campuses = sorted({p.campus for p in db_programs if p.campus})

    program_name_by_code = {p.code: {"name":p.name,"campus":p.campus}  for p in db_programs}


    submissions_rows = session.exec(
        select(
            Submission.survey_id,
            func.count(Submission.submission_id).label("submissions_count"),
        )
        .group_by(Submission.survey_id)
        .order_by(Submission.survey_id.desc())
    ).all()

    submissions_count = {r[0]:r[1] for r in submissions_rows}

    surveys = [
        {
            "survey_id": r[0],
            "program": r[1],
            "program_name": program_name_by_code[r[1]]["name"] if r[1] in program_name_by_code.keys() else r[1],
            "campus" : program_name_by_code[r[1]]["campus"] if r[1] in program_name_by_code.keys() else "Campus not found",
            "semester": r[2],
            "school_year": r[3],
            "is_closed": (r[4] != 1),
            "is_generating": (r[4] == 2),
            "respondents_count": r[5],
            "answers_count": r[6],
            "submissions_count": submissions_count[r[0]] if r[0] in submissions_count.keys() else 0,
        }
        for r in rows
    ]

    available_school_years = sorted(
        {s["school_year"] for s in surveys if s["school_year"]}, reverse=True
    )
    seen_codes: set = set()
    available_programs = []
    for s in surveys:
        if s["program"] and s["program"] not in seen_codes:
            seen_codes.add(s["program"])
            available_programs.append({"code": s["program"], "name": s["program_name"]})
    available_programs.sort(key=lambda p: p["name"])
    surveys = filter_surveys(surveys, school_year, semester, program)

    stats_by_survey = get_stats_by_survey(
        session, surveys
    )
    avg_stats = get_avg_stats(session, surveys)

    db_users = session.exec(
        select(User, func.group_concat(Role.role))
        .join(Role, Role.user_id == User.user_id, isouter=True)
        .group_by(User.user_id)
    ).all()
    users = [
        {
            "user_id": u[0].user_id,
            "mail": u[0].mail,
            "roles": u[1].split(",") if u[1] else ["student"],
            "initials": extract_initials(u[0].mail),
            "name": extract_name(u[0].mail),
        }
        for u in db_users
    ]


    prompts = [
        {"prompt_id": p.prompt_id, "description": p.description} for p in  session.exec(select(Prompt)).all()
    ]

    summary_rows = session.exec(select(Summary.survey_id,func.count(Summary.summary_id),func.count(Summary.summary_text),func.sum(case(
    (
        Summary.http_status == 0,0
    ),
    (
        Summary.http_status == 200,0
    ),
    else_=1
    ))).group_by(Summary.survey_id)).all()

    summaries = { s[0]:
         {"summaries_count": s[1], "summaries_done": s[2], "summaries_error": s[3]} for s in  summary_rows }

    context = {
        "user": user,
        "surveys": surveys,
        "stats_by_survey": stats_by_survey,
        "avg_stats": avg_stats,
        "available_school_years": available_school_years,
        "available_programs": available_programs,
        "selected_school_year": school_year or "",
        "selected_semester": semester or "",
        "selected_program": program or "",
        "programs": programs,
        "campuses": campuses,
        "users": users,
        "can_view_survey_students": True,
        "can_delete_survey": True,
        "can_update_survey_status": True,
        "can_duplicate_survey": True,
        "can_generate_summaries":True,
        "prompts":prompts,
        "summaries":summaries,
        "dashboard_navigation": get_dashboard_navigation(roles, "admin"),
    }
    return templates.TemplateResponse(
        request=request,
        name="dashboard/admin.html",
        context=context,
    )

# └────────────────────────────────────────────────────────────────┘

# ┌─ API : Gestion des rôles utilisateurs (accès restreint Admin) ────┐
