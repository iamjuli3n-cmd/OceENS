"""Client LLM multi-fournisseur utilisé par la génération des synthèses.

Ce module isole tout ce qui touche au dialogue HTTP avec un serveur de modèle
de langage. Le daemon ne connaît plus ni URL, ni format de payload, ni schéma
de réponse : il passe un `LLMProvider` et récupère un triplet normalisé.

Trois adaptateurs sont fournis :

- ``ollama``    : l'API du serveur local de l'école (comportement historique) ;
- ``openai``    : ``/v1/chat/completions``, couvre aussi les endpoints
                  compatibles OpenAI (vLLM, Groq, Mistral, LM Studio) ;
- ``anthropic`` : ``/v1/messages``.

Règle non négociable : la clé d'API n'existe que dans l'environnement. Le
fournisseur ne porte que le *nom* de la variable (`api_key_env`), et ce nom est
validé contre une liste blanche avant toute résolution — sans quoi un
administrateur pourrait pointer un fournisseur vers `SECRET_KEY` ou
`ENTRA_CLIENT_SECRET` et faire partir le secret en en-tête d'autorisation vers
un serveur tiers.
"""

import logging
import os
import re
import time
from datetime import datetime, timezone

import requests

logger = logging.getLogger("uvicorn.error")


# Types d'API reconnus. Toute valeur hors de cette liste est refusée à la
# création d'un fournisseur comme à l'appel.
API_TYPES = ("ollama", "openai", "anthropic")

# Noms de variables d'environnement acceptables pour `api_key_env`.
_API_KEY_ENV_PATTERN = re.compile(r"^(LLM_[A-Z0-9_]+|[A-Z0-9_]+_API_KEY)$")

# Refus explicite, même si le motif ci-dessus venait à s'élargir.
_API_KEY_ENV_DENIED = frozenset(
    {
        "SECRET_KEY",
        "ENTRA_CLIENT_ID",
        "ENTRA_CLIENT_SECRET",
        "ENTRA_TENANT_ID",
        "REDIRECT_URI",
        "ALLOWED_DOMAINS",
    }
)

DEFAULT_TIMEOUT = 120
DEFAULT_SEED = 42

# Anthropic impose `max_tokens`. Les synthèses de verbatims sont courtes ;
# 4096 laisse de la marge sans autoriser une réponse hors de proportion.
DEFAULT_MAX_TOKENS = 4096

ANTHROPIC_VERSION = "2023-06-01"

# En dessous de ce seuil, la durée mesurée côté client ne vient pas d'une
# génération réelle : c'est une réponse servie par le cache. Calculer un débit
# dessus afficherait des millions de tokens/s à l'utilisateur.
_MIN_DURATION_FOR_RATE = 0.05


class LLMConfigError(Exception):
    """Fournisseur mal configuré : type inconnu, clé absente ou non autorisée.

    Distinct d'un échec HTTP : il n'y a rien à réessayer, c'est la
    configuration qu'il faut corriger.
    """


# ─── Aides ────────────────────────────────────────────────────────────────────


def is_allowed_api_key_env(name):
    """Vrai si `name` est un nom de variable d'environnement acceptable.

    Utilisé à deux endroits : à la validation du formulaire d'administration et
    juste avant la résolution de la clé. Les deux doivent appliquer exactement
    la même règle, d'où la fonction unique.
    """
    if not name:
        return False
    name = name.strip()
    if name in _API_KEY_ENV_DENIED:
        return False
    return bool(_API_KEY_ENV_PATTERN.match(name))


def resolve_api_key(provider):
    """Retourne la valeur de la clé du fournisseur, ou lève `LLMConfigError`.

    Un fournisseur sans `api_key_env` est accepté : certains serveurs Ollama
    auto-hébergés n'exigent aucune authentification.
    """
    name = (provider.api_key_env or "").strip()
    if not name:
        return None

    if not is_allowed_api_key_env(name):
        raise LLMConfigError(
            f"Nom de variable d'environnement non autorisé pour la clé d'API : {name}"
        )

    value = os.getenv(name)
    if not value:
        # Le nom est journalisé, jamais la valeur.
        raise LLMConfigError(
            f"La variable d'environnement {name} est absente ou vide. "
            "Ajoutez-la au .env puis redémarrez le daemon."
        )
    return value


def has_api_key(provider):
    """Indique si la clé du fournisseur est présente, sans révéler sa valeur.

    Alimente l'indicateur « clé présente / absente » de l'administration.
    """
    try:
        resolve_api_key(provider)
    except LLMConfigError:
        return False
    return True


def _base(provider):
    """Renvoie l'URL de base du fournisseur, sans slash final."""
    return (provider.base_url or "").rstrip("/")


def _url(provider, path):
    """Concatène base_url et chemin sans dupliquer un éventuel préfixe `/v1`."""
    base = _base(provider)
    if path.startswith("/v1/") and base.endswith("/v1"):
        path = path[3:]
    return f"{base}{path}"


def _check_api_type(provider):
    if provider.api_type not in API_TYPES:
        raise LLMConfigError(
            f"Type d'API inconnu : {provider.api_type!r} "
            f"(attendu : {', '.join(API_TYPES)})"
        )


def _headers(provider):
    """En-têtes d'authentification propres à chaque fournisseur."""
    _check_api_type(provider)
    key = resolve_api_key(provider)
    headers = {"Content-Type": "application/json"}

    if provider.api_type == "anthropic":
        if key:
            headers["x-api-key"] = key
        headers["anthropic-version"] = ANTHROPIC_VERSION
    elif key:
        headers["Authorization"] = f"Bearer {key}"

    return headers


def _metadata(model, created_at, duration_s, eval_count):
    """Forme normalisée des métadonnées, commune aux trois adaptateurs."""
    tokens_per_s = None
    if eval_count and duration_s and duration_s >= _MIN_DURATION_FOR_RATE:
        tokens_per_s = eval_count / duration_s

    return {
        "model": model,
        "created_at": created_at,
        "duration_s": duration_s,
        "eval_count": eval_count,
        "tokens_per_s": tokens_per_s,
    }


def format_metadata_text(metadata):
    """Rend les métadonnées sous la forme affichée à l'utilisateur.

    Conserve le libellé historique produit par le daemon, en dégradant
    proprement quand un fournisseur n'expose pas le compte de tokens.
    """
    model = metadata.get("model") or "modèle inconnu"

    created_at = metadata.get("created_at")
    if created_at:
        date_pretty = created_at.strftime("%d/%m/%Y %H:%M")
    else:
        date_pretty = datetime.now().strftime("%d/%m/%Y %H:%M")

    text = f"Réponse synthétisée par {model} le {date_pretty}"

    duration_s = metadata.get("duration_s")
    if duration_s and duration_s >= _MIN_DURATION_FOR_RATE:
        text += f" en {duration_s:.1f}s"

    tokens_per_s = metadata.get("tokens_per_s")
    if tokens_per_s:
        text += f" ({tokens_per_s:.1f} token/s)"

    return text


def _parse_iso(value):
    """Parse une date ISO 8601, en tolérant le suffixe `Z`."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _error_metadata(response):
    """Extrait le corps d'une réponse en erreur, pour le diagnostic.

    Les fournisseurs renvoient un message utile ("invalid_api_key",
    "model_not_found"…) : le perdre laisserait l'administrateur devant un
    simple code HTTP.
    """
    try:
        return response.json()
    except ValueError:
        return {"body": (response.text or "")[:500]}


def _post(provider, path, payload, session, timeout):
    """POST commun aux trois adaptateurs, avec chronométrage côté client.

    Le chronomètre sert de repli quand le fournisseur n'expose pas de durée
    (OpenAI et Anthropic) : mieux vaut une durée mesurée qu'un débit inventé.
    """
    http = session or requests
    started = time.monotonic()
    response = http.post(
        _url(provider, path),
        headers=_headers(provider),
        json=payload,
        timeout=timeout,
    )
    return response, time.monotonic() - started


# ─── Adaptateurs : vérification du modèle ─────────────────────────────────────


def _list_models(provider, session):
    """Retourne la liste des identifiants de modèles exposés par le fournisseur."""
    http = session or requests

    if provider.api_type == "ollama":
        path, extract = "/api/tags", lambda d: [m["name"] for m in d.get("models", [])]
    else:
        # OpenAI et Anthropic exposent tous deux GET /v1/models -> {"data": [...]}
        path, extract = "/v1/models", lambda d: [m["id"] for m in d.get("data", [])]

    response = http.get(_url(provider, path), headers=_headers(provider), timeout=30)
    response.raise_for_status()
    return extract(response.json())


def list_models(provider, session=None):
    """Retourne la liste des modèles exposés par le fournisseur (test de connexion).

    Wrapper public de `_list_models` : valide d'abord le type d'API. Sert au
    bouton « Tester la connexion » de l'administration, qui vérifie ainsi que
    l'URL et la clé du fournisseur répondent. Lève `LLMConfigError` si mal
    configuré, laisse remonter les exceptions `requests` si serveur injoignable.
    """
    _check_api_type(provider)
    return _list_models(provider, session)


def check_model(provider, model, session=None):
    """Vrai si `model` est disponible chez `provider`.

    Lève `LLMConfigError` si le fournisseur est mal configuré, et laisse
    remonter les exceptions `requests` en cas de serveur injoignable : ces deux
    situations doivent être distinguées par l'appelant.
    """
    _check_api_type(provider)
    available = _list_models(provider, session)

    if model in available:
        return True

    logger.warning(
        "Modèle %s introuvable chez %s (%d modèles disponibles)",
        model,
        provider.name,
        len(available),
    )
    return False


# ─── Adaptateurs : génération ─────────────────────────────────────────────────


def _ask_ollama(provider, model, prompt, session, timeout, seed):
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"seed": seed},
    }
    response, elapsed = _post(provider, "/api/generate", payload, session, timeout)

    if response.status_code != 200:
        return None, _error_metadata(response), response.status_code

    data = response.json()
    # `context` est le vecteur d'état du modèle : volumineux et inutile ici.
    data.pop("context", None)

    text = data.get("response")
    if not text:
        return None, data, response.status_code

    # Ollama compte en nanosecondes.
    total_duration = data.get("total_duration")
    duration_s = total_duration / 1_000_000_000 if total_duration else elapsed

    eval_count = data.get("eval_count")
    eval_duration = data.get("eval_duration")
    metadata = _metadata(
        model=data.get("model") or model,
        created_at=_parse_iso(data.get("created_at")),
        duration_s=duration_s,
        eval_count=eval_count,
    )
    # Le débit d'Ollama se calcule sur la seule phase de génération, pas sur la
    # durée totale : on écrase la valeur par défaut quand l'info est présente.
    # Cette durée vient du serveur, elle reste donc juste même servie du cache.
    if eval_count and eval_duration:
        metadata["tokens_per_s"] = eval_count / (eval_duration / 1_000_000_000)

    return text, metadata, response.status_code


def _ask_openai(provider, model, prompt, session, timeout, seed):
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "seed": seed,
    }
    response, elapsed = _post(
        provider, "/v1/chat/completions", payload, session, timeout
    )

    if response.status_code != 200:
        return None, _error_metadata(response), response.status_code

    data = response.json()
    choices = data.get("choices") or []
    text = choices[0].get("message", {}).get("content") if choices else None
    if not text:
        return None, data, response.status_code

    created = data.get("created")
    created_at = (
        datetime.fromtimestamp(created, tz=timezone.utc) if created else None
    )

    metadata = _metadata(
        model=data.get("model") or model,
        created_at=created_at,
        duration_s=elapsed,
        eval_count=(data.get("usage") or {}).get("completion_tokens"),
    )
    return text, metadata, response.status_code


def _ask_anthropic(provider, model, prompt, session, timeout, seed):
    # Anthropic n'expose pas de paramètre `seed` : la reproductibilité est
    # approchée par température nulle.
    payload = {
        "model": model,
        "max_tokens": DEFAULT_MAX_TOKENS,
        "temperature": 0,
        "messages": [{"role": "user", "content": prompt}],
    }
    response, elapsed = _post(provider, "/v1/messages", payload, session, timeout)

    if response.status_code != 200:
        return None, _error_metadata(response), response.status_code

    data = response.json()
    blocks = data.get("content") or []
    text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
    if not text:
        return None, data, response.status_code

    metadata = _metadata(
        model=data.get("model") or model,
        created_at=None,  # non fourni par l'API
        duration_s=elapsed,
        eval_count=(data.get("usage") or {}).get("output_tokens"),
    )
    return text, metadata, response.status_code


_ADAPTERS = {
    "ollama": _ask_ollama,
    "openai": _ask_openai,
    "anthropic": _ask_anthropic,
}


def ask_model(provider, model, prompt, session=None, timeout=DEFAULT_TIMEOUT, seed=DEFAULT_SEED):
    """Interroge le fournisseur et retourne `(texte, métadonnées, code HTTP)`.

    `texte` vaut `None` quand la génération a échoué ; `métadonnées` contient
    alors la réponse brute du fournisseur, utile au diagnostic. Lève
    `LLMConfigError` si le fournisseur est mal configuré.
    """
    _check_api_type(provider)
    return _ADAPTERS[provider.api_type](
        provider, model, prompt, session, timeout, seed
    )


def build_cache_session(path="cache_llm.db"):
    """Construit la session HTTP mise en cache utilisée par le daemon.

    `match_headers=True` fait entrer les en-têtes d'authentification dans la
    clé de cache : deux fournisseurs distincts partageant une même URL ne se
    marchent donc pas dessus.
    """
    import requests_cache

    return requests_cache.CachedSession(
        path,
        allowable_methods=["GET", "POST"],
        expire_after=requests_cache.NEVER_EXPIRE,
        match_headers=True,
    )
