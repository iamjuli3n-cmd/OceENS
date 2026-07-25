"""Configuration de la base de données SQLite et dépendance de session.

Ce module centralise :
- la création du moteur SQLAlchemy pointant sur le fichier SQLite ;
- `create_db_and_tables()` appelé au démarrage pour créer les tables ;
- `SessionDep`, la dépendance FastAPI qui injecte une session dans les routes.
"""

from typing import Annotated
from fastapi import Depends
from sqlmodel import SQLModel, create_engine, Session, select
# User est défini dans models/ et hérite de SQLModel
from models import User
import os

# Emplacement du fichier de base (le dossier database/ est ignoré par Git)
DATABASE_PATH="./database/"
DATABASE_URL = f"sqlite:///{DATABASE_PATH}/db_oceens.db"


# Créer le dossier database/ au premier lancement s'il n'existe pas
if not os.path.exists(DATABASE_PATH):
    os.mkdir(DATABASE_PATH)

# check_same_thread=False : nécessaire pour SQLite avec FastAPI (multi-thread)
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

def create_db_and_tables():
    """Crée toutes les tables déclarées dans les modèles SQLModel."""
    SQLModel.metadata.create_all(engine)

def get_session() -> Session:
    """Dépendance FastAPI : fournit une session BDD, refermée automatiquement.

    Le `yield` (générateur) permet à FastAPI de garder la session ouverte le
    temps de la requête puis de la fermer proprement à la fin (bloc `with`).
    """
    with Session(engine) as session:
        yield session

# Alias de type pour injecter une session dans une route : `session: SessionDep`
SessionDep = Annotated[Session, Depends(get_session)]

def get_or_create_user(email: str) -> str:
    """Retourne l'utilisateur correspondant au mail, en le créant s'il manque.

    Appelé au login : on ne connaît que le mail Microsoft, on récupère la ligne
    `users` existante ou on en crée une nouvelle à la volée.

    Args:
        email: adresse mail de l'utilisateur (issue de Microsoft Entra ID)
    """
    # Normaliser le mail (sans espaces, en minuscules) pour éviter les doublons
    email = email.strip().lower()

    # 1. Chercher l'utilisateur par son mail
    statement = select(User).where(User.mail == email)
    with Session(engine) as session:
        user = session.exec(statement).first()

        if not user:
            # 2. Introuvable → on le crée
            user = User(mail=email)
            session.add(user)
            session.commit()
            session.refresh(user)  # recharger pour récupérer l'user_id généré

        return user