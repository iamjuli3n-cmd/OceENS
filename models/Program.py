from typing import Optional

from sqlalchemy import Column, Float, ForeignKey, Integer, String, Text
from sqlmodel import Field, SQLModel

class Program(SQLModel, table=True):
    __tablename__ = "programs"

    code: str = Field(sa_column=Column("code", String, primary_key=True))

    name: str = Field(sa_column=Column("name", String, nullable=False))

    campus: str = Field(sa_column=Column("campus", String, nullable=False))