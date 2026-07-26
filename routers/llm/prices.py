"""Grille tarifaire des modèles LLM (admin uniquement).

Les tarifs vivent en base plutôt qu'en dur dans le code : ils changent au gré
des fournisseurs, et chaque déploiement peut brancher ses propres modèles. Un
écran d'édition évite d'avoir à livrer une nouvelle version à chaque révision
de prix.

Aucun tarif n'est deviné : un modèle sans ligne ici est signalé comme non
chiffrable par `services/llm_costs.py`, jamais estimé.
"""

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import select

from core.database import SessionDep
from core.dependencies import templates
from models import LLMModelPrice, LLMProvider
from routers.llm._access import is_admin

backend_router = APIRouter(tags=["Backend"], prefix="/backend")


def _providers_by_id(session):
    """Fournisseurs indexés par identifiant, pour afficher leur nom."""
    return {
        provider.provider_id: provider
        for provider in session.exec(select(LLMProvider)).all()
    }


@backend_router.get("/llm/prices", response_class=HTMLResponse)
def backend_prices(request: Request, session: SessionDep):
    """Liste la grille tarifaire, tous fournisseurs confondus."""
    if not is_admin(request, session):
        return RedirectResponse(url="/")

    providers = _providers_by_id(session)
    prices = session.exec(
        select(LLMModelPrice).order_by(LLMModelPrice.model)
    ).all()

    rows = [
        {
            "price": price,
            # Un tarif sans fournisseur s'applique à tous : le libellé doit le
            # dire, sinon la ligne paraît incomplète.
            "provider_name": (
                providers[price.provider_id].name
                if price.provider_id in providers
                else "Tous les fournisseurs"
            ),
        }
        for price in prices
    ]

    return templates.TemplateResponse(request, "backend/llm/prices.html", {
        "request": request,
        "prices": rows,
        "providers": list(providers.values()),
    })


def _parse_price(value):
    """Convertit une saisie de prix, en tolérant la virgule décimale.

    Le formulaire est utilisé par des francophones : « 3,50 » doit être accepté
    au même titre que « 3.50 », sinon la saisie échoue de façon incompréhensible.
    Retourne `None` si la valeur n'est pas un nombre positif.
    """
    if value is None:
        return None
    try:
        parsed = float(str(value).strip().replace(",", "."))
    except ValueError:
        return None
    return parsed if parsed >= 0 else None


@backend_router.post("/llm/prices/save")
def save_price(
    request: Request,
    session: SessionDep,
    model: str = Form(...),
    input_price_per_mtok: str = Form(...),
    output_price_per_mtok: str = Form(...),
    provider_id: str = Form(""),  # vide = tarif générique
    note: str = Form(""),
    price_id: str = Form(""),  # vide = création
):
    """Crée ou met à jour un tarif.

    Un seul point d'entrée pour les deux opérations : le formulaire de création
    et celui d'édition ne diffèrent que par la présence de `price_id`, et les
    règles de validation sont identiques.
    """
    if not is_admin(request, session):
        return RedirectResponse(url="/", status_code=403)

    model = (model or "").strip()
    if not model:
        return RedirectResponse(
            url="/backend/llm/prices?error=modele_requis", status_code=303
        )

    price_in = _parse_price(input_price_per_mtok)
    price_out = _parse_price(output_price_per_mtok)
    if price_in is None or price_out is None:
        return RedirectResponse(
            url="/backend/llm/prices?error=prix_invalide", status_code=303
        )

    # Chaîne vide = tarif générique (pas de fournisseur particulier).
    provider = int(provider_id) if provider_id.strip() else None
    if provider is not None and not session.get(LLMProvider, provider):
        return RedirectResponse(
            url="/backend/llm/prices?error=fournisseur_introuvable", status_code=303
        )

    if price_id.strip():
        row = session.get(LLMModelPrice, int(price_id))
        if not row:
            return RedirectResponse(
                url="/backend/llm/prices?error=introuvable", status_code=303
            )
    else:
        # Refuser un doublon : deux tarifs pour le même couple rendraient le
        # coût dépendant de l'ordre de lecture, donc non reproductible.
        existing = session.exec(
            select(LLMModelPrice).where(
                LLMModelPrice.model == model,
                LLMModelPrice.provider_id == provider,
            )
        ).first()
        if existing:
            return RedirectResponse(
                url="/backend/llm/prices?error=tarif_deja_defini", status_code=303
            )
        row = LLMModelPrice()

    row.model = model
    row.provider_id = provider
    row.input_price_per_mtok = price_in
    row.output_price_per_mtok = price_out
    row.note = note.strip() or None

    session.add(row)
    session.commit()

    return RedirectResponse(url="/backend/llm/prices?success=enregistre", status_code=303)


@backend_router.post("/llm/prices/{price_id}/delete")
def delete_price(request: Request, price_id: int, session: SessionDep):
    """Supprime un tarif.

    Sans verrou : contrairement à un fournisseur, un tarif n'est référencé par
    aucune ligne. Le supprimer rend simplement les synthèses concernées non
    chiffrables, ce qui est réversible en le recréant.
    """
    if not is_admin(request, session):
        return RedirectResponse(url="/", status_code=403)

    row = session.get(LLMModelPrice, price_id)
    if row:
        session.delete(row)
        session.commit()

    return RedirectResponse(url="/backend/llm/prices?success=supprime", status_code=303)
