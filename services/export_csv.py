import re

import pandas as pd
from fastapi.responses import Response


EXPORT_COLUMNS = [
    "campus",
    "program",
    "school_year",
    "semester",
    "ue",
    "module",
    "teacher",
    "section",
    "category",
    "question_type",
    "question_id",
    "submission_id",
    "answer_value",
]


SORT_COLUMNS = [
    "campus",
    "program",
    "school_year",
    "semester",
    "section",
    "ue",
    "module",
    "teacher",
    "question_id",
    "submission_id",
]

SORT_ASCENDING = [
    True,  # campus : A à Z
    True,  # program : A à Z
    True,  # school_year : A à Z
    True,  # semester : A à Z
    True,  # section : A à Z
    True,  # ue : A à Z
    True,  # module : A à Z
    True,  # teacher : A à Z
    True,  # question_id : du plus petit au plus grand
    True,  # submission_id : du plus petit au plus grand
]


def _safe_filename(value: str) -> str:
    value = value or "export"
    value = re.sub(r"[^a-zA-Z0-9_-]+", "_", value)
    return value.strip("_")


def generate_csv_response(survey_obj) -> Response:
    """
    Convertit l'objet FullSurvey en CSV via Pandas et retourne une FastAPI Response.
    Les lignes sont triées selon la règle métier demandée.
    """
    records = survey_obj.to_flat_dataframe_records()
    df = pd.DataFrame(records) if records else pd.DataFrame()

    # Garantit que toutes les colonnes attendues existent
    for col in EXPORT_COLUMNS:
        if col not in df.columns:
            df[col] = None

    # Garantit un tri numérique correct pour les IDs
    for col in ["question_id", "submission_id"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

    # Tri demandé :
    # campus > program > school_year > semester > section > ue > module
    # > teacher > question_id > submission_id
    existing_sort_columns = []
    existing_sort_ascending = []

    for col, ascending in zip(SORT_COLUMNS, SORT_ASCENDING):
        if col in df.columns:
            existing_sort_columns.append(col)
            existing_sort_ascending.append(ascending)

    if existing_sort_columns:
        df = df.sort_values(
            by=existing_sort_columns,
            ascending=existing_sort_ascending,
            kind="stable",
            na_position="last",
        )

    # Ordre des colonnes exportées
    df = df[EXPORT_COLUMNS]

    csv_text = df.to_csv(index=False, sep=";")
    csv_bytes = csv_text.encode("utf-8-sig")

    campus = _safe_filename(getattr(survey_obj, "campus", "campus"))
    program = _safe_filename(getattr(survey_obj, "program", "program"))
    semester = _safe_filename(getattr(survey_obj, "semester", "semester"))
    school_year = _safe_filename(getattr(survey_obj, "school_year", "school_year"))

    filename = f"export_{campus}_{program}_{semester}_{school_year}.csv"

    return Response(
        content=csv_bytes,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
