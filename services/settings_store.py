"""Lecture et écriture des réglages applicatifs (table `settings`).

Aujourd'hui un seul réglage : le taux de change dollar → euro. Les
fournisseurs LLM publient en dollars, l'application compte en euros, et le taux
ne peut être ni codé en dur (il bouge) ni récupéré automatiquement (on ne veut
pas d'appel réseau sortant au démarrage, et un taux du jour rendrait les
montants non reproductibles d'une consultation à l'autre).

Le taux ne sert qu'à la **saisie** : un tarif entré en dollars est converti une
fois puis stocké en euros. Modifier le taux plus tard ne réécrit donc pas les
tarifs existants — ce qui est voulu : un tarif déjà appliqué à des synthèses
passées ne doit pas changer rétroactivement.
"""

import logging

from models import Setting

logger = logging.getLogger("uvicorn.error")

USD_TO_EUR_KEY = "usd_to_eur_rate"

# Valeur de départ, à vérifier et ajuster dans l'administration. Ce n'est pas
# un taux « officiel » : c'est un point de départ explicite, préférable à un
# taux codé en dur invisible ou à une conversion silencieusement omise.
DEFAULT_USD_TO_EUR = 0.92


def get_setting(session, key, default=None):
    """Retourne la valeur texte d'un réglage, ou `default` s'il est absent."""
    row = session.get(Setting, key)
    return row.value if row and row.value is not None else default


def set_setting(session, key, value, description=None):
    """Crée ou met à jour un réglage."""
    row = session.get(Setting, key)
    if row is None:
        row = Setting(key=key, description=description)
    row.value = str(value)
    if description:
        row.description = description
    session.add(row)
    session.commit()
    return row


def get_usd_to_eur(session):
    """Taux de conversion dollar → euro, avec repli sur la valeur par défaut.

    Un réglage illisible (saisie corrompue, valeur vide) ne doit pas empêcher
    l'affichage des coûts : on journalise et on retombe sur la valeur par
    défaut plutôt que de propager une exception jusqu'à la page.
    """
    raw = get_setting(session, USD_TO_EUR_KEY)
    if raw is None:
        return DEFAULT_USD_TO_EUR

    try:
        rate = float(str(raw).replace(",", "."))
    except ValueError:
        logger.warning(
            "Taux %s illisible (%r) : repli sur %s", USD_TO_EUR_KEY, raw, DEFAULT_USD_TO_EUR
        )
        return DEFAULT_USD_TO_EUR

    if rate <= 0:
        logger.warning("Taux %s invalide (%s) : repli sur %s", USD_TO_EUR_KEY, rate,
                       DEFAULT_USD_TO_EUR)
        return DEFAULT_USD_TO_EUR

    return rate
