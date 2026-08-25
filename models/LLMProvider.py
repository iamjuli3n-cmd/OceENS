from typing import Optional

from sqlalchemy import Column, ForeignKey, Integer, String
from sqlmodel import Field, SQLModel


class LLMProvider(SQLModel, table=True):
    """Configuration *non secrète* d'un fournisseur LLM.

    La clé d'API n'est jamais stockée ici : seule `api_key_env` est persistée,
    c'est-à-dire le *nom* de la variable d'environnement qui porte la clé. La
    valeur est résolue à l'appel via `os.getenv()`.
    """

    __tablename__ = "llm_providers"

    provider_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            "provider_id",
            Integer,
            primary_key=True,
            autoincrement=True,
        ),
    )

    name: Optional[str] = Field(sa_column=Column("name", String, nullable=False))

    api_type: Optional[str] = Field(sa_column=Column("api_type", String, nullable=False))

    base_url: Optional[str] = Field(sa_column=Column("base_url", String, nullable=False))

    api_key_env: Optional[str] = Field(
        default=None, sa_column=Column("api_key_env", String)
    )

    default_model: Optional[str] = Field(
        default=None, sa_column=Column("default_model", String)
    )

    is_active: bool = Field(
        default=True,
        sa_column=Column(
            "is_active", Integer, nullable=False, default=1, server_default="1"
        ),
    )