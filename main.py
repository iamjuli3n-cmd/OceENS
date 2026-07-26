"""
=============================================================================
OceENS - Application principale FastAPI
=============================================================================
Fabrique l'application et assemble les routeurs. La logique métier vit dans
les modules dédiés :

- `routers/` : les routes, découpées par domaine ;
- `core/security.py` : authentification, rôles et périmètres ;
- `core/dependencies.py` : `templates` et `logger` partagés ;
- `services/helpers.py` : navigation, statistiques, filtres, tri ;
- `services/` : agrégations, export CSV, client LLM.
"""

from contextlib import asynccontextmanager
import os
import sys
import subprocess

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
import uvicorn

from core.auth import router as auth_router
from core.database import create_db_and_tables
from core.dependencies import logger
from core.seed import seed_all_if_necessary

from routers import (
    pages,
    prompts,
    sections_questions,
    students,
    summaries,
    survey_templates,
    surveys,
    users,
)
from routers.llm import costs as llm_costs
from routers.llm import prices as llm_prices
from routers.llm import providers as llm_providers

load_dotenv()


# Valeurs de RUN_SUMMARIES_DAEMON interprétées comme "activé"
_TRUTHY = {"1", "true", "yes", "on"}


def _maybe_start_summaries_daemon():
    """Lance le daemon de synthèses en process séparé si demandé par l'env.

    Activé uniquement si RUN_SUMMARIES_DAEMON est vrai (1/true/yes/on). En
    production, `launch.sh` s'en charge déjà : on ne veut donc pas le lancer
    systématiquement. Retourne le Popen (ou None si non lancé).
    """
    if os.environ.get("RUN_SUMMARIES_DAEMON", "").strip().lower() not in _TRUTHY:
        return None

    logger.info("Démarrage du daemon de synthèses (RUN_SUMMARIES_DAEMON activé)...")
    # sys.executable = le même interpréteur Python que celui d'uvicorn
    return subprocess.Popen([sys.executable, "summaries_generator_daemon.py"])


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Cycle de vie de l'application : setup au démarrage, teardown à l'arrêt.

    Avant le `yield` : création des tables, seed initial, et lancement optionnel
    du daemon de synthèses en parallèle (si RUN_SUMMARIES_DAEMON est activé).
    Après le `yield` (à l'arrêt) : arrêt du daemon puis journalisation.
    """
    logger.info("Initialisation de la base de données...")
    create_db_and_tables()
    seed_all_if_necessary()

    # Lancer le daemon de synthèses en parallèle d'uvicorn (optionnel)
    daemon_process = _maybe_start_summaries_daemon()

    yield

    # Arrêter proprement le daemon à la fermeture de l'application
    if daemon_process is not None:
        logger.info("Arrêt du daemon de synthèses...")
        daemon_process.terminate()  # SIGTERM : le daemon quitte sa boucle
        try:
            daemon_process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            daemon_process.kill()  # forcer si toujours vivant après 10s

    logger.info("Fermeture de la connexion...")


def create_app():
    """
    Crée et configure l'application FastAPI fusionnée.
    """
    app = FastAPI(
        title="OceENS",
        description="Système de gestion et de connexion pour étudiants, professeurs et admins",
        lifespan=lifespan,
    )

    # SessionMiddleware (authentification)
    app.add_middleware(
        SessionMiddleware,
        secret_key=os.environ.get(
            "SECRET_KEY", "Y3mNqRjGQixkKjF9GXBCbOw2fHyC1wA3wqbJcQoIxt0="
        ),
        https_only=True,
        same_site="lax",
    )

    @app.middleware("http")
    async def redirect_errors(request: Request, call_next):
        """Renvoie toute erreur vers l'accueil, qui choisit le dashboard."""
        response = await call_next(request)

        if response.status_code == 404 and request.url.path != "/":
            return RedirectResponse(url="/", status_code=303)
        return response

    # Routeur d'authentification (login/logout/callback Azure Entra ID)
    app.include_router(auth_router)

    # Fichiers statiques (les templates Jinja sont montés dans dependencies.py)
    app.mount("/static", StaticFiles(directory="static"), name="static")

    # ┌─ Assemblage des routeurs ──────────────────────────────────────────┐
    # L'ordre reproduit celui de l'ancien app.py : api, puis dashboard,
    # puis backend. La page d'accueil reste sans préfixe.
    app.include_router(pages.router)

    for module in (surveys, students, users, summaries, sections_questions):
        app.include_router(module.router)

    for module in (prompts, survey_templates, llm_costs):
        app.include_router(module.api_router)

    app.include_router(pages.dashboard_router)

    for module in (prompts, survey_templates, llm_providers, llm_prices, llm_costs):
        app.include_router(module.backend_router)
    # └────────────────────────────────────────────────────────────────────┘

    return app


# ┌─ Instance applicative globale ───────────────────────────────────────┐
app = create_app()
# └──────────────────────────────────────────────────────────────────────┘


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
    )
