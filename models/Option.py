from typing import Optional

from sqlalchemy import Column, Float, ForeignKey, Integer, String, Text
from sqlmodel import Field, SQLModel



class Option(SQLModel, table=True):
    __tablename__ = "options"

    question_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            "question_id",
            Integer,
            ForeignKey("questions.question_id"),
        ),
    )
    option_id: Optional[int] = Field(
        default=None, sa_column=Column("option_id", Integer, primary_key=True)
    )
    text_fr: Optional[str] = Field(default=None, sa_column=Column("text_fr", Text))
    text_en: Optional[str] = Field(default=None, sa_column=Column("text_en", Text))
    is_positive: Optional[int] = Field(
        default=None, sa_column=Column("is_positive", Integer)
    )
