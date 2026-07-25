from typing import Optional

from sqlalchemy import Column, Float, ForeignKey, Integer, String, Text
from sqlmodel import Field, SQLModel

class Role(SQLModel, table=True):
    """Un rôle attribué à un utilisateur, avec son périmètre.

    Un même utilisateur peut cumuler plusieurs rôles (une ligne par rôle).
    La valeur `role` encode le rôle ET son périmètre, ex:
    `program_manager:INFO`, `campus_manager:Cachan`, ou simplement `admin`.

    La clé primaire est composite (user_id, role) : un utilisateur ne peut pas
    avoir deux fois exactement le même rôle+périmètre.
    """

    __tablename__ = "roles"

    # Partie 1 de la clé composite : à quel utilisateur appartient ce rôle
    user_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            "user_id", Integer, ForeignKey("users.user_id"), primary_key=True
        ),
    )

    # Partie 2 de la clé composite : le rôle + son périmètre (ex: "program_manager:INFO")
    # Note: la colonne SQL s'appelle "name" alors que l'attribut Python est "role"
    role: str = Field(sa_column=Column("name", String, primary_key=True))