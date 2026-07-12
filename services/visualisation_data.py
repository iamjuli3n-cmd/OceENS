from typing import Dict, Any
import unicodedata

from collections import defaultdict
from database import engine
from sqlmodel import Session, select, func
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

    histo=defaultdict(int)

    for record in records:
        if not _is_satisfaction_record(record):
            continue
        histo[record['value']]+=1

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

    if records and len(records)>0 and "question" in records[0].keys():
        question = records[0]["question"]
    else:
        question = ""
    if total == 0:
        return {
            "question": question,
            "score": None,
            "histo":None,
            "positive_count": 0,
            "total_count": 0,
            
        }

    return {
        "question": records[0]["question"] or "",
        "score": round((positive / total) * 100),
        "histo":histo,
        "positive_count": positive,
        "total_count": total,
        
        
    }


def _score_for_campus(records: list[dict]) -> dict:
    filtered = []

    for record in records:
        text = _record_text(record)

        if record["category"]== "Campus" and record["question_type"] == "QCU_Satisfaction":
            filtered.append(record)

    return _score_from_records(filtered)


def _score_for_formation(records: list[dict]) -> dict:
    filtered = []

    for record in records:
        text = _record_text(record)

        if record["category"]== "Formation" and record["question_type"] == "QCU_Satisfaction":
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

        if record["question_type"] != "QCU_Satisfaction":
            continue

        if record_teacher == teacher_name:
            filtered.append(record)

    return _score_from_records(filtered)


# ─────────────────────────────────────────────
# Context principal
# ─────────────────────────────────────────────


def _build_records_from_db(
    survey: Survey,
    program: Program | None,
    sections: list[Section],
    questions: list[Question],
    modules: list[Module],
    answers: list[Answer],
) -> list[dict]:
    sections_by_id = {section.section_id: section for section in sections}

    questions_by_key = {
        (question.section_id, question.question_id): question for question in questions
    }

    modules_by_id = {module.module_id: module for module in modules}

    records = []

    for answer in answers:
        section = sections_by_id.get(answer.section_id)
        question = questions_by_key.get((answer.section_id, answer.question_id))
        module = modules_by_id.get(answer.module_id)

        records.append(
            {
                "campus": survey.campus,
                "program": survey.program,
                "program_name": program.name if program else survey.program,
                "semester": survey.semester,
                "school_year": survey.school_year,
                "section": section.name if section else "",
                "question_id": answer.question_id,
                "question": question.text if question else "",
                "question_type": question.question_type if question else "",
                "category": question.category if question else "",
                "answer_id": answer.answer_id,
                "submission_id": answer.submission_id,
                "value": answer.value,
                "module_id": answer.module_id,
                "module": module.name if module else "",
                "ue": module.ue if module else "",
                "teacher": answer.teacher or (module.teacher if module else ""),
            }
        )

    return records


def get_visualisation_context(survey_id: int) -> Dict[str, Any]:
    with Session(engine) as session:
        survey = session.exec(
            select(Survey).where(Survey.survey_id == survey_id)
        ).first()

        if not survey:
            return {
                "survey": None,
                "program_name": "",
                "respondents_count": 0,
                "answers_count": 0,
                "warning_msg": "Survey introuvable.",
                "viz_data": {
                    "filters": {"ues": [], "modules": []},
                    "modules": [],
                    "summary_items": [],
                    "recommendation": {"question":"", "score": None, "histo":None, "count": 0, "question": ""},
                    "records": [],
                },
            }

        program = session.exec(
            select(Program).where(Program.code == survey.program)
        ).first()

        sections = session.exec(
            select(Section)
            .where(Section.template_id == survey.template_id)
            .order_by(Section.order)
        ).all()

        questions = session.exec(
            select(Question).where(Question.template_id == survey.template_id)
        ).all()

        modules_db = session.exec(
            select(Module)
            .where(Module.survey_id == survey_id)
            .order_by(Module.ue, Module.name)
        ).all()

        answers = session.exec(
            select(Answer).where(Answer.survey_id == survey_id)
        ).all()

        respondents_count = (
            session.exec(
                select(func.count(Respondent.user_id)).where(
                    Respondent.survey_id == survey_id
                )
            ).first()
            or 0
        )

        answers_count = (
            session.exec(
                select(func.count(Respondent.user_id)).where(
                    Respondent.survey_id == survey_id,
                    Respondent.submission_date != None,
                )
            ).first()
            or 0
        )

    records = _build_records_from_db(
        survey=survey,
        program=program,
        sections=sections,
        questions=questions,
        modules=modules_db,
        answers=answers,
    )

    campus = survey.campus or ""
    program_name = program.name if program else survey.program
    recommendation = _get_recommendation_score(records)

    modules = []

    for module in modules_db:
        modules.append(
            {
                "id": module.module_id,
                "name": module.name or "Module sans nom",
                "ue": module.ue or "",
                "teachers": _split_teachers(module.teacher),
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
            "histo":campus_score["histo"],
            "question":campus_score["question"].replace("[CAMPUS]",campus),
            "score_label": "",
        },
        {
            "rank": 2,
            "type": "formation",
            "title": "Formation",
            "subtitle": program_name,
            "ue": None,
            "teachers": [],
            "score": formation_score["score"],
            "positive_count": formation_score["positive_count"],
            "total_count": formation_score["total_count"],
            "histo":formation_score["histo"],
            "question":formation_score["question"].replace("[CAMPUS]",campus).replace("[FORMATION]",program_name),
            "score_label": "",
        },
    ]

    for index, module in enumerate(modules, start=3):
        teacher_scores = []

        for teacher in module["teachers"]:
            teacher_score = _score_for_module_teacher(records, module, teacher)


            print(module)

            teacher_scores.append(
                {
                    "name": teacher,
                    "score": teacher_score["score"]
                    if teacher_score["score"] is not None
                    else 0,
                    "positive_count": teacher_score["positive_count"],
                    "total_count": teacher_score["total_count"],
                    "histo": teacher_score["histo"] if teacher_score["histo"] is not None
                    else {},
                    "question": teacher_score["question"].replace("[ENSEIGNANT]",teacher).replace("[MODULE]",module["name"]),
                    "score_label": "",
                }
            )

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
                    "histo": module_score["histo"],
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

    response_rate = (
        round((answers_count / respondents_count) * 100, 1)
        if respondents_count > 0
        else 0
    )

    warning_msg = (
        f"Taux de réponse : {response_rate}% ({answers_count} sur {respondents_count})"
    )

    return {
        "survey": survey,
        "program_name": program_name,
        "program": {
            "code": survey.program,
            "name": program_name,
        },
        "respondents_count": respondents_count,
        "answers_count": answers_count,
        "warning_msg": warning_msg,
        "viz_data": {
            "filters": {
                "ues": ues,
                "modules": modules,
            },
            "modules": modules,
            "summary_items": summary_items,
            "recommendation": recommendation,
            "records": records,
        },
    }
