from sqlalchemy import Column, Integer, String
from sqlmodel import Field, SQLModel


class Stat(SQLModel, table=True):
    """Définition (métadonnées) d'une statistique affichable.

    Décrit COMMENT présenter une stat : échelle de couleur, libellés, suffixe
    (ex: "%"), à quel type de section elle s'applique. Les valeurs concrètes
    par sondage sont stockées à part dans `stat_values`.
    """

    __tablename__ = "stats"

    # Nom de la stat = clé primaire (ex: "NPS", "satisfaction")
    name: str = Field(
        sa_column=Column("name", String, primary_key=True)
    )
    # Échelle de couleur utilisée pour l'affichage (seuils de couleur)
    color_scale: str = Field(
        sa_column=Column("color_scale", String, nullable=False)
    )
    # Type de section auquel cette stat s'applique
    section_type: str = Field(
        sa_column=Column("section_type", String, nullable=False)
    )
    # Libellé court (affichage compact)
    short: str = Field(
        sa_column=Column("short", String, nullable=False)
    )
    # Libellé complet de la stat
    label: str = Field(
        sa_column=Column("label", String, nullable=False)
    )
    # Suffixe affiché après la valeur (ex: "%", "/10")
    suffix: str = Field(
        sa_column=Column("suffix", String, nullable=False)
    )
    # 1 pour afficher explicitement le taux de réponses positives
    show_explicit_positive: int = Field(
        sa_column=Column("show_explicit_positive", Integer, nullable=False)
    )
