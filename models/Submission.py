from typing import Optional

from sqlalchemy import Column, Float, ForeignKey, Integer, String, Text
from sqlmodel import Field, SQLModel

class Submission(SQLModel, table=True):
    """Un envoi complet de réponses à un sondage (une "copie" rendue).

    Une soumission regroupe toutes les `Answer` d'un même remplissage. Elle est
    anonyme au sens où elle n'est pas liée à un `User` : seul le lien vers le
    sondage et l'horodatage sont conservés.
    """

    __tablename__ = "submissions"

    # Clé primaire technique auto-incrémentée
    submission_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            "submission_id",
            Integer,
            primary_key=True,
            autoincrement=True,
        ),
    )

    # Sondage auquel se rapporte cette soumission (obligatoire)
    survey_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            "survey_id",
            Integer,
            ForeignKey("surveys.survey_id"),
            nullable=False,
        ),
    )

    # Horodatage de création de la soumission
    created_at: Optional[str] = Field(
        default=None,
        sa_column=Column("created_at", String),
    )