"""Daemon de génération des synthèses de verbatims par LLM.

Processus séparé de l'application web. Les deux moitiés ne communiquent que
par la table `summaries`, qui sert de file d'attente :

- l'application y dépose des lignes à `http_status = 0` lorsqu'un responsable
  demande la génération des synthèses d'un sondage ;
- ce daemon les consomme une par une et y réécrit le résultat.

`http_status` porte donc à la fois l'état de file et le résultat : `0` reste à
traiter, `200` est fait, toute autre valeur est un échec conservé pour le
diagnostic. Le daemon ne modifie jamais `Survey.status`.

Le dialogue HTTP avec le modèle est délégué à `services/llm_client.py` : ce
fichier ne connaît ni URL, ni format de payload, ni fournisseur particulier.

À lancer à la main uniquement : il boucle, écrit en base et contacte un
service externe.
"""

import json
import logging
import signal
import sys
import time

from dotenv import load_dotenv
from markdown_it import MarkdownIt
from requests.exceptions import RequestException
from sqlmodel import Session, select

from core.database import engine
from models import Answer, LLMProvider, Prompt, Submission, Summary
from services.llm_client import (
    LLMConfigError,
    ask_model,
    build_cache_session,
    check_model,
    format_error_text,
    format_metadata_text,
)

load_dotenv()

logger = logging.getLogger("uvicorn.error")


# Intervalle d'attente quand la file est vide.
POLL_INTERVAL_SECONDS = 30

REQUEST_TIMEOUT_SECONDS = 120

# Fournisseur utilisé par les prompts antérieurs à la configuration
# multi-fournisseur (`Prompt.provider_id` à NULL).
DEFAULT_PROVIDER_NAME = "Ollama EPF"

# Codes réécrits dans `Summary.http_status` pour les échecs qui ne viennent pas
# d'une réponse HTTP du fournisseur.
STATUS_MODEL_NOT_FOUND = 404
STATUS_TIMEOUT = 504
STATUS_CONFIG_ERROR = 500


def signal_handler(signal_number, frame):
    """Arrête proprement le daemon sur Ctrl+C (SIGINT)."""
    logger.info("Arrêt du daemon de synthèses.")
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)


def get_provider(session, prompt_row):
    """Retourne le fournisseur d'un prompt, ou le fournisseur par défaut.

    Un `provider_id` à NULL correspond aux prompts créés avant la
    configuration multi-fournisseur : ils restent routés vers Ollama EPF.
    """
    if prompt_row.provider_id:
        provider = session.get(LLMProvider, prompt_row.provider_id)
        if provider:
            return provider
        logger.warning(
            "Fournisseur %s introuvable, repli sur %s",
            prompt_row.provider_id,
            DEFAULT_PROVIDER_NAME,
        )

    return session.exec(
        select(LLMProvider).where(LLMProvider.name == DEFAULT_PROVIDER_NAME)
    ).first()


def finish_summary(
    session,
    summary_row,
    status,
    summary_text=None,
    metadata_text=None,
    metadata=None,
):
    """Écrit le résultat d'une synthèse et la sort de la file d'attente.

    Toute sortie de `process_summary()` passe par ici : une ligne dont le
    traitement échoue doit quand même quitter l'état `0`, sinon le daemon la
    reprend indéfiniment et la file n'avance plus.

    `metadata` porte les compteurs de tokens du fournisseur. Ils sont recopiés
    en colonnes dédiées : c'est la seule occasion de les capturer, l'API ne
    permet pas de les redemander après coup.
    """
    summary_row.summary_text = summary_text
    summary_row.metadata_text = metadata_text
    summary_row.http_status = status

    if metadata:
        summary_row.model_used = metadata.get("model")
        summary_row.input_tokens = metadata.get("prompt_count")
        summary_row.output_tokens = metadata.get("eval_count")

    session.add(summary_row)
    session.commit()


def load_verbatims(session, summary_row):
    """Charge les réponses ouvertes couvertes par cette synthèse.

    Quand `module_id` est renseigné, la synthèse porte sur un couple
    module/enseignant précis (sections `ME`) ; sinon elle porte sur toute la
    question du sondage.
    """
    query = (
        select(Answer.value)
        .join(Submission, Submission.submission_id == Answer.submission_id)
        .where(
            Submission.survey_id == summary_row.survey_id,
            Answer.question_id == summary_row.question_id,
        )
    )

    if summary_row.module_id:
        query = query.where(
            Answer.module_id == summary_row.module_id,
            Answer.teacher == summary_row.teacher,
        )

    # `Answer.value` est nullable : une réponse vide ferait échouer le join.
    return [value for value in session.exec(query).all() if value]


def process_summary(session, summary_row, http_session, md, checked_models):
    """Traite une ligne de la file. Retourne toujours après l'avoir sortie de l'état 0."""

    prompt_row = session.get(Prompt, summary_row.prompt_id)
    if not prompt_row:
        logger.warning(
            "Synthèse %s : prompt %s introuvable",
            summary_row.summary_id,
            summary_row.prompt_id,
        )
        finish_summary(
            session,
            summary_row,
            STATUS_CONFIG_ERROR,
            metadata_text="Prompt introuvable.",
        )
        return

    provider = get_provider(session, prompt_row)
    if not provider:
        logger.error("Aucun fournisseur LLM configuré (ni prompt, ni défaut).")
        finish_summary(
            session,
            summary_row,
            STATUS_CONFIG_ERROR,
            metadata_text="Aucun fournisseur LLM configuré.",
        )
        return

    model = prompt_row.model or provider.default_model

    # Vérification du modèle, mise en cache par (fournisseur, modèle) : un
    # fournisseur en panne ne doit pas faire échouer les lignes qui visent un
    # autre fournisseur.
    cache_key = (provider.provider_id, model)
    if cache_key not in checked_models:
        try:
            checked_models[cache_key] = check_model(
                provider, model, session=http_session
            )
        except (LLMConfigError, RequestException) as error:
            # Non mémorisé : la panne peut être transitoire.
            logger.exception(
                "Vérification du modèle %s impossible chez %s", model, provider.name
            )
            finish_summary(
                session, summary_row, STATUS_CONFIG_ERROR, metadata_text=str(error)
            )
            return

    if not checked_models[cache_key]:
        # Historiquement le daemon s'arrêtait ici (`exit(1)`). Un seul prompt
        # mal configuré bloquait alors toute la file.
        logger.warning(
            "Modèle %s indisponible chez %s : synthèse %s marquée en échec",
            model,
            provider.name,
            summary_row.summary_id,
        )
        finish_summary(
            session,
            summary_row,
            STATUS_MODEL_NOT_FOUND,
            metadata_text=f"Modèle {model} indisponible chez {provider.name}.",
        )
        return

    verbatims = load_verbatims(session, summary_row)
    if not verbatims:
        logger.warning("Synthèse %s : aucun verbatim", summary_row.summary_id)
        finish_summary(
            session,
            summary_row,
            STATUS_CONFIG_ERROR,
            metadata_text="Aucun verbatim à synthétiser.",
        )
        return

    # `{ANSWERS}` est contractuel : tous les prompts en base l'utilisent.
    full_prompt = prompt_row.prompt_text.replace("{ANSWERS}", "|".join(verbatims))

    logger.info(
        "Synthèse %s : %d verbatims, modèle %s via %s",
        summary_row.summary_id,
        len(verbatims),
        model,
        provider.name,
    )

    try:
        answer, metadata, status_code = ask_model(
            provider,
            model,
            full_prompt,
            session=http_session,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except LLMConfigError as error:
        logger.error("Fournisseur %s mal configuré : %s", provider.name, error)
        finish_summary(
            session, summary_row, STATUS_CONFIG_ERROR, metadata_text=str(error)
        )
        return
    except RequestException as error:
        logger.warning("Appel au fournisseur %s en échec : %s", provider.name, error)
        finish_summary(
            session, summary_row, STATUS_TIMEOUT, metadata_text=str(error)
        )
        return

    if not answer:
        # Le JSON brut du fournisseur part dans les logs, pour le diagnostic ;
        # la base reçoit la version lisible, qui dit quoi corriger (crédit
        # épuisé, débit dépassé, clé refusée…).
        error_text = format_error_text(provider, model, status_code, metadata)
        logger.warning(
            "Synthèse %s : réponse vide (HTTP %s) — %s — réponse brute : %s",
            summary_row.summary_id,
            status_code,
            error_text,
            json.dumps(metadata, default=str),
        )
        finish_summary(
            session,
            summary_row,
            status_code,
            metadata_text=error_text,
        )
        return

    metadata_text = format_metadata_text(metadata)
    logger.info("Synthèse %s : %s", summary_row.summary_id, metadata_text)

    finish_summary(
        session,
        summary_row,
        status_code,
        summary_text=md.render(answer),
        metadata_text=metadata_text,
        metadata=metadata,
    )


def main():
    """Boucle principale du daemon : dépile la file `summaries` en continu.

    Tant qu'il y a une ligne à http_status=0, on la traite ; sinon on attend
    POLL_INTERVAL_SECONDS avant de re-vérifier. Toute exception inattendue est
    rattrapée pour ne jamais arrêter le daemon ni bloquer une ligne.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s:     %(message)s",
    )

    md = MarkdownIt()  # convertisseur markdown → HTML pour le rendu final
    http_session = build_cache_session("cache_llm.db")

    # Disponibilité des modèles, mémorisée par (fournisseur, modèle) pour la
    # durée du processus.
    checked_models = {}

    logger.info("Daemon de synthèses démarré.")

    while True:
        with Session(engine) as session:
            summary_row = session.exec(
                select(Summary).where(Summary.http_status == 0)
            ).first()

            if not summary_row:
                time.sleep(POLL_INTERVAL_SECONDS)
                continue

            try:
                process_summary(session, summary_row, http_session, md, checked_models)
            except Exception:
                # Filet de sécurité : une exception inattendue ne doit ni
                # arrêter le daemon, ni laisser la ligne bloquée à 0.
                logger.exception(
                    "Erreur inattendue sur la synthèse %s", summary_row.summary_id
                )
                session.rollback()
                finish_summary(
                    session,
                    summary_row,
                    STATUS_CONFIG_ERROR,
                    metadata_text="Erreur interne pendant la génération.",
                )


if __name__ == "__main__":
    main()
