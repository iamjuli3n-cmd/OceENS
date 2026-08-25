from typing import Optional

from sqlalchemy import Column, Integer, String
from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    """Un utilisateur de l'application, identifié par son adresse mail.

    L'identité vient de Microsoft Entra ID (Azure AD) : lors du login, on
    retrouve (ou on crée) la ligne `users` correspondant au mail Microsoft.
    Les rôles et leur périmètre sont stockés à part dans la table `roles`.
    """

    __tablename__ = "users"

    # Clé primaire technique auto-incrémentée
    user_id: Optional[int] = Field(
        default=None, sa_column=Column("user_id", Integer, primary_key=True)
    )
    # Adresse mail Microsoft (identifiant métier réel de l'utilisateur)
    mail: Optional[str] = Field(default=None, sa_column=Column("mail", String))
