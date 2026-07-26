"""Configuration de la base de données SQLite et dépendance de session.

Ce module centralise :
- la création du moteur SQLAlchemy pointant sur le fichier SQLite ;
- `create_db_and_tables()` appelé au démarrage pour créer les tables ;
- `SessionDep`, la dépendance FastAPI qui injecte une session dans les routes.
"""

import logging
import os
from typing import Annotated

from fastapi import Depends
from sqlalchemy import text
from sqlmodel import SQLModel, create_engine, Session, select

# User est défini dans models/ et hérite de SQLModel
from models import User

logger = logging.getLogger("uvicorn.error")

# Emplacement du fichier de base (le dossier database/ est ignoré par Git)
DATABASE_PATH="./database/"
DATABASE_URL = f"sqlite:///{DATABASE_PATH}/db_oceens.db"


# Créer le dossier database/ au premier lancement s'il n'existe pas
if not os.path.exists(DATABASE_PATH):
    os.mkdir(DATABASE_PATH)

# check_same_thread=False : nécessaire pour SQLite avec FastAPI (multi-thread)
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

# Colonnes ajoutées après la première mise en production, par table. SQLite
# accepte `ALTER TABLE ... ADD COLUMN` sans réécrire la table, et une colonne
# ajoutée vaut NULL sur les lignes existantes — ce que les modèles prévoient
# déjà (coût inconnu pour les synthèses antérieures, repli sur le fournisseur
# par défaut pour les prompts).
_ADDED_COLUMNS = {
    "summaries": (
        ("model_used", "TEXT"),
        ("input_tokens", "INTEGER"),
        ("output_tokens", "INTEGER"),
    ),
    # Ajoutée avec la configuration multi-fournisseur : les bases déployées
    # avant celle-ci ne l'ont pas, et son absence casse toute lecture de la
    # table `prompts`.
    "prompts": (("provider_id", "INTEGER"),),
    # Forfait par génération, ajouté quand il est apparu que le LLM
    # auto-hébergé de l'école n'est pas gratuit à l'appel.
    "llm_model_prices": (
        ("flat_cost_min", "REAL DEFAULT 0"),
        ("flat_cost_max", "REAL DEFAULT 0"),
    ),
}


def migrate_added_columns():
    """Ajoute les colonnes manquantes aux tables déjà déployées.

    `SQLModel.metadata.create_all()` crée les tables absentes mais ne touche
    jamais à une table existante : une base en production garde donc son schéma
    d'origine, et toute requête portant sur une nouvelle colonne échoue avec
    « no such column ». Cette fonction comble l'écart au démarrage.

    Idempotente : elle compare le schéma réel (`PRAGMA table_info`) à la liste
    attendue et n'émet un `ALTER TABLE` que pour ce qui manque réellement.
    """
    with engine.connect() as connection:
        for table, columns in _ADDED_COLUMNS.items():
            # Table pas encore créée (base vierge) : create_all s'en charge
            # avec le schéma complet, il n'y a rien à migrer.
            exists = connection.execute(
                text("SELECT 1 FROM sqlite_master WHERE type='table' AND name=:t"),
                {"t": table},
            ).first()
            if not exists:
                continue

            present = {
                row[1]  # PRAGMA table_info : (cid, name, type, ...)
                for row in connection.execute(text(f"PRAGMA table_info({table})"))
            }

            for column, sql_type in columns:
                if column in present:
                    continue
                # Noms de tables et de colonnes viennent de la constante
                # ci-dessus, jamais d'une entrée utilisateur : pas de risque
                # d'injection, et ALTER TABLE n'accepte pas de paramètre lié.
                connection.execute(
                    text(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}")
                )
                connection.commit()
                logger.info("Migration : colonne %s.%s ajoutée", table, column)


def create_db_and_tables():
    """Crée les tables manquantes, puis migre les tables déjà existantes."""
    SQLModel.metadata.create_all(engine)
    migrate_added_columns()

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