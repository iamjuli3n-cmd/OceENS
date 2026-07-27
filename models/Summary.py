from typing import Optional

from sqlalchemy import Column, Float, ForeignKey, Integer, String, Text
from sqlmodel import Field, SQLModel

class Summary(SQLModel, table=True):
    __tablename__ = "summaries"

    summary_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            "summary_id",
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
        sa_column=Column("teacher", String, ForeignKey("modules.teacher"), nullable=True),
    )

    question_id: Optional[int] = Field(
        default=None,
        sa_column=Column("question_id", Integer, ForeignKey("questions.question_id")),
    )

    prompt_id: Optional[int] = Field(
        default=None,
        sa_column=Column("prompt_id", Integer, ForeignKey("prompts.prompt_id")),
    )

    http_status: Optional[int] = Field(
        default=None, sa_column=Column("http_status", Integer)
    )

    summary_text: Optional[str] = Field(sa_column=Column("summary_text", Text))

    metadata_text: Optional[str] = Field(sa_column=Column("metadata_text", Text))