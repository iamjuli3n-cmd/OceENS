from typing import Optional

from sqlalchemy import Column, Float, ForeignKey, Integer, String, Text
from sqlmodel import Field, SQLModel


class Respondent(SQLModel, table=True):
    """Inscription d'un utilisateur à un sondage (invité à répondre).

    Une ligne = un étudiant convié à un sondage. La clé primaire composite
    (survey_id, user_id) empêche les doublons. `submission_date` sert de
    marqueur d'état : NULL tant que l'étudiant n'a pas répondu, renseigné une
    fois le sondage soumis.
    """

    __tablename__ = "respondents"

    # Partie 1 de la clé composite : le sondage concerné
    survey_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            "survey_id", Integer, ForeignKey("surveys.survey_id"), primary_key=True
        ),
    )
    # Partie 2 de la clé composite : l'utilisateur convié
    user_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            "user_id", Integer, ForeignKey("users.user_id"), primary_key=True
        ),
    )

    # Date de soumission ; NULL = l'étudiant n'a pas encore répondu
    submission_date: Optional[str] = Field(
        default=None, sa_column=Column("submission_date", String)
    )
