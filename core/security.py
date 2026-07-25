"""Authentification, roles et perimetres.

L'authentification seule n'autorise aucune action metier : ces helpers sont
le point de passage oblige de tout controle d'acces cote serveur.
"""

from typing import List
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session, func, select
from core.auth import get_current_user
from core.database import SessionDep
from models import Program, Respondent, Role, Survey, User
from core.dependencies import logger


# Ensemble des rôles valides reconnus par l'application
VALID_ROLES = {
    "admin",
    "student",
    "program_manager",
    "facilitator",
    "campus_manager",
}


def check_role(roles: list[str], allowed_roles: list[str]):
    """Vrai si au moins un des rôles de l'utilisateur est dans les rôles autorisés.

    Les rôles peuvent porter un périmètre après `:` (ex: "program_manager:INFO").
    On ne compare que la partie AVANT le `:` (le nom du rôle), pas le périmètre.
    """
    logger.info("CHECK %s %s", roles, allowed_roles)
    for role_and_program in roles:
        # Isoler le nom du rôle en retirant le périmètre éventuel (après ":")
        if ":" in role_and_program:
            role = role_and_program.split(":")[0]
        else:
            role = role_and_program
        # Dès qu'un rôle correspond, l'accès est accordé
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
        auth_result = require_roles(request, session, ["admin", "program_manager"])
        if auth_result is None:
            return RedirectResponse(url="/")
        user,roles = auth_result
    """
    # 1. L'utilisateur est-il connecté ?
    user = get_current_user(request)
    if not user:
        return None,None

    # 2. Récupérer tous les rôles de l'utilisateur, concaténés en une chaîne
    #    group_concat renvoie ex: "admin,program_manager:INFO". Défaut: student.
    roles_query = session.exec(
        select(func.group_concat(Role.role))
        .join(User, Role.user_id == User.user_id, isouter=True)
        .where(User.mail == user["email"].casefold())
    ).first()
    if roles_query:
        roles = roles_query.split(",")
    else:
        roles = ["student"]

    # 3. Un des rôles est-il autorisé ? Si oui, renvoyer (user, roles)
    if check_role(roles, allowed_roles):
        return user,roles

    # Aucun rôle autorisé ne correspond
    return None,None


# ┌─ Fonctions utilitaires ──────────────────────────────────────────────┐


def parse_role_scopes(role: str) -> list[str]:
    """Extrait les périmètres (non vides) stockés après le nom d'un rôle.

    Ex: "program_manager:INFO;GEN" → ["INFO", "GEN"]. Le périmètre est la
    partie après ":", découpée par ";".
    """
    # Pas de ":" → pas de périmètre
    if not role or not isinstance(role, str) or ":" not in role:
        return []

    # Découper la partie après ":" par ";" et nettoyer les espaces
    return [
        scope.strip()
        for scope in role.split(":", 1)[1].split(";")
        if scope.strip()
    ]


def get_role_scopes(roles: list[str], role_name: str) -> list[str]:
    """Renvoie les périmètres distincts d'un rôle donné, dans l'ordre d'entrée.

    Parcourt tous les rôles de l'utilisateur, ne garde que ceux dont le nom
    correspond à `role_name`, et agrège leurs périmètres sans doublon.
    """
    scopes: list[str] = []
    seen_scopes: set[str] = set()  # pour dédoublonner tout en gardant l'ordre

    if not roles:
        return scopes

    for role in roles:
        # Ignorer les rôles dont le nom ne correspond pas
        if not isinstance(role, str) or role.split(":", 1)[0] != role_name:
            continue

        # Ajouter chaque périmètre non encore vu
        for scope in parse_role_scopes(role):
            if scope not in seen_scopes:
                seen_scopes.add(scope)
                scopes.append(scope)

    return scopes


def get_allowed_campuses(roles: list[str]) -> list[str]:
    """Renvoie les campus gérés par un campus_manager (ses périmètres)."""
    return get_role_scopes(roles, "campus_manager")


def get_program_codes_for_campuses(
    session: Session, campuses: list[str]
) -> list[str]:
    """Résout tous les codes de filières appartenant aux campus fournis."""
    if not campuses:
        return []

    # Toutes les filières dont le campus est dans la liste
    return list(
        session.exec(
            select(Program.code)
            .where(Program.campus.in_(campuses))
            .order_by(Program.code)
        ).all()
    )


def get_campus_manager_program_codes(
    session: Session, roles: list[str]
) -> list[str]:
    """Résout les filières accessibles via les rôles campus_manager.

    Un campus_manager gère des campus ; on convertit ces campus en la liste
    des filières qui y sont rattachées.
    """
    return get_program_codes_for_campuses(session, get_allowed_campuses(roles))


def get_results_program_codes(
    session: Session, roles: list[str]
) -> list[str]:
    """Résout les filières dont les résultats sont consultables/exportables.

    Combine les filières des rôles program_manager (accès direct) et celles
    déduites des rôles campus_manager, en dédoublonnant (dict.fromkeys garde
    l'ordre).
    """
    program_codes = get_role_scopes(roles, "program_manager")
    program_codes.extend(get_campus_manager_program_codes(session, roles))
    return list(dict.fromkeys(program_codes))


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
    return parse_role_scopes(role)


# └────────────────────────────────────────────────────────────────────────┘



# └────────────────────────────────────────────────────────────────────────┘


# ┌─ Modèles Pydantic pour les données entrantes ────────────────────────┐


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


def can_duplicate_survey(roles: list[str], survey_program: str | None) -> bool:
    """Vérifie qu'un RPRM peut dupliquer un sondage de l'une de ses formations."""
    if "admin" in roles: # Admin can duplicate any survey
        return True
    
    program_manager_roles = [
        role for role in roles if role.split(":", 1)[0] == "program_manager"
    ]
    if not program_manager_roles:
        return False

    allowed_programs = {
        program
        for role in program_manager_roles
        for program in parse_rprm_formations(role)
    }
    return survey_program in allowed_programs


def role_to_dashboard_slug(roles: List[str]) -> str:
    """
    Convertit le rôle stocké en BDD en slug de route dashboard.

    "admin"              → "admin"
    "program_manager"              → "program-manager"
    "program_manager:MDE_P2027"    → "program-manager"
    "campus_manager:Paris"         → "campus-manager"
    "facilitator:MDE_P2027"        → "facilitator"
    "student" (ou autre) → "student"
    """
    role_names = {role.split(":", 1)[0] for role in roles}
    if "admin" in role_names:
        return "admin"
    if "campus_manager" in role_names:
        return "campus-manager"
    if "program_manager" in role_names:
        return "program-manager"
    if "facilitator" in role_names:
        return "facilitator"
    return "student"


def get_student_dashboard_redirect(roles: list[str]) -> str | None:
    """Redirige les rôles métier hors de la vue étudiant, sauf les admins."""
    role_names = {role.split(":", 1)[0] for role in roles}
    if "admin" in role_names:
        return None
    if "campus_manager" in role_names:
        return "/dashboard/campus-manager"
    if "program_manager" in role_names:
        return "/dashboard/program-manager"
    if "facilitator" in role_names:
        return "/dashboard/facilitator"
    return None


def _check_sondage_access_and_status(
    session: Session,
    survey_id: int,
    roles: list[str],
    allowed_programs: list[str],
):
    """Helper : vérifie l'accès à un sondage et calcule ses compteurs.

    Renvoie un tuple (survey, message_erreur, nb_convies, nb_repondants).
    En cas d'erreur, survey vaut None et le 2e élément décrit l'erreur.
    """
    # 1. Charger le sondage ; introuvable → erreur 409
    survey = session.exec(
        select(Survey).where(Survey.survey_id == survey_id)
    ).first()
    if not survey:
        return (
            None,
            {"error": "Survey introuvable.", "status_code": 409},
            None,
            None,
        )

    # 2. Vérifier le périmètre : un non-admin ne peut accéder qu'à ses filières
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

    # 3. Compter le nombre total d'étudiants conviés au sondage
    respondents_count = (
        session.exec(
            select(func.count(Respondent.user_id)).where(
                Respondent.survey_id == survey_id,
            )
        ).first()
        or 0
    )
    # 4. Compter ceux qui ont réellement répondu (submission_date renseignée)
    answers_count = (
        session.exec(
            select(func.count(Respondent.user_id)).where(
                Respondent.survey_id == survey_id,
                Respondent.submission_date
                != None,  # submission_date NON NULL = a répondu
            )
        ).first()
        or 0
    )

    warning_msg = None

    return survey, warning_msg, respondents_count, answers_count
