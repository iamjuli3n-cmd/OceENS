from typing import Optional

from sqlalchemy import Column, Float, ForeignKey, Integer, String
from sqlmodel import Field, SQLModel


class StatValue(SQLModel, table=True):
    __tablename__ = "stat_values"

    survey_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            "survey_id",
            Integer,
            ForeignKey("surveys.survey_id"),
            primary_key=True,
        ),
    )
    name: str = Field(
        sa_column=Column("name", String, primary_key=True)
    )
    value: float = Field(sa_column=Column("value", Float, nullable=False))
