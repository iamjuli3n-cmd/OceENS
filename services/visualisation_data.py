from collections import defaultdict
from typing import Any, Dict, Optional
import json

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
    Stat,
    Submission,
    Survey,
    Summary,
)


STAT_COLOR_THRESHOLDS = {
    "campus_satisfaction": {20: "red", 50: "orange", 100: "green"},
    "program_satisfaction": {20: "red", 50: "orange", 100: "green"},
    "recommendation_score": {2: "red", 5: "orange", 10: "green"},
}


def _serialize_color_thresholds(stat_name: str) -> str:
    return json.dumps(STAT_COLOR_THRESHOLDS[stat_name])


def bilingual_text(text_fr: Optional[str], text_en: Optional[str]) -> str:
    """Build the bilingual label displayed by the survey UI."""
    return (
        f'<text class="text_fr">{text_fr}</text> <text class="text_en">{text_en}</text>'
    )


def _to_nps_score(value: Any) -> Optional[int]:
    """Return a valid NPS answer (an integer from 0 to 10)."""
    try:
        score = float(str(value).replace(",", ".").strip())
    except (TypeError, ValueError):
        return None

    if not score.is_integer() or not 0 <= score <= 10:
        return None
    return int(score)


def _add_recommendation_response(container: Dict[str, Any], value: Any) -> None:
    """Add one valid recommendation answer to the score and NPS counters."""
    score = _to_nps_score(value)
    if score is None:
        return

    container["nps_response_count"] = container.get("nps_response_count", 0) + 1
    container["recommendation_score_sum"] = (
        container.get("recommendation_score_sum", 0) + score
    )
    if score >= 9:
        category = "nps_promoter_count"
    elif score >= 7:
        category = "nps_passive_count"
    else:
        category = "nps_detractor_count"
    container[category] = container.get(category, 0) + 1


def _calculate_nps(container: Dict[str, Any]) -> Optional[float]:
    """Calculate % promoters - % detractors from accumulated answers."""
    response_count = container.get("nps_response_count", 0)
    if not response_count:
        return None

    promoters = container.get("nps_promoter_count", 0)
    detractors = container.get("nps_detractor_count", 0)
    return 100 * (promoters - detractors) / response_count


def _calculate_satisfaction_score(
    section: Dict[str, Any], submissions_count: int
) -> Optional[float]:
    if submissions_count <= 0 or "satisfaction_count" not in section:
        return None
    return 100 * section["satisfaction_count"] / submissions_count


def _calculate_recommendation_score(
    section: Dict[str, Any],
) -> Optional[float]:
    response_count = section.get("nps_response_count", 0)
    if not response_count:
        return None
    return section.get("recommendation_score_sum", 0) / response_count


def _calculate_survey_stats(
    sections: Dict[str, Dict[str, Any]], submissions_count: int
) -> Dict[str, float]:
    stats = {}
    for section in sections.values():
        section_type = section.get("section_type")
        if section_type == "C":
            score = _calculate_satisfaction_score(section, submissions_count)
            stat_name = "campus_satisfaction"
        elif section_type == "P":
            score = _calculate_satisfaction_score(section, submissions_count)
            stat_name = "program_satisfaction"
        elif section_type == "R":
            score = _calculate_recommendation_score(section)
            stat_name = "recommendation_score"
        else:
            continue

        if score is not None:
            stats[stat_name] = round(score, 1)

    return stats


def _sync_survey_stats(
    session: Session, survey_id: int, stats: Dict[str, float]
) -> None:
    existing_stats = session.exec(
        select(Stat).where(Stat.survey_id == survey_id)
    ).all()
    for stat in existing_stats:
        if stat.stat_name in STAT_COLOR_THRESHOLDS and stat.stat_name not in stats:
            session.delete(stat)

    for stat_name, stat_value in stats.items():
        session.merge(
            Stat(
                survey_id=survey_id,
                stat_name=stat_name,
                stat_value=stat_value,
                stat_color_threshold=_serialize_color_thresholds(stat_name),
            )
        )

    session.commit()


def _build_question(dic, data_row, options, options_value, submissions_sets):
    if data_row["question_id"] not in dic["questions"].keys():
        dic["questions"][data_row["question_id"]] = {
            "text": bilingual_text(
                data_row["question_text_fr"],
                data_row["question_text_en"],
            ),
            "question_type": data_row["question_type"],
            "question_submissions_count": 0,
            "is_positive": [],
            "histo": (
                {
                    o: 0 for o in options[data_row["question_id"]]
                }  # If the question as dedicated options, init the histo with them
                if data_row["question_id"] in options.keys()
                else defaultdict(int)
            ),
        }

    if data_row["module_name"] not in submissions_sets:
        submissions_sets[data_row["module_name"]] = {}
    if data_row["teacher"] not in submissions_sets[data_row["module_name"]]:
        submissions_sets[data_row["module_name"]][data_row["teacher"]] = defaultdict(
            set
        )
    if (
        data_row["submission_id"]
        not in submissions_sets[data_row["module_name"]][data_row["teacher"]][
            data_row["question_id"]
        ]
    ):  # Memorizing submissions_set
        submissions_sets[data_row["module_name"]][data_row["teacher"]][
            data_row["question_id"]
        ].add(data_row["submission_id"])
        dic["questions"][data_row["question_id"]][
            "question_submissions_count"
        ] += 1  # Counting submissions
    if data_row["question_type"] == "QCU_Satisfaction":  # SATIFACTION COUNT
        if "satisfaction_count" not in dic.keys():
            dic["satisfaction_count"] = 0
        if options_value[data_row["option_id"]]["is_positive"]:  # Count the positive
            dic["satisfaction_count"] += 1
    if data_row["question_type"] == "NPS":
        _add_recommendation_response(dic, data_row["answer_value"])
    if data_row["question_type"] == "QCU_Attendance":  # ATTENDANCE COUNT
        if "attendance_count" not in dic.keys():
            dic["attendance_count"] = 0
        if options_value[data_row["option_id"]]["text"] == "Oui":  # Count the Yes
            dic["attendance_count"] += 1
    if data_row["option_id"]:
        dic["questions"][data_row["question_id"]]["histo"][
            options_value[data_row["option_id"]]["text"]
        ] += 1  # Counting the number of appearance of each value
        if (
            options_value[data_row["option_id"]]["is_positive"]
            and options_value[data_row["option_id"]]["text"]
            not in dic["questions"][data_row["question_id"]]["is_positive"]
        ):
            dic["questions"][data_row["question_id"]]["is_positive"].append(
                options_value[data_row["option_id"]]["text"]
            )  # Conversion from option_id to text_fr
    else:
        dic["questions"][data_row["question_id"]]["histo"][
            data_row["answer_value"]
        ] += 1  # Counting the number of appearance of each value

def _replace_brackets_in_question(question, program, row):
    if '[' in question:
        if program["campus"]:
            question = question.replace("[CAMPUS]", program["campus"])
        if program["name"]:
            question = question.replace("[FORMATION]",program["name"])
        if row[4]:
            question = question.replace("[ENSEIGNANT]", row[4])
        if row[15]:
            question = question.replace("[MODULE]", row[15])
    return question

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
        context["respondents_count"] = (
            int(respondent_row[0] or 0) if respondent_row else 0
        )
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

        data = {}

        # Fetch default options for each question_id
        options = {
            o[0]: json.loads(o[1])
            for o in session.exec(
                select(Option.question_id, func.json_group_array(Option.text_fr))
                .order_by(Option.option_id)
                .group_by(Option.question_id)
            ).all()
        }

        options_value = {
            o.option_id: {"text": o.text_fr, "is_positive": o.is_positive}
            for o in session.exec(select(Option)).all()
        }

        # Memorize submissions_set
        submissions_sets = defaultdict()

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
                "question_text_fr": _replace_brackets_in_question(r[12], context["program"], r),
                "question_text_en": _replace_brackets_in_question(r[13], context["program"], r),
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
                    ] = {"ue": data_row["ue"], "teachers": {}}
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
                    _build_question(
                        data[data_row["section_name"]]["modules"][
                            data_row["module_name"]
                        ]["teachers"][data_row["teacher"]],
                        data_row,
                        options,
                        options_value,
                        submissions_sets,
                    )
            elif data_row["section_type"] == "R":
                if data_row["question_type"] == "NPS":
                    _add_recommendation_response(
                        data[data_row["section_name"]], data_row["answer_value"]
                    )

            else:  # section_type = S --> Simple
                if "questions" not in data[data_row["section_name"]]:
                    data[data_row["section_name"]] = {"questions": {}}
                _build_question(
                    data[data_row["section_name"]],
                    data_row,
                    options,
                    options_value,
                    submissions_sets,
                )

        # FETCH SUMMARY

        summary_rows = session.exec(select(Summary,Section.name, Module.name).select_from(Summary)
            .join(Module, Module.module_id == Summary.module_id, isouter=True)
            .join(Question, Question.question_id == Summary.question_id)
            .join(Section, Section.section_id == Question.section_id)
            .where(Summary.http_status==200,Summary.survey_id==survey_id)).all()

        for row in summary_rows:
            summary,section_name,module_name=row
            print(summary.module_id)
            if summary.module_id:
                q = data[section_name]["modules"][module_name]["teachers"][summary.teacher]["questions"][summary.question_id]
            else:
                q = data[section_name]["questions"][summary.question_id]
            q["summary"]={"text":summary.summary_text,"metadata":summary.metadata_text}

        context["sections"] = data
        recommendation_section = next(
            (
                section
                for section in data.values()
                if section.get("section_type") == "R"
            ),
            {},
        )
        context["recommendation"] = {
            "score": _calculate_nps(recommendation_section),
            "count": recommendation_section.get("nps_response_count", 0),
            "promoters": recommendation_section.get("nps_promoter_count", 0),
            "passives": recommendation_section.get("nps_passive_count", 0),
            "detractors": recommendation_section.get("nps_detractor_count", 0),
        }
        context["stats"] = _calculate_survey_stats(
            data, context["submissions_count"]
        )
        _sync_survey_stats(session, survey_id, context["stats"])
        # END ANSWERS

    return context
