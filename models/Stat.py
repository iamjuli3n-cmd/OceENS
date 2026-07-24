from sqlalchemy import Column, Integer, String
from sqlmodel import Field, SQLModel


class Stat(SQLModel, table=True):
    __tablename__ = "stats"

    name: str = Field(
        sa_column=Column("name", String, primary_key=True)
    )
    color_scale: str = Field(
        sa_column=Column("color_scale", String, nullable=False)
    )
    section_type: str = Field(
        sa_column=Column("section_type", String, nullable=False)
    )
    short: str = Field(
        sa_column=Column("short", String, nullable=False)
    )
    label: str = Field(
        sa_column=Column("label", String, nullable=False)
    )
    suffix: str = Field(
        sa_column=Column("suffix", String, nullable=False)
    )
    show_explicit_positive: int = Field(
        sa_column=Column("show_explicit_positive", Integer, nullable=False)
    )
