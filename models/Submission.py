from typing import Optional

from sqlalchemy import Column, Float, ForeignKey, Integer, String, Text
from sqlmodel import Field, SQLModel

class Submission(SQLModel, table=True):
    __tablename__ = "submissions"

    submission_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            "submission_id",
            Integer,
            primary_key=True,
            autoincrement=True,
        ),
    )

    survey_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            "survey_id",
            Integer,
            ForeignKey("surveys.survey_id"),
            nullable=False,
        ),
    )

    created_at: Optional[str] = Field(
        default=None,
        sa_column=Column("created_at", String),
    )