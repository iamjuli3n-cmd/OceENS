"""Grille tarifaire des modèles LLM (admin uniquement). Montants en euros.

Les tarifs vivent en base plutôt qu'en dur dans le code : ils changent au gré
des fournisseurs, et chaque déploiement peut brancher ses propres modèles.

Deux composantes par tarif, additionnées au moment du calcul :

- un forfait par génération, saisi en fourchette (le LLM de l'école coûte 2 à
  5 centimes « tout inclus ») ;
- un prix au million de tokens, pour les fournisseurs facturant à l'usage.

Les fournisseurs publiant en dollars, le formulaire accepte les deux devises et
convertit une fois pour toutes à l'enregistrement : tout ce qui est stocké est
en euros.

Aucun tarif n'est deviné : un modèle sans ligne ici est signalé comme non
chiffrable par `services/llm_costs.py`, jamais estimé.
"""

from datetime import date

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import select

from core.database import SessionDep
from core.dependencies import templates
from models import LLMModelPrice, LLMProvider
from routers.llm._access import is_admin
from services.llm_costs import format_amount, format_cost
from services.settings_store import USD_TO_EUR_KEY, get_usd_to_eur, set_setting

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
    prices = session.exec(select(LLMModelPrice).order_by(LLMModelPrice.model)).all()

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
            "flat_label": (
                format_cost(price.flat_cost_min, price.flat_cost_max)
                if price.flat_cost_max
                else "—"
            ),
            "input_label": format_amount(price.input_price_per_mtok),
            "output_label": format_amount(price.output_price_per_mtok),
        }
        for price in prices
    ]

    return templates.TemplateResponse(request, "backend/llm/prices.html", {
        "request": request,
        "prices": rows,
        "providers": list(providers.values()),
        "usd_to_eur": get_usd_to_eur(session),
    })


def _parse_amount(value):
    """Convertit une saisie monétaire, en tolérant la virgule décimale.

    Le formulaire est utilisé par des francophones : « 0,035 » doit être
    accepté au même titre que « 0.035 », sinon la saisie échoue de façon
    incompréhensible. Retourne `None` si la valeur n'est pas un nombre positif.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return 0.0
    try:
        parsed = float(text.replace(",", "."))
    except ValueError:
        return None
    return parsed if parsed >= 0 else None


@backend_router.post("/llm/settings/rate")
def save_rate(request: Request, session: SessionDep, usd_to_eur: str = Form(...)):
    """Enregistre le taux de conversion dollar → euro.

    Le taux ne s'applique qu'aux saisies futures : les tarifs déjà convertis
    restent inchangés, pour qu'un coût déjà constaté ne bouge pas
    rétroactivement.
    """
    if not is_admin(request, session):
        return RedirectResponse(url="/", status_code=403)

    rate = _parse_amount(usd_to_eur)
    if not rate:
        return RedirectResponse(
            url="/backend/llm/prices?error=taux_invalide", status_code=303
        )

    set_setting(
        session,
        USD_TO_EUR_KEY,
        rate,
        description="Taux dollar → euro appliqué aux tarifs saisis en dollars.",
    )
    return RedirectResponse(url="/backend/llm/prices?success=taux_enregistre", status_code=303)


@backend_router.post("/llm/prices/save")
def save_price(
    request: Request,
    session: SessionDep,
    model: str = Form(...),
    flat_cost_min: str = Form("0"),
    flat_cost_max: str = Form("0"),
    input_price_per_mtok: str = Form("0"),
    output_price_per_mtok: str = Form("0"),
    currency: str = Form("EUR"),  # devise de saisie : EUR ou USD
    provider_id: str = Form(""),  # vide = tarif générique
    note: str = Form(""),
    price_id: str = Form(""),  # vide = création
):
    """Crée ou met à jour un tarif, en convertissant en euros si besoin.

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

    amounts = {
        "flat_min": _parse_amount(flat_cost_min),
        "flat_max": _parse_amount(flat_cost_max),
        "price_in": _parse_amount(input_price_per_mtok),
        "price_out": _parse_amount(output_price_per_mtok),
    }
    if any(value is None for value in amounts.values()):
        return RedirectResponse(
            url="/backend/llm/prices?error=montant_invalide", status_code=303
        )

    # Une borne haute inférieure à la borne basse produirait une fourchette
    # inversée, donc des totaux incohérents. Un forfait exact se saisit avec
    # une seule valeur : on aligne alors le max sur le min.
    if not amounts["flat_max"]:
        amounts["flat_max"] = amounts["flat_min"]
    if amounts["flat_max"] < amounts["flat_min"]:
        return RedirectResponse(
            url="/backend/llm/prices?error=fourchette_inversee", status_code=303
        )

    # Conversion unique à la saisie : tout ce qui est stocké est en euros.
    conversion_note = ""
    if currency.upper() == "USD":
        rate = get_usd_to_eur(session)
        amounts = {key: value * rate for key, value in amounts.items()}
        conversion_note = f"converti de USD au taux {rate} le {date.today():%d/%m/%Y}"

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
    row.flat_cost_min = amounts["flat_min"]
    row.flat_cost_max = amounts["flat_max"]
    row.input_price_per_mtok = amounts["price_in"]
    row.output_price_per_mtok = amounts["price_out"]

    note = note.strip()
    # La trace de conversion est conservée : sans elle, impossible de savoir
    # plus tard si un montant en base a été converti, et à quel taux.
    row.note = " — ".join(part for part in (note, conversion_note) if part) or None

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
