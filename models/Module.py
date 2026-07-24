from typing import Optional

from sqlalchemy import Column, Float, ForeignKey, Integer, String, Text
from sqlmodel import Field, SQLModel



class Module(SQLModel, table=True):
    __tablename__ = "modules"

    module_id: Optional[int] = Field(
        default=None, sa_column=Column("module_id", Integer, primary_key=True)
    )
    name: Optional[str] = Field(default=None, sa_column=Column("name", String))
    teacher: Optional[str] = Field(default=None, sa_column=Column("teacher", String))
    ue: Optional[str] = Field(default=None, sa_column=Column("ue", String))
    one_teacher_in_list: Optional[bool] = Field(
        default=False, sa_column=Column("one_teacher_in_list", Integer)
    )
    survey_id: Optional[int] = Field(
        default=None,
        sa_column=Column("survey_id", Integer, ForeignKey("surveys.survey_id")),
    )
