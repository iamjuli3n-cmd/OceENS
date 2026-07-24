from typing import Optional

from sqlalchemy import Column, Float, ForeignKey, Integer, String, Text
from sqlmodel import Field, SQLModel



class Template(SQLModel, table=True):
    __tablename__ = "templates"

    template_id: Optional[int] = Field(
        default=None, sa_column=Column("template_id", Integer, primary_key=True)
    )
    name: Optional[str] = Field(default=None, sa_column=Column("name", String))
    user_id: Optional[int] = Field(
        default=None, sa_column=Column("user_id", Integer, ForeignKey("users.user_id"))
    )
    active: bool = Field(
        default=False,
        sa_column=Column("active", Integer, nullable=False, default=0, server_default="0"),
    )
