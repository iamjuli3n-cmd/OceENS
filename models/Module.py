from typing import Optional

from sqlalchemy import Column, Float, ForeignKey, Integer, String, Text
from sqlmodel import Field, SQLModel



class Module(SQLModel, table=True):
    """Un enseignement (couple matière + enseignant) évalué dans un sondage.

    Un sondage porte sur plusieurs modules ; chaque module associe une UE, un
    nom de cours et un enseignant. Les réponses (`Answer`) et synthèses
    (`Summary`) référencent le module concerné.
    """

    __tablename__ = "modules"

    # Clé primaire technique
    module_id: Optional[int] = Field(
        default=None, sa_column=Column("module_id", Integer, primary_key=True)
    )
    # Nom du cours / de la matière
    name: Optional[str] = Field(default=None, sa_column=Column("name", String))
    # Nom de l'enseignant évalué
    teacher: Optional[str] = Field(default=None, sa_column=Column("teacher", String))
    # Unité d'enseignement de rattachement
    ue: Optional[str] = Field(default=None, sa_column=Column("ue", String))
    # Vrai s'il n'y a qu'un seul enseignant listé pour ce module
    one_teacher_in_list: Optional[bool] = Field(
        default=False, sa_column=Column("one_teacher_in_list", Integer)
    )
    # Sondage auquel ce module appartient
    survey_id: Optional[int] = Field(
        default=None,
        sa_column=Column("survey_id", Integer, ForeignKey("surveys.survey_id")),
    )
