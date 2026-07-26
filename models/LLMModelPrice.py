from typing import Optional

from sqlalchemy import Column, Float, ForeignKey, Integer, String
from sqlmodel import Field, SQLModel


class LLMModelPrice(SQLModel, table=True):
    """Tarif d'un modèle LLM, en dollars par million de tokens.

    Les tarifs changent sans prévenir et chaque école peut ajouter son propre
    fournisseur : les garder en base plutôt qu'en dur dans le code évite une
    livraison à chaque évolution de grille tarifaire.

    Un modèle sans ligne ici n'est pas une erreur : le coût est simplement
    marqué « non calculable » plutôt qu'estimé au hasard. Un tarif faux serait
    pire qu'un tarif absent, puisqu'il serait affiché comme un montant réel.

    Les modèles auto-hébergés (Ollama de l'école) sont à 0 : l'électricité n'est
    pas facturée à l'appel.
    """

    __tablename__ = "llm_model_prices"

    price_id: Optional[int] = Field(
        default=None,
        sa_column=Column("price_id", Integer, primary_key=True, autoincrement=True),
    )

    # Fournisseur concerné. NULL = tarif générique, appliqué à ce nom de modèle
    # quel que soit le fournisseur (utile pour les endpoints compatibles OpenAI
    # qui servent le même modèle sous le même nom).
    provider_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            "provider_id",
            Integer,
            ForeignKey("llm_providers.provider_id"),
            nullable=True,
        ),
    )

    # Identifiant du modèle tel qu'envoyé au fournisseur (ex. "claude-opus-5").
    model: Optional[str] = Field(sa_column=Column("model", String, nullable=False))

    # Prix en dollars par million de tokens (unité de publication des
    # fournisseurs : la reprendre telle quelle évite une conversion à la
    # saisie, donc une source d'erreur de trois zéros).
    input_price_per_mtok: float = Field(
        default=0.0,
        sa_column=Column("input_price_per_mtok", Float, nullable=False, default=0.0),
    )

    output_price_per_mtok: float = Field(
        default=0.0,
        sa_column=Column("output_price_per_mtok", Float, nullable=False, default=0.0),
    )

    # Commentaire libre (date de relevé du tarif, palier, lien vers la grille).
    note: Optional[str] = Field(default=None, sa_column=Column("note", String))
