from typing import Optional

from sqlalchemy import Column, Float, ForeignKey, Integer, String, Text
from sqlmodel import Field, SQLModel



class Question(SQLModel, table=True):
    __tablename__ = "questions"

    
    section_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            "section_id", Integer, ForeignKey("sections.section_id")
        ),
    )
    question_id: Optional[int] = Field(
        default=None, sa_column=Column("question_id", Integer, primary_key=True)
    )
    question_type: Optional[str] = Field(
        default=None, sa_column=Column("question_type", String)
    )
    language: Optional[str] = Field(default=None, sa_column=Column("language", String))
    text_fr: Optional[str] = Field(default=None, sa_column=Column("text_fr", Text))
    text_en: Optional[str] = Field(default=None, sa_column=Column("text_en", Text))
    is_optional: bool = Field(
        default=False,
        sa_column=Column(
            "is_optional", Integer, nullable=False, default=0, server_default="0"
        ),
    )
