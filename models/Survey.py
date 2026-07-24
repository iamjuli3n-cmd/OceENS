from typing import Optional

from sqlalchemy import Column, Float, ForeignKey, Integer, String, Text
from sqlmodel import Field, SQLModel


class Survey(SQLModel, table=True):
    __tablename__ = "surveys"

    survey_id: Optional[int] = Field(
        default=None, sa_column=Column("survey_id", Integer, primary_key=True)
    )

    template_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            "template_id",
            Integer,
            ForeignKey("templates.template_id"),
        ),
    )

    program: Optional[str] = Field(
        default=None,
        sa_column=Column(
            "program",
            String,
            ForeignKey("programs.code"),
            nullable=True,
        ),
    )

    semester: Optional[str] = Field(default=None, sa_column=Column("semester", String))
    # 1 : Active / 0 : Closed
    status: Optional[int] = Field(default=None, sa_column=Column("status", Integer))
    school_year: Optional[str] = Field(
        default=None, sa_column=Column("school_year", String)
    )
    password: Optional[str] = Field(default=None, sa_column=Column("password", String))