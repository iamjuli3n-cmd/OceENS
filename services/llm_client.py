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

# Prompt et plafond du « ping » de génération (voir `ping_generation`) : il doit
# coûter le strict minimum, sa réponse n'est jamais lue.
PING_PROMPT = "ping"
PING_MAX_TOKENS = 1

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


# ─── Normalisation des erreurs de fournisseur ─────────────────────────────────
#
# Chaque fournisseur signale ses pannes dans un format différent : le crédit
# épuisé est un 429 `insufficient_quota` chez OpenAI, un 400 « Your credit
# balance is too low » chez Anthropic. Stocker ce JSON brut dans
# `Summary.metadata_text` laissait l'utilisateur devant une trace illisible,
# alors que le problème — « il faut recharger le compte » — se règle en une
# phrase. On classe donc l'erreur avant de l'écrire.

ERROR_QUOTA = "quota"  # crédit épuisé / facturation : rien ne repassera seul
ERROR_RATE_LIMIT = "rate_limit"  # débit dépassé : transitoire, réessayable
ERROR_AUTH = "auth"  # clé refusée
ERROR_MODEL = "model"  # modèle inconnu du fournisseur
ERROR_SERVER = "server"  # panne côté fournisseur
ERROR_UNKNOWN = "unknown"

# Résumé court par catégorie, réutilisable partout (synthèses, test de
# connexion). Le détail renvoyé par le fournisseur s'y ajoute quand il existe.
ERROR_LABELS = {
    ERROR_QUOTA: (
        "⚠️ Crédit ou quota épuisé chez le fournisseur : la clé est valide mais "
        "le compte ne peut plus générer. Rechargez le compte ou choisissez un "
        "autre fournisseur."
    ),
    ERROR_RATE_LIMIT: (
        "⏳ Limite de débit atteinte chez le fournisseur. Réessayez dans "
        "quelques minutes."
    ),
    ERROR_AUTH: (
        "🔑 Clé d'API refusée par le fournisseur. Vérifiez la variable "
        "d'environnement configurée."
    ),
    ERROR_MODEL: "❓ Modèle inconnu du fournisseur.",
    ERROR_SERVER: (
        "🛠️ Le fournisseur a renvoyé une erreur interne. Réessayez plus tard."
    ),
    ERROR_UNKNOWN: "Échec de l'appel au fournisseur.",
}

# Repérage du crédit épuisé dans le code/type d'erreur puis, à défaut, dans le
# message. Deux passes séparées car un message de limite de débit mentionne
# parfois le mot « quota » sans que le compte soit à sec.
_QUOTA_CODES = ("insufficient_quota", "billing", "payment", "credit", "quota")
_QUOTA_MESSAGE = re.compile(
    r"credit balance|insufficient (quota|funds|credit)|exceeded your current quota"
    r"|billing|payment required|plans? & billing|solde|crédit",
    re.IGNORECASE,
)
_RATE_LIMIT_CODES = ("rate_limit", "too_many_requests", "overloaded")
_AUTH_CODES = ("invalid_api_key", "authentication", "permission", "unauthorized")
_MODEL_CODES = ("model_not_found", "not_found", "does not exist", "unknown model")

# Au-delà, le détail du fournisseur encombre l'affichage sans aider.
_DETAIL_MAX_LENGTH = 200


def _error_fields(payload):
    """Extrait `(code, message)` d'un corps d'erreur, quel qu'en soit le format.

    Formats rencontrés : ``{"error": {"code"|"type", "message"}}`` (OpenAI,
    Groq, Anthropic), ``{"error": "..."}`` (Ollama), ``{"message": "..."}``
    (Mistral), ``{"detail": "..."}`` (vLLM), et le ``{"body": "..."}`` produit
    par `_error_metadata` quand la réponse n'est même pas du JSON.
    """
    if not isinstance(payload, dict):
        return "", str(payload or "")

    error = payload.get("error")
    if isinstance(error, dict):
        code = error.get("code") or error.get("type") or ""
        message = error.get("message") or ""
    elif isinstance(error, str):
        code, message = "", error
    else:
        code, message = "", ""

    if not message:
        # Certains fournisseurs (Anthropic) portent le type à la racine.
        message = payload.get("message") or payload.get("detail") or payload.get("body") or ""
    if not code:
        code = payload.get("type") or payload.get("code") or ""

    return str(code), str(message)


def classify_error(status_code, payload):
    """Range une réponse en erreur dans l'une des catégories `ERROR_*`.

    Le code HTTP seul ne suffit pas : OpenAI renvoie 429 aussi bien pour un
    débit dépassé (transitoire) que pour un crédit épuisé (bloquant), et
    Anthropic annonce le crédit épuisé en 400. On regarde donc d'abord ce que
    dit le corps de la réponse, le code HTTP ne servant que de repli.
    """
    code, message = _error_fields(payload)
    code_lower = code.lower()

    # Débit avant quota : « rate_limit » est explicite, alors qu'un message de
    # limite de débit peut mentionner le mot « quota » au passage.
    if any(needle in code_lower for needle in _RATE_LIMIT_CODES):
        return ERROR_RATE_LIMIT

    if any(needle in code_lower for needle in _QUOTA_CODES):
        return ERROR_QUOTA
    if _QUOTA_MESSAGE.search(message):
        return ERROR_QUOTA
    # 402 Payment Required : sans ambiguïté, quel que soit le corps.
    if status_code == 402:
        return ERROR_QUOTA

    if any(needle in code_lower for needle in _AUTH_CODES) or status_code in (401, 403):
        return ERROR_AUTH
    if any(needle in code_lower for needle in _MODEL_CODES) or status_code == 404:
        return ERROR_MODEL
    if status_code == 429:
        return ERROR_RATE_LIMIT
    if status_code and status_code >= 500:
        return ERROR_SERVER

    return ERROR_UNKNOWN


def format_error_text(provider, model, status_code, payload):
    """Rend une erreur de génération sous forme lisible, pour `metadata_text`.

    Le JSON brut du fournisseur reste destiné aux logs ; ce qui est stocké en
    base et relu par un responsable doit dire quoi faire.
    """
    kind = classify_error(status_code, payload)
    text = f"{ERROR_LABELS[kind]} (fournisseur {provider.name}"
    if model:
        text += f", modèle {model}"
    if status_code:
        text += f", HTTP {status_code}"
    text += ")"

    _, detail = _error_fields(payload)
    detail = " ".join(detail.split())  # une erreur multiligne tient sur une ligne
    if detail:
        if len(detail) > _DETAIL_MAX_LENGTH:
            detail = detail[:_DETAIL_MAX_LENGTH].rstrip() + "…"
        text += f" Détail : {detail}"

    return text


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


def _ask_ollama(provider, model, prompt, session, timeout, seed, max_tokens):
    options = {"seed": seed}
    if max_tokens:
        options["num_predict"] = max_tokens
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": options,
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


def _ask_openai(provider, model, prompt, session, timeout, seed, max_tokens):
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "seed": seed,
    }
    if max_tokens:
        payload["max_tokens"] = max_tokens
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


def _ask_anthropic(provider, model, prompt, session, timeout, seed, max_tokens):
    # Anthropic n'expose pas de paramètre `seed` : la reproductibilité est
    # approchée par température nulle.
    payload = {
        "model": model,
        "max_tokens": max_tokens or DEFAULT_MAX_TOKENS,
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


def ask_model(
    provider,
    model,
    prompt,
    session=None,
    timeout=DEFAULT_TIMEOUT,
    seed=DEFAULT_SEED,
    max_tokens=None,
):
    """Interroge le fournisseur et retourne `(texte, métadonnées, code HTTP)`.

    `texte` vaut `None` quand la génération a échoué ; `métadonnées` contient
    alors la réponse brute du fournisseur, utile au diagnostic. Lève
    `LLMConfigError` si le fournisseur est mal configuré.

    `max_tokens` plafonne la réponse. Les synthèses le laissent à `None` (pas
    de limite hors celle qu'Anthropic impose) ; seul le ping de `ping_generation`
    s'en sert pour ne payer qu'un token.
    """
    _check_api_type(provider)
    return _ADAPTERS[provider.api_type](
        provider, model, prompt, session, timeout, seed, max_tokens
    )


def ping_generation(provider, model, session=None, timeout=30):
    """Vérifie que le compte peut réellement *générer*, pas seulement répondre.

    `list_models` ne suffit pas à valider un fournisseur : chez OpenAI comme
    chez Anthropic, la liste des modèles répond encore normalement avec un
    solde à zéro. Seul un appel de génération fait apparaître le crédit épuisé
    — d'où ce ping d'un token, dont la réponse n'est jamais lue.

    Retourne `(ok, kind, message)` : `kind` et `message` valent `None` en cas de
    succès, sinon `kind` est l'une des constantes `ERROR_*` et `message` le
    texte lisible correspondant.
    """
    _check_api_type(provider)
    _, payload, status_code = ask_model(
        provider,
        model,
        PING_PROMPT,
        session=session,
        timeout=timeout,
        max_tokens=PING_MAX_TOKENS,
    )

    # Une réponse vide mais en 200 suffit : la génération est autorisée, c'est
    # tout ce que ce ping cherche à établir.
    if status_code == 200:
        return True, None, None

    kind = classify_error(status_code, payload)
    return False, kind, format_error_text(provider, model, status_code, payload)


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
