import io
import re
import pandas as pd
from fastapi.responses import Response


EXPORT_COLUMNS = [
    "Campus",
    "Formation",
    "Annee_Scolaire",
    "Semestre",
    "UE",
    "Module",
    "Enseignant",
    "Section",
    "Categorie",
    "Type_Question",
    "Valeur_Reponse",
    "Question_ID",
    "Reponse_ID",
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
    formation = _safe_filename(getattr(survey_obj, "formation", "formation"))
    semestre = _safe_filename(getattr(survey_obj, "semestre", "semestre"))
    annee_scolaire = _safe_filename(
        getattr(survey_obj, "annee_scolaire", "annee_scolaire")
    )

    filename = f"export_{campus}_{formation}_{semestre}_{annee_scolaire}.csv"

    return Response(
        content=csv_bytes,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
