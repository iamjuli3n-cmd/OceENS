from typing import Optional

from sqlalchemy import Column, Float, ForeignKey, Integer, String, Text
from sqlmodel import Field, SQLModel

class Role(SQLModel, table=True):
    __tablename__ = "roles"

    # Composite primary key (user_id,role,program_code)

    user_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            "user_id", Integer, ForeignKey("users.user_id"), primary_key=True
        ),
    )

    role: str = Field(sa_column=Column("name", String, primary_key=True))