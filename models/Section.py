from typing import Optional

from sqlalchemy import Column, Float, ForeignKey, Integer, String, Text
from sqlmodel import Field, SQLModel



class Section(SQLModel, table=True):
    __tablename__ = "sections"

    section_id: Optional[int] = Field(
        default=None, sa_column=Column("section_id", Integer, primary_key=True)
    )

    template_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            "template_id",
            Integer,
            ForeignKey("templates.template_id"),
        ),
    )

    name: Optional[str] = Field(default=None, sa_column=Column("name", String))
    order: Optional[int] = Field(default=None, sa_column=Column("order", Integer))
    section_type: Optional[str] = Field(
        default=None, sa_column=Column("section_type", String)
    )