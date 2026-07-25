from typing import Optional

from sqlalchemy import Column, Float, ForeignKey, Integer, String, Text
from sqlmodel import Field, SQLModel



class Section(SQLModel, table=True):
    """Une section d'un modèle de sondage, regroupant des questions.

    Les sections structurent un template (ex: "Campus", "Formation",
    "Module/Enseignant"). Le `section_type` pilote la logique métier (calcul
    des scores, affichage dans la visualisation) et `order` fixe l'ordre
    d'affichage.
    """

    __tablename__ = "sections"

    # Clé primaire technique
    section_id: Optional[int] = Field(
        default=None, sa_column=Column("section_id", Integer, primary_key=True)
    )

    # Modèle de sondage auquel appartient la section
    template_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            "template_id",
            Integer,
            ForeignKey("templates.template_id"),
        ),
    )

    # Titre de la section
    name: Optional[str] = Field(default=None, sa_column=Column("name", String))
    # Ordre d'affichage de la section dans le sondage
    order: Optional[int] = Field(default=None, sa_column=Column("order", Integer))
    # Type de section (ex: "ME" pour module/enseignant) : pilote la logique métier
    section_type: Optional[str] = Field(
        default=None, sa_column=Column("section_type", String)
    )