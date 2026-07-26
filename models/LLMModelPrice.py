from typing import Optional

from sqlalchemy import Column, Float, ForeignKey, Integer, String
from sqlmodel import Field, SQLModel


class LLMModelPrice(SQLModel, table=True):
    """Tarif d'un modèle LLM. Tous les montants sont **en euros**.

    Les tarifs changent sans prévenir et chaque école peut ajouter son propre
    fournisseur : les garder en base plutôt qu'en dur dans le code évite une
    livraison à chaque évolution de grille tarifaire.

    Deux composantes, additionnées :

    - un **forfait par génération** (`flat_cost_min` / `flat_cost_max`), pour
      les modèles dont le coût ne se mesure pas au token. Le LLM auto-hébergé
      de l'école entre dans ce cas : GPU, électricité et amortissement du
      serveur, ramenés à un appel, coûtent 2 à 5 centimes « tout inclus ». Ce
      n'est donc pas gratuit, contrairement à ce qu'on suppose spontanément
      d'un service auto-hébergé ;
    - un **prix au million de tokens**, pour les fournisseurs commerciaux qui
      facturent à la consommation.

    Le forfait est une *fourchette* parce que l'information de départ en est
    une. Écraser « 2 à 5 centimes » en une moyenne afficherait une précision
    que la mesure n'a pas. Un tarif exact se saisit avec min = max.

    Un modèle sans ligne ici n'est pas une erreur : le coût est marqué « non
    calculable » plutôt qu'estimé au hasard. Un tarif faux serait pire qu'un
    tarif absent, puisqu'il serait affiché comme un montant réel.
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

    # Forfait par génération, en euros. Fourchette basse et haute : min == max
    # quand le coût est connu exactement, min == max == 0 pour un modèle
    # facturé uniquement à la consommation.
    flat_cost_min: float = Field(
        default=0.0,
        sa_column=Column("flat_cost_min", Float, nullable=False, default=0.0),
    )

    flat_cost_max: float = Field(
        default=0.0,
        sa_column=Column("flat_cost_max", Float, nullable=False, default=0.0),
    )

    # Prix en euros par million de tokens. Les fournisseurs publient en dollars
    # par million : le million est conservé comme unité de saisie (diviser à
    # la saisie inviterait l'erreur de trois zéros), mais la conversion en
    # euros est faite au moment de l'enregistrement, pour que tous les montants
    # de l'application soient dans la même devise.
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
