from typing import Optional

from sqlalchemy import Column, Float, ForeignKey, Integer, String, Text
from sqlmodel import Field, SQLModel

class Summary(SQLModel, table=True):
    """Synthèse LLM des verbatims, générée de façon asynchrone.

    Le daemon `summaries_generator_daemon.py` traite les lignes en attente et
    remplit `summary_text` (HTML) et `metadata_text`. Le champ `http_status`
    sert de marqueur d'état de la file :
    - 0 : en attente de génération ;
    - 200 : synthèse générée avec succès ;
    - 504 / autre : échec (timeout, modèle introuvable...).
    """

    __tablename__ = "summaries"

    # Clé primaire technique auto-incrémentée
    summary_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            "summary_id",
            Integer,
            primary_key=True,
            autoincrement=True,
        ),
    )

    # Sondage concerné par la synthèse (obligatoire)
    survey_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            "survey_id",
            Integer,
            ForeignKey("surveys.survey_id"),
            nullable=False,
        ),
    )

    # Module concerné (null si la synthèse ne cible pas un module précis)
    module_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            "module_id",
            Integer,
            ForeignKey("modules.module_id"),
            nullable=True,
        ),
    )

    # Enseignant concerné (null si non applicable)
    teacher: Optional[str] = Field(
        default=None,
        sa_column=Column("teacher", String, ForeignKey("modules.teacher"), nullable=True),
    )

    # Question dont on synthétise les verbatims
    question_id: Optional[int] = Field(
        default=None,
        sa_column=Column("question_id", Integer, ForeignKey("questions.question_id")),
    )

    # Prompt LLM utilisé pour générer cette synthèse
    prompt_id: Optional[int] = Field(
        default=None,
        sa_column=Column("prompt_id", Integer, ForeignKey("prompts.prompt_id")),
    )

    # État de la file : 0 = à générer, 200 = OK, 504/autre = échec
    http_status: Optional[int] = Field(
        default=None, sa_column=Column("http_status", Integer)
    )

    # Texte de la synthèse (HTML rendu depuis le markdown du LLM)
    summary_text: Optional[str] = Field(sa_column=Column("summary_text", Text))

    # Métadonnées de génération (modèle, durée, nb de tokens...) au format texte
    metadata_text: Optional[str] = Field(sa_column=Column("metadata_text", Text))