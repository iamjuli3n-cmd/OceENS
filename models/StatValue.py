from typing import Optional

from sqlalchemy import Column, Float, ForeignKey, Integer, String
from sqlmodel import Field, SQLModel


class StatValue(SQLModel, table=True):
    """Valeur d'une statistique calculée pour un sondage donné.

    Ex: pour le sondage 12, la stat "NPS" vaut 42.0. La définition de la stat
    (échelle de couleur, libellé, etc.) est dans la table `stats` ; ici on ne
    stocke que la valeur numérique par (sondage, nom de stat).

    Clé primaire composite (survey_id, name) : une seule valeur par stat et
    par sondage.
    """

    __tablename__ = "stat_values"

    # Partie 1 de la clé : à quel sondage se rapporte cette valeur
    survey_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            "survey_id",
            Integer,
            ForeignKey("surveys.survey_id"),
            primary_key=True,
        ),
    )
    # Partie 2 de la clé : nom de la stat (référence logique vers stats.name)
    name: str = Field(
        sa_column=Column("name", String, primary_key=True)
    )
    # La valeur numérique calculée
    value: float = Field(sa_column=Column("value", Float, nullable=False))
