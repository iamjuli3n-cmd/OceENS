from typing import Optional

from sqlalchemy import Column, Float, ForeignKey, Integer, String, Text
from sqlmodel import Field, SQLModel


class Prompt(SQLModel, table=True):
    __tablename__ = "prompts"

    prompt_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            "prompt_id",
            Integer,
            primary_key=True,
            autoincrement=True,
        ),
    )

    description: Optional[str] = Field(sa_column=Column("description", String))

    model: Optional[str] = Field(sa_column=Column("model", String))

    prompt_text: Optional[str] = Field(sa_column=Column("prompt_text", Text))