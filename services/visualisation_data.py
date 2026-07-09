from typing import Dict, Any


# Helper functions
def _get_record_field(record: dict, *names, default=""):
    for name in names:
        if name in record and record[name] is not None:
            return record[name]
    return default


def _to_score_1_10(value):
    try:
        score = float(str(value).replace(",", ".").strip())
    except (TypeError, ValueError):
        return None

    if 1 <= score <= 10:
        return score

    return None


def _is_recommendation_record(record: dict) -> bool:
    question_type = str(
        _get_record_field(record, "question_type", "Type_Question")
    ).lower()

    section = str(
        _get_record_field(record, "section", "Section", "category", "Categorie")
    ).lower()

    question = str(_get_record_field(record, "question", "Question")).lower()

    text = f"{question_type} {section} {question}"

    return "nps" in text or "recommand" in text or "recommend" in text


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


def get_visualisation_context(
    survey_obj,
    program_name: str | None = None,
) -> Dict[str, Any]:
    """
    Prépare les données d'affichage de la visualisation.
    """
    records = survey_obj.to_flat_dataframe_records()

    campus = survey_obj.campus or ""
    program_code = survey_obj.program or ""
    program = program_name or program_code

    # ── Score de recommandation ─────────────────────────────
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

    if recommendation_candidates:
        last_question_id = max(
            item["question_id"] for item in recommendation_candidates
        )

        last_question_scores = [
            item
            for item in recommendation_candidates
            if item["question_id"] == last_question_id
        ]

        recommendation_score = round(
            sum(item["score"] for item in last_question_scores)
            / len(last_question_scores),
            1,
        )

        recommendation_count = len(last_question_scores)
        recommendation_question = last_question_scores[0]["question"]
    else:
        recommendation_score = None
        recommendation_count = 0
        recommendation_question = ""

    # ── Modules du sondage ──────────────────────────────────
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
                "score_label": "Plutôt satisfait et +",
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

    # ── Liste affichée dans la synthèse ─────────────────────
    summary_items = [
        {
            "rank": 1,
            "type": "campus",
            "title": "Campus",
            "subtitle": campus,
            "ue": None,
            "teachers": [],
            "score": None,
            "score_label": "Plutôt satisfait et +",
        },
        {
            "rank": 2,
            "type": "formation",
            "title": "Formation",
            "subtitle": program,
            "ue": None,
            "teachers": [],
            "score": None,
            "score_label": "Plutôt satisfait et +",
        },
    ]

    for index, module in enumerate(modules, start=3):
        summary_items.append(
            {
                "rank": index,
                "type": "module",
                "title": module["name"],
                "subtitle": "",
                "ue": module["ue"],
                "teachers": module["teachers"],
                "score": module["score"],
                "score_label": module["score_label"],
            }
        )

    return {
        "filters": {
            "ues": ues,
            "modules": modules,
        },
        "modules": modules,
        "summary_items": summary_items,
        "recommendation": {
            "score": recommendation_score,
            "count": recommendation_count,
            "question": recommendation_question,
        },
        "records": records,
    }
