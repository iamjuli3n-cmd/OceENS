from typing import Optional

from sqlalchemy import Column, Integer, String
from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    __tablename__ = "users"

    user_id: Optional[int] = Field(
        default=None, sa_column=Column("user_id", Integer, primary_key=True)
    )
    mail: Optional[str] = Field(default=None, sa_column=Column("mail", String))
