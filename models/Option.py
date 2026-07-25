from typing import Optional

from sqlalchemy import Column, Float, ForeignKey, Integer, String, Text
from sqlmodel import Field, SQLModel



class Option(SQLModel, table=True):
    """Une option de réponse proposée pour une question à choix.

    Chaque option a un libellé bilingue (FR/EN) et un indicateur `is_positive`
    servant au calcul des statistiques de satisfaction (une réponse "positive"
    compte favorablement dans le score).
    """

    __tablename__ = "options"

    # Question à laquelle cette option appartient
    question_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            "question_id",
            Integer,
            ForeignKey("questions.question_id"),
        ),
    )
    # Clé primaire technique de l'option
    option_id: Optional[int] = Field(
        default=None, sa_column=Column("option_id", Integer, primary_key=True)
    )
    # Libellé de l'option en français
    text_fr: Optional[str] = Field(default=None, sa_column=Column("text_fr", Text))
    # Libellé de l'option en anglais
    text_en: Optional[str] = Field(default=None, sa_column=Column("text_en", Text))
    # 1 si l'option compte comme réponse "positive" pour le score de satisfaction
    is_positive: Optional[int] = Field(
        default=None, sa_column=Column("is_positive", Integer)
    )
