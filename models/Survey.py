from typing import Optional

from sqlalchemy import Column, Float, ForeignKey, Integer, String, Text
from sqlmodel import Field, SQLModel


class Survey(SQLModel, table=True):
    """Un sondage concret : un modèle instancié pour une filière/année/semestre.

    Le sondage hérite sa structure d'un `Template`, et cible une filière
    (`program`) sur une année scolaire et un semestre donnés. Le `status`
    pilote le cycle de vie (voir le champ ci-dessous) et `password` protège
    éventuellement l'accès au questionnaire.
    """

    __tablename__ = "surveys"

    # Clé primaire technique
    survey_id: Optional[int] = Field(
        default=None, sa_column=Column("survey_id", Integer, primary_key=True)
    )

    # Modèle de sondage dont ce sondage hérite sa structure
    template_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            "template_id",
            Integer,
            ForeignKey("templates.template_id"),
        ),
    )

    # Filière ciblée par le sondage (code de programme)
    program: Optional[str] = Field(
        default=None,
        sa_column=Column(
            "program",
            String,
            ForeignKey("programs.code"),
            nullable=True,
        ),
    )

    # Semestre concerné (ex: "S1", "S2")
    semester: Optional[str] = Field(default=None, sa_column=Column("semester", String))
    # Statut du sondage : 1 = actif (ouvert aux réponses) / 0 = fermé
    status: Optional[int] = Field(default=None, sa_column=Column("status", Integer))
    # Année scolaire (ex: "2025-2026")
    school_year: Optional[str] = Field(
        default=None, sa_column=Column("school_year", String)
    )
    # Mot de passe éventuel protégeant l'accès au questionnaire
    password: Optional[str] = Field(default=None, sa_column=Column("password", String))