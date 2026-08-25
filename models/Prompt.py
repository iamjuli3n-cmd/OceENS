from typing import Optional

from sqlalchemy import Column, Float, ForeignKey, Integer, String, Text
from sqlmodel import Field, SQLModel


class Prompt(SQLModel, table=True):
    """Un prompt LLM utilisé pour générer les synthèses de verbatims.

    Le `prompt_text` contient le marqueur littéral `{ANSWERS}` qui sera
    remplacé par les réponses réelles au moment de la génération. Le champ
    `model` indique quel modèle utiliser côté fournisseur LLM.
    """

    __tablename__ = "prompts"

    # Clé primaire technique auto-incrémentée
    prompt_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            "prompt_id",
            Integer,
            primary_key=True,
            autoincrement=True,
        ),
    )

    # Description lisible du prompt (à quoi il sert)
    description: Optional[str] = Field(sa_column=Column("description", String))

    # Nom du modèle LLM à utiliser (ex: "llama2", "gpt-4")
    model: Optional[str] = Field(sa_column=Column("model", String))

    # Le texte du prompt, contient le marqueur {ANSWERS} à substituer
    prompt_text: Optional[str] = Field(sa_column=Column("prompt_text", Text))

    # Fournisseur LLM à utiliser (FK nullable vers llm_providers).
    # NULL = repli sur le fournisseur par défaut (Ollama EPF) : les prompts
    # créés avant la config multi-fournisseur continuent de fonctionner.
    provider_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            "provider_id",
            Integer,
            ForeignKey("llm_providers.provider_id"),
            nullable=True,
        ),
    )