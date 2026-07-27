from typing import Optional

from sqlalchemy import Column, Float, ForeignKey, Integer, String, Text
from sqlmodel import Field, SQLModel


class Respondent(SQLModel, table=True):
    __tablename__ = "respondents"

    # Composite Primary Key (survey_id,user_id)

    survey_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            "survey_id", Integer, ForeignKey("surveys.survey_id"), primary_key=True
        ),
    )
    user_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            "user_id", Integer, ForeignKey("users.user_id"), primary_key=True
        ),
    )

    # If submission_date is NULL --> Not yet answered
    submission_date: Optional[str] = Field(
        default=None, sa_column=Column("submission_date", String)
    )
