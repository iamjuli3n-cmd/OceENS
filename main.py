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

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initialisation de la base de données...")
    create_db_and_tables()
    seed_all_if_necessary()
    yield
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

    for module in (prompts, survey_templates):
        app.include_router(module.api_router)

    app.include_router(pages.dashboard_router)

    for module in (prompts, survey_templates):
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
