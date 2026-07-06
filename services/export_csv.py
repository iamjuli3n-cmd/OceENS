import io
import re
import pandas as pd
from fastapi.responses import Response


EXPORT_COLUMNS = [
    "campus",
    "program",
    "school_year",
    "semester",
    "submission_id",
    "ue",
    "module",
    "teacher",
    "section",
    "category",
    "question_type",
    "question_id",
    "answer_id",
    "answer_value",
]


def _safe_filename(value: str) -> str:
    value = value or "export"
    value = re.sub(r"[^a-zA-Z0-9_-]+", "_", value)
    return value.strip("_")


def generate_csv_response(survey_obj) -> Response:
    """
    Convertit l'objet FullSurvey en CSV via Pandas et retourne une FastAPI Response.
    """
    records = survey_obj.to_flat_dataframe_records()

    # debug
    print(records[:3])

    df = pd.DataFrame(records) if records else pd.DataFrame()

    # Garantit que toutes les colonnes attendues existent
    for col in EXPORT_COLUMNS:
        if col not in df.columns:
            df[col] = None

    # Ordre logique pour lecture prof
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
