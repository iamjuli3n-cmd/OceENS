from typing import Optional

from sqlalchemy import Column, Float, ForeignKey, Integer, String, Text
from sqlmodel import Field, SQLModel

class Answer(SQLModel, table=True):
    __tablename__ = "answers"

    answer_id: Optional[int] = Field(
        default=None,
        sa_column=Column("answer_id", Integer, primary_key=True, autoincrement=True),
    )

    submission_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            "submission_id",
            Integer,
            ForeignKey("submissions.submission_id"),
            nullable=False,
        ),
    )

    module_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            "module_id",
            Integer,
            ForeignKey("modules.module_id"),
            nullable=True,
        ),
    )

    teacher: Optional[str] = Field(
        default=None,
        sa_column=Column("teacher", String, nullable=True),
    )

    question_id: Optional[int] = Field(
        default=None,
        sa_column=Column("question_id", Integer, ForeignKey("questions.question_id")),
    )

    option_id: Optional[int] = Field(
        default=None,
        sa_column=Column("option_id", Integer, ForeignKey("options.option_id")),
    )

    value: Optional[str] = Field(default=None, sa_column=Column("value", Text))