"""Helpers metier partages : navigation, statistiques, filtres, tri."""

import json
import re
import unicodedata

from typing import Dict, List, Optional
from fastapi.responses import JSONResponse
from sqlmodel import Session, delete, func, select
from models import Answer, Module, Respondent, Stat, StatValue, Submission, Summary, Survey


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
        "role": "campus_manager",
        "slug": "campus-manager",
        "label": "Direction de campus",
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
        if "campus_manager" in role_names:
            available_roles.add("campus_manager")
    else:
        available_roles = role_names & {
            "facilitator",
            "program_manager",
            "campus_manager",
        }

    return [
        {
            "url": f"/dashboard/{dashboard['slug']}",
            "label": dashboard["label"],
        }
        for dashboard in DASHBOARD_NAVIGATION
        if dashboard["role"] in available_roles
        and dashboard["slug"] != current_dashboard
    ]


def build_survey_prefill(survey: Survey, modules: list[Module]) -> dict:
    """Construit les données éditables du formulaire depuis un sondage existant."""
    ues_by_name: Dict[str, dict] = {}
    next_module_id = 1

    for module in modules:
        ue_name = module.ue or "Sans UE"
        if ue_name not in ues_by_name:
            ues_by_name[ue_name] = {
                "id": len(ues_by_name) + 1,
                "name": ue_name,
                "_open": True,
                "modules": [],
            }

        teachers = [
            teacher.strip()
            for teacher in (module.teacher or "").split(",")
            if teacher.strip()
        ]
        ues_by_name[ue_name]["modules"].append(
            {
                "id": next_module_id,
                "name": module.name or "Module",
                "one_teacher_in_list": bool(module.one_teacher_in_list),
                "teachers": teachers,
            }
        )
        next_module_id += 1

    return {
        "source_survey_id": survey.survey_id,
        "template_id": survey.template_id,
        "program": survey.program,
        "semester": survey.semester,
        "school_year": survey.school_year,
        "ues": list(ues_by_name.values()),
    }


def delete_survey_with_relations(session: Session, survey_id: int) -> None:
    """Supprime les données propres au sondage sans supprimer son modèle partagé."""
    submission_ids = select(Submission.submission_id).where(
        Submission.survey_id == survey_id
    )

    # Les réponses référencent les soumissions et les modules : elles doivent
    # donc être supprimées avant ces deux tables.
    try:
        session.exec(delete(Answer).where(Answer.submission_id.in_(submission_ids)))
        session.exec(delete(Respondent).where(Respondent.survey_id == survey_id))
        session.exec(delete(Summary).where(Summary.survey_id == survey_id))
        session.exec(delete(Module).where(Module.survey_id == survey_id))
        session.exec(delete(Submission).where(Submission.survey_id == survey_id))
        session.exec(delete(Survey).where(Survey.survey_id == survey_id))
        session.commit()

    except Exception as e:
            session.rollback()
            return JSONResponse(
                content={"error": "Impossible de retirer ce sondage. ({e})"},
                status_code=500,
            )


def _get_color(color_scale:dict,score:float):
    """Renvoie la couleur associée à un score selon une échelle de seuils.

    color_scale mappe un seuil (max) → couleur. On renvoie la couleur du
    premier seuil que le score ne dépasse pas. None si aucun seuil ne convient.
    """
    color = None
    for threshold in color_scale:
        if (score <= float(threshold)):
            return color_scale[threshold]

    return color


def get_stats_by_survey(session: Session, surveys: List) -> Dict[int, Dict]:
    """Renvoie les stats calculées par sondage (uniquement les sondages fermés).

    Les sondages ouverts n'ont pas encore de StatValue ; on les ignore. Pour
    chaque sondage fermé, on joint StatValue à Stat pour enrichir chaque valeur
    de ses métadonnées d'affichage (couleur, libellé, suffixe...).
    """
    if not surveys:
        return {}
    
    stats_by_survey={}
    
    for survey in surveys:
        if survey["is_closed"]: #Not open
            stats_by_survey[survey["survey_id"]] = {sv[0].name:{'value':sv[0].value,'color':_get_color(json.loads(sv[1].color_scale),sv[0].value),'short':sv[1].short,'label':sv[1].label,'suffix':sv[1].suffix,'show_explicit_positive':sv[1].show_explicit_positive} for sv in session.exec(select(StatValue,Stat).join(Stat,Stat.name==StatValue.name).where(StatValue.survey_id==survey["survey_id"])).all()}
    return stats_by_survey


def get_avg_stats(session: Session, surveys: List) -> Dict[str, Dict]:
    """Moyenne, pour chaque stat existante, sa valeur sur les sondages fermés
    parmi ceux fournis (mêmes sondages que get_stats_by_survey : les sondages
    ouverts n'ont pas encore de StatValue)."""
    closed_survey_ids = [s["survey_id"] for s in surveys if s["is_closed"]]
    if not closed_survey_ids:
        return {}

    rows = session.exec(
        select(Stat, func.avg(StatValue.value), func.count(StatValue.value))
        .join(StatValue, Stat.name == StatValue.name)
        .where(StatValue.survey_id.in_(closed_survey_ids))
        .group_by(Stat.name)
    ).all()

    avg_stats = {}
    for stat, avg_value, count in rows:
        if avg_value is None or not count:
            continue
        avg_stats[stat.name] = {
            "value": avg_value,
            "color": _get_color(json.loads(stat.color_scale), avg_value),
            "short": stat.short,
            "label": stat.label,
            "suffix": stat.suffix,
            "show_explicit_positive": stat.show_explicit_positive,
            "surveys_count": count,
        }
    return avg_stats


def filter_surveys(
    surveys: List[dict],
    school_year: Optional[str],
    semester: Optional[str],
    program: Optional[str] = None,
) -> List[dict]:
    """Filtre une liste de sondages déjà scopée par rôle, sur année scolaire,
    semestre et/ou formation (valeur vide = pas de filtre sur ce champ)."""
    filtered = surveys
    if school_year:
        filtered = [s for s in filtered if s["school_year"] == school_year]
    if semester:
        filtered = [s for s in filtered if s["semester"] == semester]
    if program:
        filtered = [s for s in filtered if s["program"] == program]
    return filtered


def parse_name(full_name: Optional[str], fallback_id: int) -> Dict[str, Optional[str]]:
    """Découpe un nom complet en prénom / nom.

    Le premier mot est le prénom, le reste le nom. Renvoie un dict avec un id
    de repli si le nom est vide.
    """
    if not full_name:
        return {"id": fallback_id, "firstname": None, "name": None}
    parts = full_name.strip().split()
    if len(parts) == 1:
        return {"id": fallback_id, "firstname": parts[0], "name": ""}
    return {"id": fallback_id, "firstname": parts[0], "name": " ".join(parts[1:])}


def teacher_sort_key(name: str) -> str:
    """Clé de tri d'un nom d'enseignant, insensible à la casse et aux accents.

    Normalise en retirant les accents (NFD + suppression des diacritiques) et
    en compactant les espaces, pour trier "Éric" et "eric" au même endroit.
    """
    normalized = unicodedata.normalize("NFD", name.casefold())
    without_accents = "".join(
        char for char in normalized if unicodedata.category(char) != "Mn"
    )
    return re.sub(r"\s+", " ", without_accents).strip()


# ┌─ Gestion du cycle de vie (lifespan) ──────────────────────────────────┐
