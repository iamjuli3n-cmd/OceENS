from typing import Optional

from sqlalchemy import Column, Float, ForeignKey, Integer, String, Text
from sqlmodel import Field, SQLModel



class Question(SQLModel, table=True):
    """Une question appartenant à une section d'un modèle de sondage.

    Le `question_type` (ex: "QCU_Satisfaction", "verbatim") détermine le mode
    de réponse et le traitement statistique. Le libellé est bilingue (FR/EN)
    et `is_optional` indique si l'étudiant peut ne pas répondre.
    """

    __tablename__ = "questions"

    # Section à laquelle appartient la question
    section_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            "section_id", Integer, ForeignKey("sections.section_id")
        ),
    )
    # Clé primaire technique de la question
    question_id: Optional[int] = Field(
        default=None, sa_column=Column("question_id", Integer, primary_key=True)
    )
    # Type de question (pilote l'affichage et le calcul des scores)
    question_type: Optional[str] = Field(
        default=None, sa_column=Column("question_type", String)
    )
    # Langue de la question
    language: Optional[str] = Field(default=None, sa_column=Column("language", String))
    # Libellé en français
    text_fr: Optional[str] = Field(default=None, sa_column=Column("text_fr", Text))
    # Libellé en anglais
    text_en: Optional[str] = Field(default=None, sa_column=Column("text_en", Text))
    # Vrai si la réponse est facultative (stocké comme 0/1 en base)
    is_optional: bool = Field(
        default=False,
        sa_column=Column(
            "is_optional", Integer, nullable=False, default=0, server_default="0"
        ),
    )
