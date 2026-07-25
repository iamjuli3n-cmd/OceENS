from typing import Optional

from sqlalchemy import Column, Float, ForeignKey, Integer, String, Text
from sqlmodel import Field, SQLModel

class Program(SQLModel, table=True):
    """Une filière (formation) de l'EPF, ex: "INFO", "GEN".

    La clé primaire est le `code` de la filière (pas un ID technique) : c'est
    lui qu'on retrouve dans les périmètres de rôles (`program_manager:<code>`)
    et sur les sondages (`Survey.program`).
    """

    __tablename__ = "programs"

    # Code de la filière = clé primaire métier (ex: "INFO")
    code: str = Field(sa_column=Column("code", String, primary_key=True))

    # Libellé lisible de la filière
    name: str = Field(sa_column=Column("name", String, nullable=False))

    # Campus de rattachement de la filière
    campus: str = Field(sa_column=Column("campus", String, nullable=False))