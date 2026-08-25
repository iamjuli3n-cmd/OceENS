from typing import Optional

from sqlalchemy import Column, Float, ForeignKey, Integer, String, Text
from sqlmodel import Field, SQLModel



class Template(SQLModel, table=True):
    """Un modèle de sondage réutilisable.

    Un template définit la structure d'un sondage (ses sections et questions)
    sans être lié à une filière ou une année précise. Un `Survey` concret
    instancie un template pour une filière/semestre donnés.
    """

    __tablename__ = "templates"

    # Clé primaire technique
    template_id: Optional[int] = Field(
        default=None, sa_column=Column("template_id", Integer, primary_key=True)
    )
    # Libellé du modèle
    name: Optional[str] = Field(default=None, sa_column=Column("name", String))
    # Auteur/propriétaire du modèle
    user_id: Optional[int] = Field(
        default=None, sa_column=Column("user_id", Integer, ForeignKey("users.user_id"))
    )
    # Modèle utilisable ou archivé (stocké comme 0/1 en base)
    active: bool = Field(
        default=False,
        sa_column=Column("active", Integer, nullable=False, default=0, server_default="0"),
    )
