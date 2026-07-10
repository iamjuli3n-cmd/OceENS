from typing import Dict, Any
import unicodedata

from database import engine
from sqlmodel import Session,select
from models import (
    Program,
    User,
    Role,
    Template,
    Section,
    Question,
    Option,
    Module,
    Survey,
    Respondent,
    Answer,
)


# ─────────────────────────────────────────────
# Helpers génériques
# ─────────────────────────────────────────────
def _get_record_field(record: dict, *names, default=""):
    for name in names:
        if name in record and record[name] is not None:
            return record[name]
    return default


def _get_attr(obj, *names, default=None):
    for name in names:
        if hasattr(obj, name):
            value = getattr(obj, name)
            if value is not None:
                return value
    return default


def _split_teachers(value: str) -> list[str]:
    if not value:
        return []

    return [teacher.strip() for teacher in str(value).split(",") if teacher.strip()]


def _normalize(value) -> str:
    value = str(value or "").strip().lower()
    value = unicodedata.normalize("NFD", value)
    value = "".join(c for c in value if unicodedata.category(c) != "Mn")
    value = value.replace("’", "'")
    value = " ".join(value.split())
    return value


# ─────────────────────────────────────────────
# Score satisfaction : ""
# ─────────────────────────────────────────────
POSITIVE_SATISFACTION = {
    "totalement satisfait",
    "totally satisfied",
    "tres satisfait",
    "very satisfied",
    "plutot satisfait",
    "somewhat satisfied",
}

ALL_SATISFACTION = POSITIVE_SATISFACTION | {
    "plutot pas satisfait",
    "somewhat dissatisfied",
    "pas du tout satisfait",
    "not at all satisfied",
    "totalement insatisfait",
    "totally dissatisfied",
}


def _answer_labels(value) -> list[str]:
    return [_normalize(part) for part in str(value or "").split("/") if part.strip()]


def _is_satisfaction_answer(value) -> bool:
    labels = _answer_labels(value)
    return any(label in ALL_SATISFACTION for label in labels)


def _is_positive_satisfaction(value) -> bool:
    labels = _answer_labels(value)
    return any(label in POSITIVE_SATISFACTION for label in labels)


def _is_satisfaction_record(record: dict) -> bool:
    question_type = _normalize(
        _get_record_field(record, "question_type", "Type_Question")
    )

    value = _get_record_field(
        record,
        "value",
        "answer_value",
        "Valeur_Reponse",
        "Valeur",
    )

    return "satisfaction" in question_type or _is_satisfaction_answer(value)


def _record_text(record: dict) -> str:
    return _normalize(
        " ".join(
            [
                str(_get_record_field(record, "section", "Section")),
                str(_get_record_field(record, "category", "Categorie")),
                str(_get_record_field(record, "question", "Question")),
            ]
        )
    )


def _record_module_id(record: dict):
    return _get_record_field(
        record,
        "module_id",
        "Module_ID",
        "Id_Module",
        default=None,
    )


def _record_module_name(record: dict) -> str:
    return str(
        _get_record_field(
            record,
            "module",
            "Module",
            "module_name",
            default="",
        )
    )


def _record_has_module(record: dict) -> bool:
    return bool(_record_module_id(record) or _record_module_name(record))


def _score_from_records(records: list[dict]) -> dict:
    total = 0
    positive = 0

    for record in records:
        if not _is_satisfaction_record(record):
            continue

        value = _get_record_field(
            record,
            "value",
            "answer_value",
            "Valeur_Reponse",
            "Valeur",
        )

        if not _is_satisfaction_answer(value):
            continue

        total += 1

        if _is_positive_satisfaction(value):
            positive += 1

    if total == 0:
        return {
            "score": None,
            "positive_count": 0,
            "total_count": 0,
        }

    return {
        "score": round((positive / total) * 100),
        "positive_count": positive,
        "total_count": total,
    }


def _score_for_campus(records: list[dict]) -> dict:
    filtered = []

    for record in records:
        text = _record_text(record)

        if _record_has_module(record):
            continue

        if "campus" in text:
            filtered.append(record)

    return _score_from_records(filtered)


def _score_for_formation(records: list[dict]) -> dict:
    filtered = []

    for record in records:
        text = _record_text(record)

        if _record_has_module(record):
            continue

        if "formation" in text or "program" in text:
            filtered.append(record)

    return _score_from_records(filtered)


def _score_for_module(records: list[dict], module: dict) -> dict:
    module_id = module.get("id")
    module_name = _normalize(module.get("name"))

    filtered = []

    for record in records:
        record_module_id = _record_module_id(record)
        record_module_name = _normalize(_record_module_name(record))

        if module_id is not None and record_module_id is not None:
            if str(record_module_id) == str(module_id):
                filtered.append(record)
            continue

        if module_name and record_module_name == module_name:
            filtered.append(record)

    return _score_from_records(filtered)


# ─────────────────────────────────────────────
# Score recommandation
# ─────────────────────────────────────────────
def _to_score_1_10(value):
    try:
        score = float(str(value).replace(",", ".").strip())
    except (TypeError, ValueError):
        return None

    if 1 <= score <= 10:
        return score

    return None


def _is_recommendation_record(record: dict) -> bool:
    question_type = _normalize(
        _get_record_field(record, "question_type", "Type_Question")
    )

    section = _normalize(
        _get_record_field(record, "section", "Section", "category", "Categorie")
    )

    question = _normalize(_get_record_field(record, "question", "Question"))

    text = f"{question_type} {section} {question}"

    return "nps" in text or "recommand" in text or "recommend" in text


def _get_recommendation_score(records: list[dict]) -> dict:
    recommendation_candidates = []

    for record in records:
        if not _is_recommendation_record(record):
            continue

        value = _get_record_field(
            record,
            "value",
            "answer_value",
            "Valeur_Reponse",
            "Valeur",
        )

        score = _to_score_1_10(value)

        if score is None:
            continue

        question_id = _get_record_field(
            record,
            "question_id",
            "Question_ID",
            default=0,
        )

        recommendation_candidates.append(
            {
                "question_id": int(question_id or 0),
                "score": score,
                "question": _get_record_field(record, "question", "Question"),
            }
        )

    if not recommendation_candidates:
        return {
            "score": None,
            "count": 0,
            "question": "",
        }

    last_question_id = max(item["question_id"] for item in recommendation_candidates)

    last_question_scores = [
        item
        for item in recommendation_candidates
        if item["question_id"] == last_question_id
    ]

    return {
        "score": round(
            sum(item["score"] for item in last_question_scores)
            / len(last_question_scores),
            1,
        ),
        "count": len(last_question_scores),
        "question": last_question_scores[0]["question"],
    }


def _record_teacher(record: dict) -> str:
    return str(
        _get_record_field(
            record,
            "teacher",
            "Enseignant",
            "answer_teacher",
            default="",
        )
    )


def _score_for_module_teacher(records: list[dict], module: dict, teacher: str) -> dict:
    module_id = module.get("id")
    module_name = _normalize(module.get("name"))
    teacher_name = _normalize(teacher)

    filtered = []

    for record in records:
        record_module_id = _record_module_id(record)
        record_module_name = _normalize(_record_module_name(record))
        record_teacher = _normalize(_record_teacher(record))

        # Filtre module
        same_module = False

        if module_id is not None and record_module_id is not None:
            same_module = str(record_module_id) == str(module_id)
        elif module_name and record_module_name == module_name:
            same_module = True

        if not same_module:
            continue

        # Filtre enseignant
        if not teacher_name:
            continue

        if record_teacher == teacher_name:
            filtered.append(record)

    return _score_from_records(filtered)


# ─────────────────────────────────────────────
# Context principal
# ─────────────────────────────────────────────
def get_visualisation_context(
    survey_id:int
) -> Dict[str, Any]:
    
    session = Session(engine)
    
    survey = session.exec(select(Survey).join(Program,Survey.program==Program.code).where(Survey.survey_id==survey_id)).first()
    
    print(survey)

    

    return {"survey":survey,"answers_count":0,"respondents_count": 1,"viz_data":{}}
    



    records = survey_obj.to_flat_dataframe_records()

    campus = survey_obj.campus or ""
    program_code = survey_obj.program or ""
    program = program_name or program_code

    recommendation = _get_recommendation_score(records)

    modules = []

    for module in survey_obj.modules:
        module_id = _get_attr(module, "module_id", "id", default=None)
        module_name = _get_attr(module, "nom", "name", default="Module sans nom")
        ue_name = _get_attr(module, "ue", "UE", default="")
        teacher_raw = _get_attr(module, "teacher", "enseignant", default="")

        modules.append(
            {
                "id": module_id,
                "name": module_name,
                "ue": ue_name,
                "teachers": _split_teachers(teacher_raw),
                "score": None,
                "score_label": "",
            }
        )

    modules = sorted(
        modules,
        key=lambda m: (
            (m["ue"] or "").lower(),
            (m["name"] or "").lower(),
        ),
    )

    ues = sorted({module["ue"] for module in modules if module.get("ue")})

    campus_score = _score_for_campus(records)
    formation_score = _score_for_formation(records)

    summary_items = [
        {
            "rank": 1,
            "type": "campus",
            "title": "Campus",
            "subtitle": campus,
            "ue": None,
            "teachers": [],
            "score": campus_score["score"],
            "positive_count": campus_score["positive_count"],
            "total_count": campus_score["total_count"],
            "score_label": "",
        },
        {
            "rank": 2,
            "type": "formation",
            "title": "Formation",
            "subtitle": program,
            "ue": None,
            "teachers": [],
            "score": formation_score["score"],
            "positive_count": formation_score["positive_count"],
            "total_count": formation_score["total_count"],
            "score_label": "",
        },
    ]

    for index, module in enumerate(modules, start=3):
        teacher_scores = []

        for teacher in module["teachers"]:
            teacher_score = _score_for_module_teacher(records, module, teacher)

            teacher_scores.append(
                {
                    "name": teacher,
                    "score": teacher_score["score"]
                    if teacher_score["score"] is not None
                    else 0,
                    "positive_count": teacher_score["positive_count"],
                    "total_count": teacher_score["total_count"],
                    "score_label": "",
                }
            )

        # Fallback si module sans enseignant
        if not teacher_scores:
            module_score = _score_for_module(records, module)

            teacher_scores.append(
                {
                    "name": "",
                    "score": module_score["score"]
                    if module_score["score"] is not None
                    else 0,
                    "positive_count": module_score["positive_count"],
                    "total_count": module_score["total_count"],
                    "score_label": "",
                }
            )

        module["teacher_scores"] = teacher_scores

        summary_items.append(
            {
                "rank": index,
                "type": "module",
                "title": module["name"],
                "subtitle": "",
                "ue": module["ue"],
                "teachers": module["teachers"],
                "score": None,
                "positive_count": 0,
                "total_count": 0,
                "score_label": "",
                "teacher_scores": teacher_scores,
            }
        )

    return {
        "filters": {
            "ues": ues,
            "modules": modules,
        },
        "modules": modules,
        "summary_items": summary_items,
        "recommendation": recommendation,
        "records": records,
    }
