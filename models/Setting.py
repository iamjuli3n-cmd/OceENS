from typing import Optional

from sqlalchemy import Column, String
from sqlmodel import Field, SQLModel


class Setting(SQLModel, table=True):
    """Réglage applicatif modifiable depuis l'administration, en clé/valeur.

    Introduit pour le taux de change dollar → euro : les fournisseurs publient
    leurs tarifs en dollars, l'application affiche des euros, et le taux ne
    peut être ni codé en dur (il bouge) ni deviné à l'exécution (aucun appel
    réseau sortant n'est souhaitable au démarrage).

    Volontairement générique et minimal : une table de réglages évite d'ajouter
    une colonne à une table métier chaque fois qu'un paramètre apparaît. La
    valeur est stockée en texte, chaque appelant sachant la relire dans son
    type.
    """

    __tablename__ = "settings"

    key: Optional[str] = Field(
        default=None, sa_column=Column("key", String, primary_key=True)
    )

    value: Optional[str] = Field(default=None, sa_column=Column("value", String))

    # À quoi sert ce réglage, affiché à côté du champ de saisie.
    description: Optional[str] = Field(
        default=None, sa_column=Column("description", String)
    )
