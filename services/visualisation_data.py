from collections import OrderedDict, defaultdict
from typing import Any, Dict, Optional
import unicodedata
import json

from sqlalchemy.orm import aliased
from sqlmodel import Session, func, select

from database import engine
from models import (
    Answer,
    Module,
    Option,
    Program,
    Question,
    Respondent,
    Section,
    Submission,
    Survey,
)


def _normalize(value: Any) -> str:
    value = str(value or "").strip().lower()
    value = unicodedata.normalize("NFD", value)
    return "".join(char for char in value if unicodedata.category(char) != "Mn")


def _count_labels(question_type: str) -> dict[str, str]:
    """Return wording matching what is actually counted by a chart."""

    if _normalize(question_type) == "qcm_insatisfaction":
        return {
            "count_label": "choix sélectionné(s)",
            "series_name": "Choix sélectionnés",
            "axis_title": "Nombre de choix sélectionnés",
            "allow_pie": False,
        }
    return {
        "count_label": "réponse(s)",
        "series_name": "Réponses",
        "axis_title": "Nombre de réponses",
        "allow_pie": True,
    }


def bilingual_text(text_fr: Optional[str], text_en: Optional[str]) -> str:
    """Build the bilingual label displayed by the survey UI."""
    # parts = [text.strip() for text in (text_fr, text_en) if text and text.strip()]
    # return " / ".join(dict.fromkeys(parts))
    return (
        f'<text class="text_fr">{text_fr}</text> <text class="text_en">{text_en}</text>'
    )


def _split_teachers(value: Optional[str]) -> list[str]:
    return [
        teacher.strip() for teacher in str(value or "").split(",") if teacher.strip()
    ]


def _replace_placeholders(text: str, record: dict) -> str:
    return (
        (text or "")
        .replace("[CAMPUS]", record.get("campus") or "")
        .replace(
            "[FORMATION]", record.get("program_name") or record.get("program") or ""
        )
        .replace("[MODULE]", record.get("module") or "")
        .replace("[ENSEIGNANT]", record.get("teacher") or "")
    )


def _nps_options() -> list[dict[str, Any]]:
    """Return a fresh 1-to-10 option catalog for NPS questions."""

    return [
        {
            "option_id": f"nps:{score}",
            "text_fr": str(score),
            "text_en": str(score),
            "label": str(score),
            "is_positive": None,
        }
        for score in range(1, 11)
    ]


def _make_chart_item(
    label: str,
    *,
    text_fr: str = "",
    text_en: str = "",
    is_positive: Optional[bool] = None,
    count: int = 0,
) -> dict[str, Any]:
    """Build the common representation consumed by every answer chart."""

    return {
        "label": label,
        "text_fr": text_fr or label,
        "text_en": text_en,
        "is_positive": is_positive,
        "count": count,
    }


def _to_score_1_10(value: Any) -> Optional[float]:
    try:
        score = float(str(value).replace(",", ".").strip())
    except (TypeError, ValueError):
        return None
    return score if 1 <= score <= 10 else None


def _build_question(dic, data_row, options, options_value, submissions_sets):
    if (data_row["question_id"] not in dic["questions"].keys()):
        dic["questions"][data_row["question_id"]] = {
            "text": bilingual_text(data_row["question_text_fr"],data_row["question_text_en"],),
            "question_type": data_row["question_type"],
            "question_submissions_count":0,
            "is_positive": [],
            "histo": {
                o: 0 for o in options[data_row["question_id"]]
            }  # If the question as dedicated options, init the histo with them
            if data_row["question_id"] in options.keys()
            else defaultdict(int),
        }

    if data_row["module_name"] not in submissions_sets:
        submissions_sets[data_row["module_name"]]={}
    if data_row["teacher"] not in submissions_sets[data_row["module_name"]]:
        submissions_sets[data_row["module_name"]][data_row["teacher"]] = defaultdict(set)
    if data_row["submission_id"] not in submissions_sets[data_row["module_name"]][data_row["teacher"]][data_row["question_id"]]: # Memorizing submissions_set
        submissions_sets[data_row["module_name"]][data_row["teacher"]][data_row["question_id"]].add(data_row["submission_id"])
        dic["questions"][data_row["question_id"]]["question_submissions_count"]+=1 # Counting submissions
    if (data_row['question_type']=='QCU_Satisfaction'): # SATIFACTION COUNT
        if "satisfaction_count" not in dic.keys():
            dic["satisfaction_count"]=0
        if options_value[data_row["option_id"]]["is_positive"]: # Count the positive
            dic["satisfaction_count"]+=1
    if data_row["question_type"] == "NPS":
        recommendation_score = _to_score_1_10(data_row["answer_value"])
        if recommendation_score is not None:
            dic["recommendation_sum"] = dic.get("recommendation_sum", 0) + recommendation_score
            dic["recommendation_count"] = dic.get("recommendation_count", 0) + 1
    if (data_row['question_type']=='QCU_Attendance'): # ATTENDANCE COUNT
        if "attendance_count" not in dic.keys():
            dic["attendance_count"]=0
        if options_value[data_row["option_id"]]["text"] == 'Oui': # Count the Yes
            dic["attendance_count"]+=1
    if data_row["option_id"]:
        dic["questions"][data_row["question_id"]]["histo"][options_value[data_row["option_id"]]["text"]] += 1  # Counting the number of appearance of each value
        if (options_value[data_row["option_id"]]["is_positive"] 
        and options_value[data_row["option_id"]]["text"] not in dic["questions"][data_row["question_id"]]["is_positive"]):
            dic["questions"][data_row["question_id"]]["is_positive"].append(options_value[data_row["option_id"]]["text"])  # Conversion from option_id to text_fr
    else:
        dic["questions"][data_row["question_id"]]["histo"][data_row["answer_value"]] += 1  # Counting the number of appearance of each value


def get_visualisation_context2(survey_id: int) -> Optional[Dict[str, Any]]:
    context = {}
    with Session(engine) as session:

        # FETCH SURVEY AND PROGRAM
        survey_row = session.exec(
            select(Survey, Program)
            .join(Program, Program.code == Survey.program, isouter=True)
            .where(Survey.survey_id == survey_id)
        ).first()
        if not survey_row:
            return None

        survey, program = survey_row
        context["survey"] = {
            "survey_id": survey.survey_id,
            "template_id": survey.template_id,
            "program": survey.program,
            "campus": program.campus if program else "",
            "semester": survey.semester,
            "school_year": survey.school_year,
            "status": survey.status,
        }
        context["program"] = {
            "code": survey.program,
            "name": program.name if program else survey.program,
            "campus": program.campus if program else "",
        }

        respondent_row = session.exec(
            select(
                func.count(Respondent.user_id),
                func.count(Respondent.submission_date),
            ).where(Respondent.survey_id == survey_id)
        ).first()
        context["respondents_count"] = int(respondent_row[0] or 0) if respondent_row else 0
        context["answers_count"] = int(respondent_row[1] or 0) if respondent_row else 0
        context["submissions_count"] = int(
            session.exec(
                select(func.count(Submission.submission_id)).where(
                    Submission.survey_id == survey_id
                )
            ).one()
            or 0
        )

        # END SURVEY AND PROGRAM

        # FETCH ANSWERS

        data={}

        # Fetch default options for each question_id
        options = {
            o[0]: json.loads(o[1])
            for o in session.exec(
                select(Option.question_id, func.json_group_array(Option.text_fr))
                .order_by(Option.option_id)
                .group_by(Option.question_id)
            ).all()
        }

        print(options)

        options_value = {
            o.option_id: {"text":o.text_fr,"is_positive":o.is_positive} for o in session.exec(select(Option)).all()
        }

        # Memorize submissions_set
        submissions_sets=defaultdict()

        rows = session.exec(
            select(
                Answer.answer_id,
                Answer.submission_id,
                Answer.question_id,
                Answer.module_id,
                Answer.teacher,
                Answer.option_id,
                Answer.value.label("answer_value"),
                Section.section_id,
                Section.name.label("section_name"),
                Section.order.label("section_order"),
                Section.section_type,
                Question.question_type,
                Question.text_fr.label("question_text_fr"),
                Question.text_en.label("question_text_en"),
                Module.ue,
                Module.name.label("module_name"),
            )
            .join(Submission, Submission.submission_id == Answer.submission_id)
            .join(Survey, Survey.survey_id == Submission.survey_id)
            .join(Program, Program.code == Survey.program, isouter=True)
            .join(Question, Question.question_id == Answer.question_id)
            .join(Section, Section.section_id == Question.section_id)
            .join(Module, Module.module_id == Answer.module_id, isouter=True)
            .where(Survey.survey_id == survey_id)
            .order_by(
                Section.order,
                Module.ue,
                Module.name,
                Answer.teacher,
                Question.question_id,
                Answer.option_id,
            )
        ).all()

        for r in rows:
            data_row = {
                "answer_id": r[0],
                "submission_id": r[1],
                "question_id": r[2],
                "module_id": r[3],
                "teacher": r[4],
                "option_id": r[5],
                "answer_value": r[6],
                "section_id": r[7],
                "section_name": r[8],
                "section_order": r[9],
                "section_type": r[10],
                "question_type": r[11],
                "question_text_fr": r[12],
                "question_text_en": r[13],
                "ue": r[14],
                "module_name": r[15],
            }
            if data_row["section_name"] not in data.keys():
                data[data_row["section_name"]] = {}
            data[data_row["section_name"]]["section_type"] = data_row["section_type"]
            if data_row["section_type"] == "ME":
                if "modules" not in data[data_row["section_name"]].keys():
                    data[data_row["section_name"]]["modules"] = {}
                if (
                    data_row["module_name"]
                    not in data[data_row["section_name"]]["modules"].keys()
                ):
                    data[data_row["section_name"]]["modules"][
                        data_row["module_name"]
                    ] = {"ue": data_row["ue"], "teachers":{}}
                if data_row["teacher"]:
                    if (
                        data_row["teacher"]
                        not in data[data_row["section_name"]]["modules"][
                            data_row["module_name"]
                        ]["teachers"].keys()
                    ):
                        data[data_row["section_name"]]["modules"][
                            data_row["module_name"]
                        ]["teachers"][data_row["teacher"]] = {"questions": {}}
                    _build_question(data[data_row["section_name"]]["modules"][
                            data_row["module_name"]
                        ]["teachers"][data_row["teacher"]], data_row, options, options_value, submissions_sets)
            elif data_row["section_type"] == "R":
                
                if "recommendation_sum" not in data[data_row["section_name"]]:
                    data[data_row["section_name"]]["recommendation_sum"] = 0
                    data[data_row["section_name"]]["submission_count"] = 0
                data[data_row["section_name"]]["recommendation_sum"]+=float(data_row["answer_value"])
                data[data_row["section_name"]]["submission_count"]+=1

            else: # section_type = S --> Simple
                if "questions" not in data[data_row["section_name"]]:
                    data[data_row["section_name"]] = {"questions": {}}
                _build_question(data[data_row["section_name"]], data_row, options, options_value, submissions_sets)


    context["sections"] = data
    # END ANSWERS   
       
    #print(data)
    return context


def get_answers_details(survey_id: int) -> Optional[Dict[str, Any]]:
    """Load every datum needed by the visualisation in one service call.

    The answer query is deliberately bulk-oriented: it loads selected options and
    every possible option for each answered question at once. This removes the old
    query-per-answer behaviour and lets chart categories be generated from data.
    """
    selected_option = aliased(Option, name="selected_option")

    with Session(engine) as session:
        survey_row = session.exec(
            select(Survey, Program)
            .join(Program, Program.code == Survey.program, isouter=True)
            .where(Survey.survey_id == survey_id)
        ).first()
        if not survey_row:
            return None

        survey, program = survey_row
        survey_data = {
            "survey_id": survey.survey_id,
            "template_id": survey.template_id,
            "program": survey.program,
            "campus": program.campus if program else "",
            "semester": survey.semester,
            "school_year": survey.school_year,
            "status": survey.status,
        }
        program_data = {
            "code": survey.program,
            "name": program.name if program else survey.program,
            "campus": program.campus if program else "",
        }

        respondent_counts = session.exec(
            select(
                func.count(Respondent.user_id),
                func.count(Respondent.submission_date),
            ).where(Respondent.survey_id == survey_id)
        ).first()
        respondents_count = int(respondent_counts[0] or 0) if respondent_counts else 0
        answers_count = int(respondent_counts[1] or 0) if respondent_counts else 0
        submissions_count = int(
            session.exec(
                select(func.count(Submission.submission_id)).where(
                    Submission.survey_id == survey_id
                )
            ).one()
            or 0
        )

        module_rows = session.exec(
            select(Module)
            .where(Module.survey_id == survey_id)
            .order_by(Module.ue, Module.name, Module.module_id)
        ).all()
        modules = [
            {
                "id": module.module_id,
                "name": module.name or "Module sans nom",
                "ue": module.ue or "",
                "teachers": _split_teachers(module.teacher),
            }
            for module in module_rows
        ]

        catalog_rows = session.exec(
            select(
                Section.section_id,
                Section.name.label("section_name"),
                Section.order.label("section_order"),
                Question.question_id,
                Question.question_type,
                Question.text_fr.label("question_text_fr"),
                Question.text_en.label("question_text_en"),
                Option.option_id,
                Option.text_fr.label("option_text_fr"),
                Option.text_en.label("option_text_en"),
                Option.is_positive,
            )
            .join(Question, Question.section_id == Section.section_id)
            .join(Option, Option.question_id == Question.question_id, isouter=True)
            .where(Section.template_id == survey.template_id)
            .order_by(Section.order, Question.question_id, Option.option_id)
        ).all()

        rows = session.exec(
            select(
                Answer.answer_id,
                Answer.submission_id,
                Answer.question_id,
                Answer.module_id,
                Answer.teacher,
                Answer.option_id,
                Answer.value.label("answer_value"),
                Section.section_id,
                Section.name.label("section_name"),
                Section.order.label("section_order"),
                Question.question_type,
                Question.language,
                Question.text_fr.label("question_text_fr"),
                Question.text_en.label("question_text_en"),
                Module.ue,
                Module.name.label("module_name"),
                selected_option.text_fr.label("selected_text_fr"),
                selected_option.text_en.label("selected_text_en"),
                selected_option.is_positive.label("selected_is_positive"),
            )
            .join(Submission, Submission.submission_id == Answer.submission_id)
            .join(Survey, Survey.survey_id == Submission.survey_id)
            .join(Program, Program.code == Survey.program, isouter=True)
            .join(Question, Question.question_id == Answer.question_id)
            .join(Section, Section.section_id == Question.section_id)
            .join(Module, Module.module_id == Answer.module_id, isouter=True)
            .join(
                selected_option,
                selected_option.option_id == Answer.option_id,
                isouter=True,
            )
            .where(Survey.survey_id == survey_id)
            .order_by(
                Section.order,
                Module.ue,
                Module.name,
                Answer.teacher,
                Question.question_id,
                Answer.answer_id,
            )
        ).all()

    question_catalog_by_id: OrderedDict[int, dict] = OrderedDict()
    section_positions: dict[int, dict[int, int]] = {}
    for row in catalog_rows:
        if row.question_id not in question_catalog_by_id:
            positions = section_positions.setdefault(row.section_id, {})
            positions.setdefault(row.question_id, len(positions) + 1)
            question_catalog_by_id[row.question_id] = {
                "section_id": row.section_id,
                "section_name": row.section_name or "Sans section",
                "section_order": row.section_order or 0,
                "question_id": row.question_id,
                "question_position": positions[row.question_id],
                "question_type": row.question_type or "",
                "question_text_fr": row.question_text_fr or "",
                "question_text_en": row.question_text_en or "",
                "question": bilingual_text(row.question_text_fr, row.question_text_en),
                "options": [],
            }
        if row.option_id:
            question_catalog_by_id[row.question_id]["options"].append(
                {
                    "option_id": row.option_id,
                    "text_fr": row.option_text_fr or "",
                    "text_en": row.option_text_en or "",
                    "label": row.option_text_fr,  # bilingual_text(row.option_text_fr, row.option_text_en),
                    "is_positive": (
                        None if row.is_positive is None else bool(row.is_positive)
                    ),
                }
            )

    for question in question_catalog_by_id.values():
        if _normalize(question["question_type"]) == "nps" and not question["options"]:
            question["options"] = _nps_options()

    records_by_answer: OrderedDict[int, dict] = OrderedDict()
    for row in rows:
        selected_text_fr = row.selected_text_fr or ""
        selected_text_en = row.selected_text_en or ""
        records_by_answer[row.answer_id] = {
            "answer_id": row.answer_id,
            "submission_id": row.submission_id,
            "campus": survey_data["campus"],
            "program": survey_data["program"],
            "program_name": program_data["name"],
            "semester": survey_data["semester"],
            "school_year": survey_data["school_year"],
            "section_id": row.section_id,
            "section_order": row.section_order,
            "category": row.section_name or "Sans section",
            "question_id": row.question_id,
            "question_type": row.question_type or "",
            "language": row.language or "",
            "question_text_fr": row.question_text_fr or "",
            "question_text_en": row.question_text_en or "",
            "question": bilingual_text(row.question_text_fr, row.question_text_en),
            "module_id": row.module_id or None,
            "ue": row.ue or "",
            "module": row.module_name or "",
            "teacher": row.teacher or "",
            "option_id": row.option_id or None,
            "option_text_fr": selected_text_fr,
            "option_text_en": selected_text_en,
            "is_positive": (
                None
                if row.selected_is_positive is None
                else bool(row.selected_is_positive)
            ),
            "answer_value": row.answer_value or "",
            "value": selected_text_fr or selected_text_en or row.answer_value or "",
        }

    records = list(records_by_answer.values())
    for record in records:
        question = question_catalog_by_id.get(record["question_id"], {})
        record["options"] = [dict(option) for option in question.get("options", [])]
        if record["option_id"] is None and record["value"]:
            normalized_value = _normalize(record["value"])
            matching_option = next(
                (
                    option
                    for option in record["options"]
                    if normalized_value
                    in {_normalize(option["text_fr"]), _normalize(option["text_en"])}
                ),
                None,
            )
            if matching_option:
                record.update(
                    {
                        "option_id": matching_option["option_id"],
                        "option_text_fr": matching_option["text_fr"],
                        "option_text_en": matching_option["text_en"],
                        "is_positive": matching_option["is_positive"],
                        "value": matching_option["text_fr"]
                        or matching_option["text_en"],
                    }
                )

    return {
        "survey": survey_data,
        "program": program_data,
        "respondents_count": respondents_count,
        "answers_count": answers_count,
        "submissions_count": submissions_count,
        "modules": modules,
        "questions": list(question_catalog_by_id.values()),
        "records": records,
    }


def _is_satisfaction_record(record: dict) -> bool:
    return _normalize(record.get("question_type")) in {
        "qcu_satisfaction",
        "satisfaction",
    }


def _legacy_positive(value: Any) -> bool:
    normalized = _normalize(value)
    return any(
        label in normalized
        for label in (
            "totalement satisfait",
            "totally satisfied",
            "tres satisfait",
            "very satisfied",
            "plutot satisfait",
            "somewhat satisfied",
        )
    )


def _score_from_records(records: list[dict]) -> dict:
    satisfaction_records = [
        record for record in records if _is_satisfaction_record(record)
    ]
    if not satisfaction_records:
        return {
            "question": "",
            "score": None,
            "histo": {},
            "chart": [],
            "positive_count": 0,
            "total_count": 0,
        }

    chart_by_key: OrderedDict[Any, dict] = OrderedDict()
    for record in satisfaction_records:
        for option in record.get("options", []):
            chart_by_key.setdefault(
                option["option_id"],
                _make_chart_item(
                    option["label"],
                    text_fr=option["text_fr"],
                    text_en=option["text_en"],
                    is_positive=option["is_positive"],
                ),
            )

    positive_count = 0
    histo: OrderedDict[str, int] = OrderedDict()
    for record in satisfaction_records:
        key: Any = record.get("option_id")
        label = record.get(
            "option_text_fr"
        )  # bilingual_text(record.get("option_text_fr"), record.get("option_text_en"))
        label = label or str(record.get("value") or "Sans réponse")
        if key is None:
            key = f"value:{label}"
        chart_by_key.setdefault(
            key,
            _make_chart_item(
                label,
                text_fr=record.get("option_text_fr") or label,
                text_en=record.get("option_text_en") or "",
                is_positive=record.get("is_positive"),
            ),
        )
        chart_by_key[key]["count"] += 1
        histo[label] = histo.get(label, 0) + 1

        is_positive = record.get("is_positive")
        if is_positive is True or (
            is_positive is None and _legacy_positive(record.get("value"))
        ):
            positive_count += 1

    question = _replace_placeholders(
        satisfaction_records[0].get("question") or "", satisfaction_records[0]
    )
    total_count = len(satisfaction_records)
    return {
        "question": question,
        "score": round(100 * positive_count / total_count),
        "histo": dict(histo),
        "chart": list(chart_by_key.values()),
        "positive_count": positive_count,
        "total_count": total_count,
    }


def _same_module(record: dict, module: dict) -> bool:
    if record.get("module_id") is not None and module.get("id") is not None:
        return str(record["module_id"]) == str(module["id"])
    return _normalize(record.get("module")) == _normalize(module.get("name"))


def _teachers_for_module(records: list[dict], module: dict) -> list[str]:
    """Merge configured and observed teachers while preserving their order."""

    answer_teachers = [
        record.get("teacher") or ""
        for record in records
        if _same_module(record, module) and record.get("teacher")
    ]
    return list(dict.fromkeys([*module.get("teachers", []), *answer_teachers]))


def _build_attendance_data(
    records: list[dict], module: dict, teachers: list[str]
) -> dict[str, Any]:
    """Aggregate distinct students attending a module and each of its teachers."""

    attendance_records = [
        record
        for record in records
        if _same_module(record, module)
        and _normalize(record.get("question_type")) == "qcu_attendance"
        and (
            record.get("is_positive") is True
            or _normalize(record.get("value")) in {"oui", "yes"}
        )
    ]
    attendance_total = len(
        {
            record.get("submission_id") or record.get("answer_id")
            for record in attendance_records
        }
    )
    attendance_chart = []
    for teacher in teachers:
        teacher_count = len(
            {
                record.get("submission_id") or record.get("answer_id")
                for record in attendance_records
                if _normalize(record.get("teacher")) == _normalize(teacher)
            }
        )
        attendance_chart.append(
            _make_chart_item(teacher, text_fr=teacher, count=teacher_count)
        )

    return {
        "total": attendance_total,
        "chart_data": {
            "title": "Étudiants ayant suivi le module par enseignant",
            "items": attendance_chart,
            "mode": "count",
            "count_label": "étudiant(s)",
            "series_name": "Étudiants",
            "axis_title": "Nombre d'étudiants",
        },
    }


def _score_for_section(records: list[dict], section_name: str) -> dict:
    return _score_from_records(
        [
            record
            for record in records
            if _normalize(record.get("category")) == _normalize(section_name)
        ]
    )


def _score_for_module(
    records: list[dict], module: dict, teacher: Optional[str] = None
) -> dict:
    filtered = [record for record in records if _same_module(record, module)]
    if teacher is not None:
        filtered = [
            record
            for record in filtered
            if _normalize(record.get("teacher")) == _normalize(teacher)
        ]
    return _score_from_records(filtered)


def _get_recommendation_score(records: list[dict]) -> dict:
    candidates = []
    for record in records:
        if _normalize(record.get("question_type")) != "nps":
            continue
        score = _to_score_1_10(record.get("value"))
        if score is not None:
            candidates.append((record, score))
    if not candidates:
        return {"score": None, "count": 0, "question": ""}
    return {
        "score": round(sum(score for _, score in candidates) / len(candidates), 1),
        "count": len(candidates),
        "question": _replace_placeholders(
            candidates[0][0]["question"], candidates[0][0]
        ),
    }


def _finalize_detail(detail: dict, chart_index: int, submissions_count: int) -> None:
    """Convert one accumulated detail into the payload expected by the template."""

    detail["chart"] = list(detail["chart"].values())
    detail["respondent_count"] = len(detail.pop("_respondent_ids"))
    detail["chart_id"] = f"answer-detail-{chart_index}"
    detail["chart_data"] = {
        "title": "",
        "items": detail["chart"],
        "mode": "percent",
        "count_label": detail["count_label"],
        "series_name": detail["series_name"],
        "axis_title": detail["axis_title"],
        "percentage_denominator": submissions_count,  # The percentage denominator should be the total submissions count (% of the whole promo that has answered)
        "allow_pie": detail["allow_pie"],
    }


def build_answer_details(
    records: list[dict],
    submissions_count: int,
    questions: Optional[list[dict]] = None,
    modules: Optional[list[dict]] = None,
    survey: Optional[dict] = None,
    program: Optional[dict] = None,
) -> dict:
    """Group every question under the summary row that owns it."""
    sections: OrderedDict[int, dict] = OrderedDict()
    groups: OrderedDict[tuple, dict] = OrderedDict()
    questions = questions or []
    modules = modules or []
    survey = survey or {}
    program = program or {}

    def ensure_detail(record: dict) -> dict:
        section_id = record["section_id"]
        section = sections.setdefault(
            section_id,
            {
                "section_id": section_id,
                "name": record["category"],
                "order": record.get("section_order") or 0,
                "questions": [],
            },
        )
        key = (
            record["question_id"],
            record.get("module_id"),
            record.get("teacher") or "",
        )
        if key in groups:
            return groups[key]

        context = " · ".join(
            value
            for value in (
                record.get("ue") or "",
                record.get("module") or "",
                record.get("teacher") or "",
            )
            if value
        )
        option_chart = OrderedDict(
            (
                option["option_id"],
                _make_chart_item(
                    option["label"],
                    text_fr=option["text_fr"],
                    text_en=option["text_en"],
                    is_positive=option["is_positive"],
                ),
            )
            for option in record.get("options", [])
        )
        detail = {
            "section_id": section_id,
            "question_id": record["question_id"],
            "question_position": record.get("question_position"),
            "question_type": record["question_type"],
            "question": _replace_placeholders(record["question"], record),
            "context": context,
            "module_id": record.get("module_id"),
            "module": record.get("module") or "",
            "ue": record.get("ue") or "",
            "teacher": record.get("teacher") or "",
            "is_open": not bool(record.get("options")),
            "answers": [],
            "chart": option_chart,
            "total_count": 0,
            "_respondent_ids": set(),
            **_count_labels(record["question_type"]),
        }
        groups[key] = detail
        section["questions"].append(detail)
        return detail

    teachers_by_module = {
        module.get("id"): _teachers_for_module(records, module) for module in modules
    }

    for question in questions:
        base_record = {
            "campus": survey.get("campus") or "",
            "program": survey.get("program") or "",
            "program_name": program.get("name") or survey.get("program") or "",
            "section_id": question["section_id"],
            "section_order": question.get("section_order") or 0,
            "category": question["section_name"],
            "question_id": question["question_id"],
            "question_position": question.get("question_position"),
            "question_type": question["question_type"],
            "question": question["question"],
            "options": question.get("options", []),
            "module_id": None,
            "module": "",
            "ue": "",
            "teacher": "",
        }
        section_name = _normalize(question["section_name"])
        is_module_question = "module" in section_name and "enseignant" in section_name
        if not is_module_question:
            ensure_detail(base_record)
            continue

        for module in modules:
            teachers = teachers_by_module.get(module.get("id")) or [""]
            for teacher in teachers:
                ensure_detail(
                    {
                        **base_record,
                        "module_id": module.get("id"),
                        "module": module.get("name") or "",
                        "ue": module.get("ue") or "",
                        "teacher": teacher,
                    }
                )

    question_positions = {
        question["question_id"]: question.get("question_position")
        for question in questions
    }
    for record in records:
        detail = ensure_detail(
            {
                **record,
                "question_position": question_positions.get(record["question_id"]),
            }
        )
        detail["total_count"] += 1
        detail["_respondent_ids"].add(
            record.get("submission_id") or record.get("answer_id")
        )
        if detail["is_open"]:
            if record.get("value"):
                detail["answers"].append(record["value"])
            continue

        option_key: Any = record.get("option_id")
        label = record.get(
            "option_text_fr"
        )  # bilingual_text(record.get("option_text_fr"), record.get("option_text_en"))
        label = label or str(record.get("value") or "Sans réponse")
        if option_key is None:
            option_key = f"value:{label}"
        detail["chart"].setdefault(
            option_key,
            _make_chart_item(
                label,
                text_fr=record.get("option_text_fr") or label,
                text_en=record.get("option_text_en") or "",
                is_positive=record.get("is_positive"),
            ),
        )
        detail["chart"][option_key]["count"] += 1

    chart_index = 0
    for section in sections.values():
        section["questions"].sort(
            key=lambda detail: (
                detail.get("question_position") or detail["question_id"],
                detail.get("module_id") or 0,
                _normalize(detail.get("teacher")),
            )
        )
        for detail in section["questions"]:
            chart_index += 1
            _finalize_detail(detail, chart_index, submissions_count)

    return {"sections": list(sections.values())}


def _chart_data(score: dict) -> dict:
    return {"title": score["question"], "items": score["chart"]}


def get_visualisation_context(survey_id: int) -> Dict[str, Any]:
    details = get_answers_details(survey_id)
    if details is None:
        return {
            "survey": None,
            "program_name": "",
            "program": {"code": "", "name": ""},
            "respondents_count": 0,
            "answers_count": 0,
            "submissions_count": 0,
            "warning_msg": "Survey introuvable.",
            "viz_data": {
                "filters": {"ues": [], "modules": []},
                "modules": [],
                "summary_items": [],
                "recommendation": {"score": None, "count": 0, "question": ""},
                "details": {"sections": []},
                "records": [],
            },
        }

    records = details["records"]
    survey = details["survey"]
    program = details["program"]
    modules = details["modules"]
    answer_details = build_answer_details(
        records,
        details["submissions_count"],
        questions=details["questions"],
        modules=modules,
        survey=survey,
        program=program,
    )
    detail_sections = {
        _normalize(section["name"]): section["questions"]
        for section in answer_details["sections"]
    }

    campus_score = _score_for_section(records, "Campus")
    formation_score = _score_for_section(records, "Formation")
    summary_items = [
        {
            "rank": 1,
            "type": "campus",
            "title": "Campus",
            "subtitle": survey["campus"],
            "ue": None,
            "teachers": [],
            "details": detail_sections.get(_normalize("Campus"), []),
            **campus_score,
            "chart_data": _chart_data(campus_score),
        },
        {
            "rank": 2,
            "type": "formation",
            "title": "Formation",
            "subtitle": program["name"],
            "ue": None,
            "teachers": [],
            "details": detail_sections.get(_normalize("Formation"), []),
            **formation_score,
            "chart_data": _chart_data(formation_score),
        },
    ]

    for rank, module in enumerate(modules, start=3):
        teachers = _teachers_for_module(records, module)
        teacher_scores = []
        if teachers:
            for teacher in teachers:
                score = _score_for_module(records, module, teacher)
                teacher_scores.append(
                    {
                        "name": teacher,
                        **score,
                        "chart_data": _chart_data(score),
                    }
                )
        else:
            score = _score_for_module(records, module)
            teacher_scores.append(
                {"name": "", **score, "chart_data": _chart_data(score)}
            )

        module["teachers"] = teachers
        module["teacher_scores"] = teacher_scores
        module_details = [
            detail
            for section_name, section_details in detail_sections.items()
            if "module" in section_name and "enseignant" in section_name
            for detail in section_details
            if str(detail.get("module_id")) == str(module.get("id"))
        ]
        attendance = _build_attendance_data(records, module, teachers)

        teacher_groups = []
        group_names = teachers or [""]
        for teacher in group_names:
            teacher_groups.append(
                {
                    "name": teacher,
                    "questions": [
                        detail
                        for detail in module_details
                        if _normalize(detail.get("teacher")) == _normalize(teacher)
                        and _normalize(detail.get("question_type")) != "qcu_oui_non"
                    ],
                }
            )
        summary_items.append(
            {
                "rank": rank,
                "type": "module",
                "title": module["name"],
                "subtitle": "",
                "ue": module["ue"],
                "teachers": teachers,
                "score": None,
                "positive_count": 0,
                "total_count": 0,
                "teacher_scores": teacher_scores,
                "attendance_total": attendance["total"],
                "attendance_chart_data": attendance["chart_data"],
                "teacher_groups": teacher_groups,
            }
        )

    ues = sorted({module["ue"] for module in modules if module.get("ue")})
    warning_msg = None if records else "Aucune réponse n'est encore disponible."

    return {
        "survey": survey,
        "program_name": program["name"],
        "program": program,
        "respondents_count": details["respondents_count"],
        "answers_count": details["answers_count"],
        "submissions_count": details["submissions_count"],
        "warning_msg": warning_msg,
        "viz_data": {
            "filters": {"ues": ues, "modules": modules},
            "modules": modules,
            "summary_items": summary_items,
            "recommendation": _get_recommendation_score(records),
            "details": answer_details,
            "records": records,
        },
    }
