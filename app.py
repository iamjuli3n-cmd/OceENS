"""
=============================================================================
OceENS - Application principale FastAPI (version fusionnée)
=============================================================================
Combine :
- L'authentification Azure Entra ID (auth.py)
- La gestion des sessions (SessionMiddleware)
- Les routes du module app (1).py (surveys, questionnaires, API)
- Les dashboards par rôle
"""

from dotenv import load_dotenv


import os
import io
import re
from typing import Annotated, Dict, List, Optional
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, Form, Request, UploadFile, APIRouter
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from requests import session
from sqlmodel import Session, SQLModel, create_engine, select, func, delete
import uvicorn
from seed import seed_all_if_necessary
from database import engine, SessionDep, create_db_and_tables
from services.visualisation_data import bilingual_text

# ┌─ Importation des modèles et du module d'authentification ─────────────┐
from models import (
    Module,
    Question,
    Respondent,
    Answer,
    Section,
    Survey,
    Template,
    Option,
    User,
    Role,
    Submission,
    Program,
)
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware
from auth import router as auth_router, get_current_user
from sondage_loader import load_sondage_complet
from services.export_csv import generate_csv_response
from services.visualisation_data import get_visualisation_context2

load_dotenv()
# ┌─ Configuration ────────────────────────────────────────────────────────┐
# Les trois slugs de dashboard reconnus par l'application
VALID_ROLES = {"admin", "student", "program_manager"}

DASHBOARD_NAVIGATION = (
    {
        "role": "facilitator",
        "slug": "facilitator",
        "label": "Animateur",
    },
    {
        "role": "program_manager",
        "slug": "program-manager",
        "label": "RP-RM",
    },
    {
        "role": "admin",
        "slug": "admin",
        "label": "Administrateur",
    },
    {
        "role": "student",
        "slug": "student",
        "label": "Étudiant",
    },
)


def get_dashboard_navigation(
    roles: list[str], current_dashboard: str
) -> list[dict[str, str]]:
    """Retourne les autres dashboards accessibles pour les rôles fournis."""
    role_names = {role.split(":", 1)[0] for role in roles}

    if "admin" in role_names:
        available_roles = {
            "facilitator",
            "program_manager",
            "admin",
            "student",
        }
    else:
        available_roles = role_names & {"facilitator", "program_manager"}

    return [
        {
            "url": f"/dashboard/{dashboard['slug']}",
            "label": dashboard["label"],
        }
        for dashboard in DASHBOARD_NAVIGATION
        if dashboard["role"] in available_roles
        and dashboard["slug"] != current_dashboard
    ]


def get_student_dashboard_redirect(roles: list[str]) -> str | None:
    """Redirige les rôles métier hors de la vue étudiant, sauf les admins."""
    role_names = {role.split(":", 1)[0] for role in roles}
    if "admin" in role_names:
        return None
    if "program_manager" in role_names:
        return "/dashboard/program-manager"
    if "facilitator" in role_names:
        return "/dashboard/facilitator"
    return None


def can_manage_survey(roles: list[str], survey_program: str | None) -> bool:
    """Vérifie qu'un admin ou un RPRM de la formation peut gérer le sondage."""
    if "admin" in roles:
        return True

    allowed_programs = {
        program.strip()
        for role in roles
        if role.split(":", 1)[0] == "program_manager" and ":" in role
        for program in role.split(":", 1)[1].split(";")
        if program.strip()
    }
    return survey_program in allowed_programs


def delete_survey_with_relations(session: Session, survey_id: int) -> None:
    """Supprime les données propres au sondage sans supprimer son modèle partagé."""
    submission_ids = select(Submission.submission_id).where(
        Submission.survey_id == survey_id
    )

    # Les réponses référencent les soumissions et les modules : elles doivent
    # donc être supprimées avant ces deux tables.
    session.exec(delete(Answer).where(Answer.submission_id.in_(submission_ids)))
    session.exec(delete(Respondent).where(Respondent.survey_id == survey_id))
    session.exec(delete(Module).where(Module.survey_id == survey_id))
    session.exec(delete(Submission).where(Submission.survey_id == survey_id))
    session.exec(delete(Survey).where(Survey.survey_id == survey_id))


def role_to_dashboard_slug(roles: List[str]) -> str:
    """
    Convertit le rôle stocké en BDD en slug de route dashboard.

    "admin"              → "admin"
    "program_manager"              → "program_manager"
    "program_manager:MDE_P2027"    → "program_manager"
    "student" (ou autre) → "student"
    """
    for role in roles:
        if role.startswith("admin"):
            return "admin"
        elif role.startswith("program_manager"):
            return "program-manager"
        else:
            return "student"


def parse_rprm_formations(role: str) -> list[str]:
    """
    Extrait la liste des formations autorisées depuis une chaîne de rôle RP-RM.

    "program_manager:PROGRAM1;PROGRAM2" → ["PROGRAM1", "PROGRAM2"]
    "program_manager:PROGRAM1"            → ["PROGRAM1"]
    "program_manager"                       → []
    "admin"                       → []
    "admin:PROGRAM1;PROGRAM2" → ["PROGRAM1", "PROGRAM2"]
    "admin:PROGRAM1"            → ["PROGRAM1"]
    """
    if not role or not isinstance(role, str) or ":" not in role:
        return []
    return [f.strip() for f in role.split(":")[1].split(";")]


# └────────────────────────────────────────────────────────────────────────┘



# └────────────────────────────────────────────────────────────────────────┘


# ┌─ Modèles Pydantic pour les données entrantes ────────────────────────┐
class SurveyCreate(BaseModel):
    template_id: int
    campus: str
    program: str
    semester: str
    school_year: str
    user_id: Optional[int] = 1


class ModuleCreate(BaseModel):
    id: int
    name: str
    one_teacher_in_list: bool = False
    teachers: List[str]


class UECreate(BaseModel):
    id: int
    name: str
    is_optional: bool
    modules: List[ModuleCreate]


class SurveyFullCreate(BaseModel):
    template_id: int
    campus: str
    program: str
    semester: str
    school_year: str
    ues: List[UECreate]
    students: List[str]


class AnswerItem(BaseModel):
    section_id: int
    question_id: int
    value: str
    option_id: Optional[int] = None
    module_id: Optional[int] = None
    teacher: Optional[str] = None


class SurveySubmission(BaseModel):
    answers: List[AnswerItem]


class RoleUpdate(BaseModel):
    roles: List[str]


class SurveyStudentsAdd(BaseModel):
    emails: List[str]


import json

# └────────────────────────────────────────────────────────────────────────┘

# ┌─ Fonction utilitaire : Vérification des rôles autorisés ────────────────────┐


def check_role(roles: list[str], allowed_roles: list[str]):
    print(f"CHECK {roles} {allowed_roles}")
    for role_and_program in roles:
        if ":" in role_and_program:
            role = role_and_program.split(":")[0]
        else:
            role = role_and_program
        if role in allowed_roles:
            return True
    return False


def require_roles(
    request: Request, session: SessionDep, allowed_roles: list[str]
) -> dict | None:
    """
    Vérifie que l'utilisateur connecté possède un rôle autorisé.

    Logique :
    1. Récupère l'utilisateur via get_current_user()
    2. Si pas connecté → retourne None
    3. Vérifie si le rôle de l'utilisateur correspond à un des rôles autorisés
       - "admin" → match exact avec "admin"
       - "program_manager" → match si le rôle commence par "program_manager" (couvre "program_manager:MDE_P2027")
       - "student" → match exact avec "student"
    4. Si le rôle ne correspond pas → retourne None
    5. Si le rôle correspond → retourne le dict utilisateur

    Args :
        request : L'objet Request FastAPI
        allowed_roles : Liste de rôles autorisés, ex: ["admin", "program_manager"]

    Return :
        dict avec {"name", "email", "role"} si autorisé, None sinon

    Exemple :
        user = require_roles(request, session, ["admin", "program_manager"])
        if user is None:
            return RedirectResponse(url="/dashboard/student")
    """
    user = get_current_user(request)
    if not user:
        return None

    # Get all roles (or student if None)
    roles_query = session.exec(
        select(func.group_concat(Role.role))
        .join(User, Role.user_id == User.user_id, isouter=True)
        .where(User.mail == user["email"].casefold())
    ).first()
    if roles_query:
        roles = roles_query.split(",")
    else:
        roles = ["student"]

    if check_role(roles, allowed_roles):
        return user

    # Aucun rôle autorisé ne correspond
    return None


# ┌─ Fonctions utilitaires ──────────────────────────────────────────────┐
def parse_name(full_name: Optional[str], fallback_id: int) -> Dict[str, Optional[str]]:
    if not full_name:
        return {"id": fallback_id, "firstname": None, "name": None}
    parts = full_name.strip().split()
    if len(parts) == 1:
        return {"id": fallback_id, "firstname": parts[0], "name": ""}
    return {"id": fallback_id, "firstname": parts[0], "name": " ".join(parts[1:])}


# ┌─ Gestion du cycle de vie (lifespan) ──────────────────────────────────┐
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Initialisation de la base de données...")
    create_db_and_tables()
    seed_all_if_necessary()
    yield
    print("Fermeture de la connexion...")


# └────────────────────────────────────────────────────────────────────────┘


def create_app():
    """
    Crée et configure l'application FastAPI fusionnée.
    """
    app = FastAPI(
        title="OceENS",
        description="Système de gestion et de connexion pour étudiants, professeurs et admins",
        lifespan=lifespan,
    )

    # SessionMiddleware (authentification)
    app.add_middleware(
        SessionMiddleware,
        secret_key=os.environ.get(
            "SECRET_KEY", "Y3mNqRjGQixkKjF9GXBCbOw2fHyC1wA3wqbJcQoIxt0="
        ),
        https_only=True,
        same_site="lax",
    )

    # Routeur d'authentification (login/logout/callback Azure Entra ID)
    app.include_router(auth_router)

    # Fichiers statiques et templates (montés une seule fois)
    app.mount("/static", StaticFiles(directory="static"), name="static")
    templates = Jinja2Templates(directory="templates")
    templates.env.policies['json.dumps_kwargs'] = {'sort_keys': False}


    # ┌─ Route : Page d'accueil (version app.py conservée) ──────────────┐
    @app.get("/", response_class=HTMLResponse)
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
            return RedirectResponse(url=f"/dashboard/{slug}")
        return templates.TemplateResponse(request=request, name="index.html")

    # └────────────────────────────────────────────────────────────────┘

    dashboard_router = APIRouter(tags=["Dashboard"], prefix="/dashboard")

    api_router = APIRouter(tags=["API"], prefix="/api")

    # ┌─ Route : Paramétrage (accès restreint Admin + RP-RM) ──────────────┐
    @dashboard_router.get("/survey-create", response_class=HTMLResponse)
    def surveys_create(request: Request, session: SessionDep):
        # ── Sécurité : vérifier que l'utilisateur est Admin ou RP-RM ──
        user = require_roles(request, session, ["admin", "program_manager"])
        if user is None:
            # Utilisateur non connecté ou rôle insuffisant → redirection
            return RedirectResponse(url="/")

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

        allowed_programs = []
        for role in roles:
            if role.startswith("program_manager"):
                allowed_programs.extend(parse_rprm_formations(role))

        # Fetch all potential templates
        survey_templates = session.exec(select(Template)).all()

        # Extract all distinct school years
        school_years = session.exec(select(Survey.school_year).distinct()).all()

        # Extract all distinct teachers
        associated_teachers = session.exec(select(Module.teacher).distinct()).all()
        teachers = set()
        for at in associated_teachers:
            for teacher in at.split(","):
                teachers.add(teacher.strip())

        if (allowed_programs is None or allowed_programs == []) and "admin" in roles:
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
                "teachers_list": sorted(list(teachers)),
                "user": user,
            },
        )

    # └────────────────────────────────────────────────────────────────┘

    # ┌─ API : Modules du survey de l'année précédente ─────────────────┐
    @api_router.get("/modules/previous")
    def modules_precedents_api(
        session: SessionDep,
        semester: str = "",
        program: str = "",
        school_year: str = "",
    ):
        """
        Retourne les modules du survey de l'année scolaire précédente
        pour le même semester et la même program.

        Exemple : school_year="2025-2026" → cherche "2024-2025".
        Si aucun survey précédent n'existe, renvoie un tableau vide.
        """
        if not semester or not program or not school_year:
            return JSONResponse(content={"ues": [], "teachers_list": []})

        # ── Calcul de l'année précédente ──────────────────────────────
        try:
            parts = school_year.split("-")
            if len(parts) == 2:
                year_start = int(parts[0]) - 1
                year_end = int(parts[1]) - 1
                previous_school_year = f"{year_start}-{year_end}"
            else:
                return JSONResponse(content={"ues": [], "teachers_list": []})
        except (ValueError, IndexError):
            return JSONResponse(content={"ues": [], "teachers_list": []})

        # ── Recherche du survey de l'année précédente ────────────────
        previous_survey = session.exec(
            select(Survey).where(
                Survey.school_year == previous_school_year,
                Survey.semester == semester,
                Survey.program == program,
            )
        ).first()

        if not previous_survey:
            return JSONResponse(content={"ues": [], "teachers_list": []})

        # ── Récupération des modules liés à ce sondage ────────────────
        modules = session.exec(
            select(Module).where(
                Module.survey_id == previous_survey.survey_id,
            )
        ).all()

        if not modules:
            return JSONResponse(content={"ues": [], "teachers_list": []})

        # ── Groupement par UE + extraction des professeurs ────────────
        ues_dict = {}
        teachers_seen = {}
        teachers = []
        teacher_index = 1

        for module in modules:
            ue_name = module.ue or "Sans UE"
            if ue_name not in ues_dict:
                ues_dict[ue_name] = {
                    "id": len(ues_dict) + 1,
                    "name": ue_name,
                    "is_optional": bool(module.is_optional),
                    "_open": True,
                    "modules": [],
                }

            teachers_list = []
            if module.teacher:
                teachers_list_as_string = [
                    p.strip() for p in module.teacher.split(",") if p.strip()
                ]
                for teacher_as_string in teachers_list_as_string:
                    parsed = parse_name(teacher_as_string, teacher_index)
                    if parsed["firstname"] or parsed["name"]:
                        key = (
                            (parsed["firstname"] or "").lower(),
                            (parsed["name"] or "").lower(),
                        )
                        if key not in teachers_seen:
                            teachers_seen[key] = teacher_index
                            parsed["id"] = teacher_index
                            teachers.append(parsed)
                            teacher_index += 1
                        teachers_list.append(
                            {
                                "id": teachers_seen[key],
                                "firstname": parsed["firstname"],
                                "name": parsed["name"],
                            }
                        )

            ues_dict[ue_name]["modules"].append(
                {
                    "id": int(module.module_id or 0),
                    "name": module.name or "Module",
                    "one_teacher_in_list": bool(module.one_teacher_in_list),
                    "teachers": teachers_list,
                }
            )

        return JSONResponse(
            content={
                "ues": list(ues_dict.values()),
                "teachersList": teachers_list,
                "previousSchoolYear": previous_school_year,
                "surveyId": previous_survey.survey_id,
            }
        )

    # └────────────────────────────────────────────────────────────────┘

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
        user = require_roles(request, session, ["admin", "program_manager"])
        if user is None:
            return JSONResponse(
                content={"error": "Accès refusé. Rôle Admin ou RP-RM requis."},
                status_code=403,
            )

        # ── Sécurité : vérifier que la program est autorisée pour le RP-RM ──
        roles_query = session.exec(
            select(func.group_concat(Role.role))
            .join(User, Role.user_id == User.user_id, isouter=True)
            .where(User.mail == user["email"].casefold())
        ).first()
        session.flush()
        if roles_query:
            roles = roles_query.split(",")
        else:
            roles = ["student"]

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
                            enseignant_str = (
                                ", ".join(module_data.teachers)
                                if module_data.teachers
                                else None
                            )

                            new_module = Module(
                                name=module_data.name,
                                teacher=enseignant_str,
                                ue=ue.name,
                                is_optional=ue.is_optional,
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
                        print(
                            f"[SONDAGE+IMPORT] {len(existing_email_map)} user(s) existant(s) en BDD"
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

                        print(
                            f"[SONDAGE+IMPORT] Users : {nb_crees} créé(s), {nb_existants} existant(s)"
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

                        print(
                            f"[SONDAGE+IMPORT] Respondent : {nb_repondre_inseres} affectation(s) ajoutée(s)."
                        )

            # Si on arrive ici, le COMMIT a été fait par le context manager
            print(f"[SONDAGE+IMPORT] Transaction COMMIT réussie !")

        except Exception as e:
            print(f"[SONDAGE+IMPORT] ERREUR — ROLLBACK : {type(e).__name__}: {e}")
            import traceback

            traceback.print_exc()
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
            return HTMLResponse(content="Survey introuvable.", status_code=404)

        program = session.exec(
            select(Program).where(Program.code == survey.program)
        ).first()
        

        # ── État du sondage ─────────────────────────────────────────────
        survey_is_closed = survey.status == 0

        # ── Vérifier si l'utilisateur connecté a déjà répondu ───────────
        user_has_answered = False
        user = get_current_user(request)

        if user and user.get("email"):
            db_user = session.exec(
                select(User).where(func.lower(User.mail) == user["email"].casefold())
            ).first()

            if db_user:
                respondent = session.exec(
                    select(Respondent).where(
                        Respondent.survey_id == survey_id,
                        Respondent.user_id == db_user.user_id,
                    )
                ).first()

                if respondent:
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
                        for score in range(1, 11)
                    ]

                questions_data.append(
                    {
                        "question_id": q.question_id,
                        "text": bilingual_text(q.text_fr, q.text_en),
                        "text_fr": q.text_fr or "",
                        "text_en": q.text_en or "",
                        "question_type": q.question_type,
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
                    "is_optional": bool(mod.is_optional),
                    "teachers": teachers,
                    "one_teacher_in_list": bool(mod.one_teacher_in_list),
                }
            )

        # ── Grouper les modules par UE pour la logique conditionnelle ────
        ues_data = {}

        for mod_data in modules_data:
            ue_name = mod_data["ue"] or "Sans UE"

            if ue_name not in ues_data:
                ues_data[ue_name] = {
                    "name": ue_name,
                    "is_optional": mod_data["is_optional"],
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
                content={"error": "Survey introuvable."}, status_code=404
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
        user = require_roles(request, session, ["admin", "program_manager"])
        if user is None:
            return JSONResponse(
                content={"error": "Accès refusé."},
                status_code=403,
            )

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
                status_code=404,
            )

        roles_query = session.exec(
            select(func.group_concat(Role.role))
            .join(User, Role.user_id == User.user_id, isouter=True)
            .where(User.mail == user["email"].casefold())
        ).first()
        if roles_query:
            roles = roles_query.split(",")
        else:
            roles = ["student"]

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
        session.commit()

        return RedirectResponse(
            url=request.headers.get("referer","/").split('?')[0], # Referer without eventual parameters
            status_code=303,
        )

    def _get_survey_for_student_management(
        survey_id: int,
        request: Request,
        session: Session,
    ):
        """Retourne le sondage si l'utilisateur peut gérer ses étudiants."""
        user = require_roles(request, session, ["admin", "program_manager"])
        if user is None:
            return None, JSONResponse(
                content={"error": "Accès refusé."}, status_code=403
            )

        survey = session.exec(
            select(Survey).where(Survey.survey_id == survey_id)
        ).first()
        if not survey:
            return None, JSONResponse(
                content={"error": "Sondage introuvable."}, status_code=404
            )

        roles_query = session.exec(
            select(func.group_concat(Role.role))
            .join(User, Role.user_id == User.user_id, isouter=True)
            .where(User.mail == user["email"].casefold())
        ).first()
        roles = roles_query.split(",") if roles_query else ["student"]

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
                status_code=404,
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
        except Exception:
            session.rollback()
            return JSONResponse(
                content={"error": "Impossible de retirer cet étudiant du sondage."},
                status_code=500,
            )

        result = _get_survey_students_payload(session, survey_id)
        result["message"] = "Étudiant retiré du sondage."
        return result

    @api_router.delete("/surveys/{survey_id}")
    @api_router.post("/surveys/{survey_id}/delete")
    def delete_survey(
        survey_id: int,
        request: Request,
        session: SessionDep,
    ):
        user = require_roles(request, session, ["admin", "program_manager"])
        if user is None:
            return JSONResponse(
                content={"error": "Accès refusé."},
                status_code=403,
            )

        survey = session.exec(
            select(Survey).where(Survey.survey_id == survey_id)
        ).first()
        if not survey:
            return JSONResponse(
                content={"error": "Sondage introuvable."},
                status_code=404,
            )

        roles_query = session.exec(
            select(func.group_concat(Role.role))
            .join(User, Role.user_id == User.user_id, isouter=True)
            .where(User.mail == user["email"].casefold())
        ).first()
        roles = roles_query.split(",") if roles_query else ["student"]

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
                    "is_closed": (r[5] == 0),
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
    async def program_manager_dashboard(request: Request, session: SessionDep):
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
                "is_closed": (r[5] == 0),
                "respondents_count": r[6],
                "answers_count": r[7],
                "submissions_count": submissions_count[r[0]] if r[0] in submissions_count.keys() else 0,
            }
            for r in rows
        ]

        programs = [
            {
                "code": p.code,
                "name": p.name,
                "campus": p.campus,
            }
            for p in db_programs
        ]

        context = {
            "user": user,
            "surveys": surveys,
            "programs": programs,
            "allowed_programs":allowed_programs,
            "can_view_survey_students": True,
            "can_delete_survey": True,
            "can_update_survey_status": True,
            "dashboard_navigation": get_dashboard_navigation(
                roles, "program-manager"
            ),
        }

        return templates.TemplateResponse(
            request=request,
            name="dashboard/program_manager.html",
            context=context,
        )

    @dashboard_router.get("/facilitator", response_class=HTMLResponse)
    async def facilitator_dashboard(request: Request, session: SessionDep):
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
                "is_closed": (r[5] == 0),
                "respondents_count": r[6],
                "answers_count": r[7],
                "submissions_count": submissions_count[r[0]] if r[0] in submissions_count.keys() else 0,
            }
            for r in rows
        ]

        programs = [
            {
                "code": p.code,
                "name": p.name,
                "campus": p.campus,
            }
            for p in db_programs
        ]

        context = {
            "user": user,
            "surveys": surveys,
            "programs": programs,
            "allowed_programs":allowed_programs,
            "can_view_survey_students": True,
            "can_delete_survey": False,
            "can_update_survey_status": False,
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
    async def admin_dashboard(request: Request, session: SessionDep):
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
                "is_closed": (r[4] == 0),
                "respondents_count": r[5],
                "answers_count": r[6],
                "submissions_count": submissions_count[r[0]] if r[0] in submissions_count.keys() else 0,
            }
            for r in rows
        ]

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

        programs = [
            {"code": p.code, "name": p.name, "campus": p.campus} for p in db_programs
        ]

        context = {
            "user": user,
            "surveys": surveys,
            "programs": programs,
            "users": users,
            "can_view_survey_students": True,
            "can_delete_survey": True,
            "can_update_survey_status": True,
            "dashboard_navigation": get_dashboard_navigation(roles, "admin"),
        }
        return templates.TemplateResponse(
            request=request,
            name="dashboard/admin.html",
            context=context,
        )

    # └────────────────────────────────────────────────────────────────┘

    # ┌─ API : Gestion des rôles utilisateurs (accès restreint Admin) ────┐
    def _is_valid_role(roles: List[str]) -> bool:
        return check_role(roles, ["student", "program_manager", "admin", "facilitator"])

    @api_router.put("/users/{user_id}/role")
    def update_user_role(
        request: Request, user_id: int, body: RoleUpdate, session: SessionDep
    ):
        # ── Sécurité : seul un Admin peut modifier les rôles ──
        admin = require_roles(request, session, ["admin"])
        if admin is None:
            return JSONResponse(
                content={"error": "Accès refusé. Rôle Admin requis."},
                status_code=403,
            )

        for role in body.roles:
            if not _is_valid_role([role]):
                return JSONResponse(
                    content={"detail": f"Rôle invalide : '{role}'"},
                    status_code=422,
                )
        user = session.get(User, user_id)
        if not user:
            return JSONResponse(
                content={"detail": f"Utilisateur {user_id} introuvable"},
                status_code=404,
            )
        # Remove all previous roles
        session.exec(delete(Role).where(Role.user_id == user_id))
        session.commit()
        for role in body.roles:
            new_role = Role(user_id=user_id, role=role)
            session.add(new_role)
        session.commit()

        return {"user_id": user.user_id, "mail": user.mail, "roles": body.roles}

    # ┌─ Visualisation & Export CSV ──────────────────────────────────────┐
    def _check_sondage_access_and_status(
        session: Session,
        survey_id: int,
        roles: list[str],
        allowed_programs: list[str],
    ):
        """Helper pour vérifier les accès et le statut de participation"""
        survey = session.exec(
            select(Survey).where(Survey.survey_id == survey_id)
        ).first()
        if not survey:
            return (
                None,
                {"error": "Survey introuvable.", "status_code": 404},
                None,
                None,
            )

        if "admin" not in roles and survey.program not in allowed_programs:
            return (
                None,
                {
                    "error": f"Formation '{survey.program}' non autorisée pour votre rôle.",
                    "status_code": 403,
                },
                None,
                None,
            )

        respondents_count = (
            session.exec(
                select(func.count(Respondent.user_id)).where(
                    Respondent.survey_id == survey_id,
                )
            ).first()
            or 0
        )
        answers_count = (
            session.exec(
                select(func.count(Respondent.user_id)).where(
                    Respondent.survey_id == survey_id,
                    Respondent.submission_date
                    != None,  # submission_date NOT NULL = has_answered
                )
            ).first()
            or 0
        )

        

        warning_msg = None

        return survey, warning_msg, respondents_count, answers_count

    @api_router.get("/surveys/{survey_id}/export")
    def export_sondage_csv(request: Request, survey_id: int, session: SessionDep):
        user = require_roles(request, session, ["admin", "program_manager"])
        if user is None:
            return JSONResponse(content={"error": "Accès refusé."}, status_code=403)

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
        user = require_roles(request, session, ["admin", "program_manager"])
        if user is None:
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
        context["user"]=user



        return templates.TemplateResponse(
            request=request, name="visualisation.html", context=context
        )

    # └───────────────────────────────────────────────────────────────────┘

    app.include_router(api_router)
    app.include_router(dashboard_router)

    return app


# ┌─ Instance applicative globale ───────────────────────────────────────┐
app = create_app()
# └──────────────────────────────────────────────────────────────────────┘


if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )
