"""Calcul du coût réel des synthèses générées par LLM.

Le coût est *mesuré*, pas estimé : il croise les compteurs de tokens renvoyés
par le fournisseur au moment de la génération (`Summary.input_tokens` /
`output_tokens`) avec la grille tarifaire de `llm_model_prices`.

Deux conséquences assumées :

- une synthèse dont le modèle n'a pas de tarif enregistré n'est pas chiffrée à
  zéro, elle est comptée à part comme « non chiffrable ». Un montant inventé
  serait plus nuisible qu'un montant absent, puisqu'il s'afficherait comme un
  vrai ;
- les synthèses générées avant l'ajout des compteurs (colonnes NULL) tombent
  dans la même catégorie. L'historique ne peut pas être reconstitué : les
  tokens consommés n'ont jamais été enregistrés.

Les tarifs sont publiés par million de tokens, et stockés tels quels : la
division n'a lieu qu'ici, au dernier moment.
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
    """Coût d'une synthèse en dollars, ou None si non chiffrable.

    `None` signifie « on ne sait pas » — compteurs absents ou modèle sans
    tarif — et doit rester distinct de 0.0, qui est le coût bien réel d'un
    modèle auto-hébergé.
    """
    if summary_row.input_tokens is None and summary_row.output_tokens is None:
        return None

    price = find_price(prices, provider_id, summary_row.model_used)
    if price is None:
        return None

    tokens_in = summary_row.input_tokens or 0
    tokens_out = summary_row.output_tokens or 0

    return (
        tokens_in * price.input_price_per_mtok
        + tokens_out * price.output_price_per_mtok
    ) / TOKENS_PER_PRICE_UNIT


def _blank_report():
    return {
        "cost_usd": 0.0,
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
        {"cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0,
         "summaries": 0, "unpriced": 0},
    )
    entry["summaries"] += 1

    if cost is None:
        report["summaries_unpriced"] += 1
        entry["unpriced"] += 1
        return

    tokens_in = summary_row.input_tokens or 0
    tokens_out = summary_row.output_tokens or 0

    report["summaries_priced"] += 1
    report["cost_usd"] += cost
    report["input_tokens"] += tokens_in
    report["output_tokens"] += tokens_out

    entry["cost_usd"] += cost
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

    rows = session.exec(
        select(Summary).where(Summary.http_status == 200)
    ).all()

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
    labels = {}
    for survey in session.exec(select(Survey)).all():
        labels[survey.survey_id] = survey

    return total, per_survey, labels


def format_cost(cost_usd):
    """Rend un montant en dollars lisible, sans fausse précision.

    Une synthèse coûte souvent une fraction de centime : arrondir à deux
    décimales afficherait « $0.00 » pour une campagne entière. On garde donc
    assez de décimales pour que les petits montants restent visibles.
    """
    if cost_usd is None:
        return "—"
    if cost_usd == 0:
        return "$0.00"
    if cost_usd < 0.01:
        return f"${cost_usd:.4f}"
    return f"${cost_usd:.2f}"
