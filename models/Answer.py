from typing import Optional

from sqlalchemy import Column, Float, ForeignKey, Integer, String, Text
from sqlmodel import Field, SQLModel

class Answer(SQLModel, table=True):
    """Une réponse individuelle à une question, au sein d'une soumission.

    Une soumission (`Submission`) regroupe toutes les réponses d'un étudiant à
    un sondage. Selon le type de question :
    - question à choix : `option_id` est renseigné (l'option choisie) ;
    - question ouverte (verbatim) : `value` contient le texte libre.
    `module_id`/`teacher` précisent l'enseignement concerné pour les sections
    module/enseignant.
    """

    __tablename__ = "answers"

    # Clé primaire technique auto-incrémentée
    answer_id: Optional[int] = Field(
        default=None,
        sa_column=Column("answer_id", Integer, primary_key=True, autoincrement=True),
    )

    # Soumission à laquelle appartient cette réponse (obligatoire)
    submission_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            "submission_id",
            Integer,
            ForeignKey("submissions.submission_id"),
            nullable=False,
        ),
    )

    # Module/enseignement concerné (null pour les questions hors module)
    module_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            "module_id",
            Integer,
            ForeignKey("modules.module_id"),
            nullable=True,
        ),
    )

    # Nom de l'enseignant concerné (copié pour l'agrégation des scores profs)
    teacher: Optional[str] = Field(
        default=None,
        sa_column=Column("teacher", String, nullable=True),
    )

    # Question à laquelle on répond
    question_id: Optional[int] = Field(
        default=None,
        sa_column=Column("question_id", Integer, ForeignKey("questions.question_id")),
    )

    # Option choisie (pour les questions à choix ; null pour un verbatim)
    option_id: Optional[int] = Field(
        default=None,
        sa_column=Column("option_id", Integer, ForeignKey("options.option_id")),
    )

    # Valeur texte libre (pour les questions ouvertes ; null pour un choix)
    value: Optional[str] = Field(default=None, sa_column=Column("value", Text))