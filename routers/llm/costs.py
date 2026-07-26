"""Écrans de coût des synthèses LLM.

Deux entrées :

- `/backend/llm/costs` : le coût global, tous sondages confondus, avec le
  détail par sondage et par modèle (admin) ;
- `/api/surveys/{id}/cost` : le coût d'un seul sondage, en JSON, appelé depuis
  le bouton présent sur chaque ligne de sondage.

Les montants proviennent de `services/llm_costs.py`, qui ne chiffre que ce
qu'il peut prouver : une synthèse sans compteur de tokens ou sans tarif connu
est comptée comme non chiffrable, jamais estimée.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from core.database import SessionDep
from core.dependencies import templates
from models import Survey
from routers.llm._access import current_roles, is_admin
from services.llm_costs import format_cost, global_cost, survey_cost

backend_router = APIRouter(tags=["Backend"], prefix="/backend")
api_router = APIRouter(tags=["API"], prefix="/api")

# Rôles autorisés à consulter le coût d'un sondage : ceux qui peuvent déjà
# lancer une génération. Le coût est une conséquence directe de cette action,
# il n'y a pas de raison de le cacher à qui la déclenche.
COST_ROLES = {"admin", "rp", "direction"}


@backend_router.get("/llm/costs", response_class=HTMLResponse)
def backend_costs(request: Request, session: SessionDep):
    """Coût global de toutes les synthèses, avec le détail par sondage."""
    if not is_admin(request, session):
        return RedirectResponse(url="/")

    total, per_survey, labels = global_cost(session)

    # Les sondages les plus coûteux en premier : c'est l'information qu'on
    # vient chercher sur cette page.
    surveys = sorted(
        (
            {
                "survey_id": survey_id,
                "survey": labels.get(survey_id),
                "report": report,
                "cost_label": format_cost(report["cost_usd"]),
            }
            for survey_id, report in per_survey.items()
        ),
        key=lambda item: item["report"]["cost_usd"],
        reverse=True,
    )

    models = sorted(
        (
            {"model": model, **entry, "cost_label": format_cost(entry["cost_usd"])}
            for model, entry in total["models"].items()
        ),
        key=lambda item: item["cost_usd"],
        reverse=True,
    )

    return templates.TemplateResponse(request, "backend/llm/costs.html", {
        "request": request,
        "total": total,
        "total_label": format_cost(total["cost_usd"]),
        "surveys": surveys,
        "models": models,
    })


@api_router.get("/surveys/{survey_id}/cost")
def api_survey_cost(request: Request, survey_id: int, session: SessionDep):
    """Coût des synthèses d'un sondage, en JSON.

    Appelé en fetch depuis le bouton de la ligne de sondage. Renvoie aussi le
    nombre de synthèses non chiffrables, pour que l'interface puisse dire que
    le total est partiel plutôt que de le présenter comme complet.
    """
    user, roles = current_roles(request, session)
    if not user:
        return JSONResponse({"ok": False, "error": "Non authentifié."}, status_code=401)
    if not COST_ROLES.intersection(roles):
        return JSONResponse({"ok": False, "error": "Accès refusé."}, status_code=403)

    if not session.get(Survey, survey_id):
        return JSONResponse(
            {"ok": False, "error": "Sondage introuvable."}, status_code=404
        )

    report = survey_cost(session, survey_id)

    return JSONResponse({
        "ok": True,
        "cost_label": format_cost(report["cost_usd"]),
        "cost_usd": report["cost_usd"],
        "input_tokens": report["input_tokens"],
        "output_tokens": report["output_tokens"],
        "summaries_total": report["summaries_total"],
        "summaries_priced": report["summaries_priced"],
        "summaries_unpriced": report["summaries_unpriced"],
        "models": sorted(report["models"].keys()),
    })
