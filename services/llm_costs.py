"""Calcul du coût réel des synthèses générées par LLM. Montants **en euros**.

Le coût est *mesuré*, pas estimé : il croise ce qui a été réellement consommé
au moment de la génération (`Summary.input_tokens` / `output_tokens`) avec la
grille tarifaire de `llm_model_prices`.

Deux composantes s'additionnent pour chaque synthèse :

- un **forfait par génération**, pour les modèles dont le coût ne se mesure pas
  au token. Le LLM auto-hébergé de l'école coûte 2 à 5 centimes « tout inclus »
  (GPU, électricité, amortissement) : auto-hébergé ne veut pas dire gratuit ;
- un **coût au token**, pour les fournisseurs facturant à la consommation.

Tous les totaux sont des **fourchettes** `(min, max)`. Quand un tarif est
connu exactement, min et max sont égaux et l'affichage se réduit de lui-même à
un seul montant : il n'y a donc pas deux chemins de calcul à maintenir, et une
imprécision d'entrée ne peut jamais se perdre en route.

Trois choses restent hors du chiffrage, et sont comptées à part plutôt
qu'approximées :

- les synthèses générées avant l'ajout des compteurs (colonnes NULL) — les
  tokens consommés n'ont jamais été enregistrés, l'historique est irrécupérable ;
- celles dont le fournisseur n'expose pas ses compteurs ;
- celles dont le modèle n'a aucun tarif enregistré.
"""

import logging

from sqlmodel import select

from models import LLMModelPrice, Prompt, Summary, Survey

logger = logging.getLogger("uvicorn.error")

TOKENS_PER_PRICE_UNIT = 1_000_000


def load_price_table(session):
    """Charge la grille tarifaire sous forme de dictionnaire de recherche.

    Deux clés par tarif : `(provider_id, model)` pour un tarif propre à un
    fournisseur, et `(None, model)` pour un tarif générique. Une seule requête
    suffit ainsi à chiffrer un lot entier de synthèses.
    """
    prices = {}
    for price in session.exec(select(LLMModelPrice)).all():
        prices[(price.provider_id, price.model)] = price
    return prices


def find_price(prices, provider_id, model):
    """Retourne le tarif applicable, ou None s'il n'y en a pas.

    Le tarif propre au fournisseur l'emporte sur le tarif générique : deux
    fournisseurs peuvent servir le même nom de modèle à des prix différents
    (une offre négociée, un revendeur), et le plus spécifique gagne.
    """
    if not model:
        return None
    return prices.get((provider_id, model)) or prices.get((None, model))


def summary_cost(summary_row, prices, provider_id=None):
    """Coût d'une synthèse, en euros, sous forme `(min, max)`.

    Retourne `None` quand le coût est inconnu — compteurs absents ou modèle
    sans tarif. À ne pas confondre avec `(0.0, 0.0)`, qui est un coût nul
    parfaitement connu.
    """
    if summary_row.input_tokens is None and summary_row.output_tokens is None:
        return None

    price = find_price(prices, provider_id, summary_row.model_used)
    if price is None:
        return None

    tokens_in = summary_row.input_tokens or 0
    tokens_out = summary_row.output_tokens or 0

    # La part au token est exacte : seul le forfait porte l'incertitude.
    token_cost = (
        tokens_in * price.input_price_per_mtok
        + tokens_out * price.output_price_per_mtok
    ) / TOKENS_PER_PRICE_UNIT

    return (
        price.flat_cost_min + token_cost,
        price.flat_cost_max + token_cost,
    )


def _blank_report():
    return {
        "cost_min": 0.0,
        "cost_max": 0.0,
        "input_tokens": 0,
        "output_tokens": 0,
        "summaries_priced": 0,  # synthèses effectivement chiffrées
        "summaries_unpriced": 0,  # compteurs ou tarif manquants
        "models": {},  # détail par modèle, pour l'affichage
    }


def _accumulate(report, summary_row, cost):
    """Ajoute une synthèse au rapport, chiffrée ou non."""
    model = summary_row.model_used or "modèle inconnu"
    entry = report["models"].setdefault(
        model,
        {"cost_min": 0.0, "cost_max": 0.0, "input_tokens": 0, "output_tokens": 0,
         "summaries": 0, "unpriced": 0},
    )
    entry["summaries"] += 1

    if cost is None:
        report["summaries_unpriced"] += 1
        entry["unpriced"] += 1
        return

    cost_min, cost_max = cost
    tokens_in = summary_row.input_tokens or 0
    tokens_out = summary_row.output_tokens or 0

    report["summaries_priced"] += 1
    report["cost_min"] += cost_min
    report["cost_max"] += cost_max
    report["input_tokens"] += tokens_in
    report["output_tokens"] += tokens_out

    entry["cost_min"] += cost_min
    entry["cost_max"] += cost_max
    entry["input_tokens"] += tokens_in
    entry["output_tokens"] += tokens_out


def _provider_by_prompt(session):
    """Associe chaque prompt à son fournisseur, pour le choix du tarif."""
    return {
        prompt.prompt_id: prompt.provider_id
        for prompt in session.exec(select(Prompt)).all()
    }


def survey_cost(session, survey_id):
    """Coût cumulé des synthèses réussies d'un sondage.

    Seules les synthèses en succès (`http_status == 200`) sont comptées : un
    appel en échec avant génération n'est pas facturé, et l'inclure gonflerait
    le total sans contrepartie.
    """
    prices = load_price_table(session)
    providers = _provider_by_prompt(session)

    report = _blank_report()
    rows = session.exec(
        select(Summary).where(
            Summary.survey_id == survey_id,
            Summary.http_status == 200,
        )
    ).all()

    for row in rows:
        provider_id = providers.get(row.prompt_id)
        _accumulate(report, row, summary_cost(row, prices, provider_id))

    report["summaries_total"] = len(rows)
    return report


def global_cost(session):
    """Coût cumulé de toutes les synthèses, avec le détail par sondage.

    Une seule passe sur la table : les grilles tarifaires et la correspondance
    prompt/fournisseur sont chargées une fois, pas une fois par sondage.
    """
    prices = load_price_table(session)
    providers = _provider_by_prompt(session)

    total = _blank_report()
    per_survey = {}

    rows = session.exec(select(Summary).where(Summary.http_status == 200)).all()

    for row in rows:
        provider_id = providers.get(row.prompt_id)
        cost = summary_cost(row, prices, provider_id)

        _accumulate(total, row, cost)

        survey_report = per_survey.setdefault(row.survey_id, _blank_report())
        _accumulate(survey_report, row, cost)
        survey_report["summaries_total"] = survey_report.get("summaries_total", 0) + 1

    total["summaries_total"] = len(rows)

    # Libellé des sondages, pour que le tableau soit lisible sans jointure
    # supplémentaire côté template.
    labels = {survey.survey_id: survey for survey in session.exec(select(Survey)).all()}

    return total, per_survey, labels


def format_amount(amount_eur):
    """Rend un montant en euros, à la française (virgule décimale).

    Une synthèse coûte quelques centimes : arrondir à deux décimales
    afficherait « 0,00 € » pour un petit lot. On garde donc plus de décimales
    tant que le montant est petit, sans jamais dépasser ce que la donnée
    supporte.
    """
    if amount_eur is None:
        return "—"
    if amount_eur == 0:
        return "0,00 €"
    if amount_eur < 0.01:
        text = f"{amount_eur:.4f}"
    else:
        text = f"{amount_eur:.2f}"
    return text.replace(".", ",") + " €"


def format_cost(cost_min, cost_max=None):
    """Rend une fourchette de coût.

    Se réduit à un seul montant quand les deux bornes coïncident : afficher
    « 1,40 € à 1,40 € » ferait croire à une incertitude inexistante, alors
    qu'afficher « 1,40 € » pour une vraie fourchette masquerait l'inverse.
    """
    if cost_min is None:
        return "—"
    if cost_max is None or abs(cost_max - cost_min) < 1e-9:
        return format_amount(cost_min)
    return f"{format_amount(cost_min)} à {format_amount(cost_max)}"
