FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && rm -rf /var/lib/apt/lists/*

COPY ./requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Fichiers source Python (structure plate, pas de sous-dossier app/)
COPY main.py seed.py schemas.py ./
COPY sondage_loader.py survey_loader_from_xlsx.py summaries_generator_daemon.py ./

# Répertoires applicatifs
COPY ./core core
COPY ./models models
COPY ./routers routers
COPY ./services services
COPY ./templates templates
COPY ./static static
COPY ./import import

ENV PYTHONUNBUFFERED=1


# Le répertoire database/ est créé automatiquement par database.py au démarrage.
# Monter /app/database comme volume pour persister la base SQLite entre les redémarrages.
# Le fichier .env ne doit PAS être copié dans l'image : fournir les secrets via
# --env-file .env au lancement (docker run) ou via les variables d'environnement.

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

