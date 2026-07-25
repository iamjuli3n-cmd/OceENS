# OcéEns II

Plateforme d'évaluation des enseignements conçue pour l'école d'ingénieurs EPF.

## Aperçu

L'application **OcéEns II** permet aux responsables de programme, animateurs, directions de campus et administrateurs de créer et gérer des sondages d'évaluation pour les différentes filières de l'EPF, et aux étudiants d'y répondre. Les réponses peuvent être exportées, visualisées, et synthétisées via un LLM. L'interface est habillée de la charte graphique officielle de l'EPF.

### Stack technique

| Composant | Technologie |
|-----------|-------------|
| **Framework** | FastAPI (Python 3.12) |
| **Authentification** | Microsoft Entra ID (Azure AD) via OAuth2.0 / MSAL, Microsoft Graph |
| **Base de données** | SQLite (via SQLAlchemy + SQLModel) |
| **Templating** | Jinja2 (rendu serveur) |
| **Frontend** | HTML / CSS / JavaScript, sans framework |
| **Serveur** | Uvicorn |
| **Journalisation** | Module standard Python `logging`, via les handlers Uvicorn |
| **Exports** | Pandas (CSV) |
| **Synthèses de verbatims** | Daemon séparé, appel à un LLM (`requests-cache`, `markdown-it-py`) |

---

## Rôles

- `student` : répond aux sondages auxquels il est inscrit.
- `program_manager:<code>` : gère les sondages de sa/ses filière(s).
- `facilitator:<code>` : anime les sondages de sa/ses filière(s).
- `campus_manager:<campus>` : périmètre à l'échelle du campus.
- `admin` : administration générale.

Un utilisateur peut cumuler plusieurs rôles, chacun avec son propre périmètre (codes filière ou campus séparés par `;`).

---

## Pages et routes principales

| Route | Description |
|-------|-------------|
| `/` | Accueil, hub d'authentification. |
| `/login`, `/auth/callback`, `/logout` | Flux d'authentification Microsoft Entra ID. |
| `/dashboard/student` | Dashboard étudiant. |
| `/dashboard/program-manager` | Dashboard responsable de programme. |
| `/dashboard/facilitator` | Dashboard animateur. |
| `/dashboard/campus-manager` | Dashboard direction de campus. |
| `/dashboard/teachers/analytics` | Score de satisfaction par enseignant, filtrable par année / semestre / formation. Accessible aux rôles `campus_manager` et `program_manager`, scopé au périmètre de chacun. |
| `/dashboard/admin` | Dashboard administrateur. |
| `/dashboard/survey-create` | Création / paramétrage d'un sondage. |
| `/api/surveys/{survey_id}` | Questionnaire (réponse au sondage). |
| `/api/surveys/{survey_id}/status` | Changement de statut d'un sondage. |
| `/api/surveys/{survey_id}/students` | Gestion des étudiants inscrits à un sondage. |
| `/api/surveys/{survey_id}/export` | Export CSV des réponses. |
| `/api/surveys/{survey_id}/visualisation` | Visualisation des réponses. Accepte `?teacher=<nom>` pour arriver déjà filtré sur un enseignant. |
| `/api/surveys/{survey_id}/generate-summaries` | Lancement de la génération de synthèses LLM. |
| `/api/surveys/{survey_id}/destroy-summaries` | Suppression des synthèses générées. |
| `/api/users/{user_id}/role` | Modification du rôle d'un utilisateur. |
| `/backend/prompts` | Liste des prompts LLM (admin uniquement). |
| `/backend/prompts/new` | Formulaire de création d'un prompt. |
| `/backend/prompts/{id}/edit` | Formulaire de modification d'un prompt. |
| `/api/prompts` | Création d'un prompt (POST, form). |
| `/api/prompts/{id}` | Modification d'un prompt (PUT, fetch). Bloqué si le prompt est référencé dans `summaries`. |
| `/api/prompts/{id}/delete` | Suppression d'un prompt (POST, form). Bloquée si le prompt est référencé dans `summaries`. |

---

## Installation et démarrage

### Prérequis

- Python 3.12
- Un fichier `.env` configuré (voir section [Configuration](#configuration))

### Avec Docker Compose (recommandé)

```bash
docker compose up --build
```

La base SQLite est persistée dans un répertoire local. Par défaut `./database/` ; pour pointer ailleurs, définir `LOCAL_DATABASE_DIR` dans `.env` ou dans l'environnement :

```env
LOCAL_DATABASE_DIR=/chemin/vers/database
```

**Développement** — code source monté en volume (les modifications sont prises en compte sans rebuild), données de seed disponibles :

```bash
docker run -p 8000:8000 --env-file .env -v oceens_db:/app/database -v ./import:/app/import -v .:/app oceens:1.0
```

> Le `Dockerfile` inclut `--reload` dans la commande Uvicorn : uvicorn détecte les changements de fichiers et recharge l'application automatiquement lorsque le code source est monté via `-v .:/app`. Retirer `--reload` pour un déploiement en production.

> La base SQLite est persistée dans le volume Docker `oceens_db` (`/app/database`).
> Le fichier `.env` n'est jamais copié dans l'image : il est passé via `--env-file` au lancement.

### Sans Docker (installation manuelle)

### Étapes

1. **Cloner le projet**

   ```bash
   git clone <url-du-repo>
   cd OceENS
   ```

2. **Créer et activer un environnement virtuel**

   ```bash
   python -m venv env
   env/scripts/activate        # Windows
   source env/bin/activate     # Linux / macOS
   ```

3. **Installer les dépendances**

   ```bash
   pip install -r requirements.txt
   ```

4. **Ajouter la base de données**
   Créer un dossier `database/` puis y placer le fichier `db_oceens.db`, ou laisser `seed_all_if_necessary()` initialiser une base vide au premier démarrage.

5. **Lancer l'application** :

   ```bash
   fastapi dev
   ```

   Ou directement avec Uvicorn :

   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8000
   ```

   En production, `launch.sh` lance l'application et le daemon de synthèses dans des sessions `screen` séparées.

6. **(Optionnel) Lancer le daemon de synthèses LLM** :

   ```bash
   python summaries_generator_daemon.py
   ```

   Ce processus tourne en boucle, écrit en base et contacte un service LLM externe : à ne lancer que lorsque c'est nécessaire.

7. Ouvrez votre navigateur à l'adresse **http://localhost:8000**.

---

## Journalisation

Les logs applicatifs utilisent le module standard Python `logging` et le logger
`uvicorn`. Cela permet aux messages de l'application, d'`auth.py` et de `seed.py` de reprendre
le format, les couleurs et les handlers déjà configurés par le serveur.

Les niveaux sont utilisés selon leur gravité :

| Niveau | Utilisation |
|--------|-------------|
| `DEBUG` | Informations détaillées utiles au développement et au seeding. |
| `INFO` | Démarrage, arrêt et opérations applicatives normales. |
| `WARNING` | Ressource attendue absente ou situation non bloquante. |
| `ERROR` / `EXCEPTION` | Échec d'une opération ; `logger.exception()` conserve la traceback. |
| `CRITICAL` | Configuration indispensable manquante, empêchant le démarrage. |

Exemple :

```python
import logging

logger = logging.getLogger("uvicorn")

logger.info("Opération terminée")

try:
    operation_risquee()
except Exception:
    logger.exception("Échec de l'opération")
```

Les nouveaux diagnostics doivent utiliser le logger approprié plutôt que
`print()`. Le niveau applicatif est actuellement réglé sur `DEBUG` dans
`dependencies.py`. Les logs applicatifs passent par le handler Uvicorn, généralement
écrit sur `stderr` ; avec une redirection séparée, utilisez par exemple
`2> error.log` pour les récupérer.

---

## Configuration

Créez un fichier `.env` à la racine du projet :

```env
# Azure Entra ID
ENTRA_CLIENT_ID=your_app_id_here
ENTRA_CLIENT_SECRET=your_secret_here
ENTRA_TENANT_ID=your_tenant_id_here
REDIRECT_URI=http://localhost:8000/auth/callback
ALLOWED_DOMAINS=epf.fr,epfedu.fr

# Session
SECRET_KEY=your_secure_random_key_here

# Synthèses LLM
LLM_API_KEY=your_llm_api_key_here
```

> [!CAUTION]
> Ne jamais commiter le fichier `.env`. Il est déjà listé dans le `.gitignore`, tout comme les fichiers `*.db` (`database/db_oceens.db`, `cache_llm.db`).

---

## Token Counting et Coûts Claude API

OceENS inclut des outils pour estimer et tracker la consommation de tokens **pour Claude API** (support d'autres fournisseurs à venir).

### Utilisation rapide

```bash
# Estimation rapide (fonctionne sans API key)
./estimate-tokens.sh          # Unix/Linux/Mac
estimate-tokens.bat           # Windows

# Ou accès direct
python llm-utils/token-counting/estimate_tokens_local.py
```

**Statistiques du projet :**
- ~68K tokens pour l'intégralité du codebase
- Coût estimé : $0.20 (Sonnet 5) pour une revue complète
- Session type (5 tours) : ~$0.23

### Configuration pour comptage exact

Pour obtenir des comptages exacts via l'API Anthropic :

```bash
export ANTHROPIC_API_KEY='sk-...'
python llm-utils/token-counting/estimate_tokens.py
```

### Documentation complète

Voir `llm-utils/token-counting/TOKEN_COUNTING_GUIDE.md` pour :
- Guide d'intégration Claude Desktop
- Stratégies de réduction de coûts
- Tarification détaillée par modèle
- Recommandations de modèles (Haiku, Sonnet 5, Opus)

---

## Structure du projet

```
OceENS/
├── main.py                       # Fabrique FastAPI, middlewares et assemblage des routeurs
├── schemas.py                    # Schémas Pydantic des corps de requête
├── seed.py                       # Données initiales et synchronisation des formations
├── sondage_loader.py             # Chargement d'un sondage complet pour l'export
├── survey_loader_from_xlsx.py    # Import de sondages depuis un fichier Excel
├── summaries_generator_daemon.py # Traitement asynchrone des synthèses LLM (processus séparé)
├── launch.sh                     # Script de lancement (production, sans Docker)
├── requirements.txt              # Dépendances Python
├── Dockerfile                    # Image Docker de l'application
├── .dockerignore                 # Fichiers exclus du build Docker
├── .env                          # Variables d'environnement (⚠️ non commité)
├── .gitignore                    # Fichiers et dossiers ignorés par Git
│
├── core/                         # Accès bas niveau et sécurité
│   ├── auth.py                   #   Authentification Microsoft Entra ID (login, logout, callback)
│   ├── database.py               #   Moteur SQLite et dépendance SessionDep
│   ├── security.py               #   Rôles, périmètres, contrôle d'accès
│   └── dependencies.py           #   templates Jinja et logger partagés
│
├── models/                       # Schéma SQLModel, un fichier par table
│   ├── __init__.py               #   Ré-exporte toutes les classes (voir sa docstring)
│   └── User.py, Survey.py, ...
│
├── routers/                      # Routes découpées par domaine métier
│   ├── pages.py                  #   Accueil et dashboards par rôle
│   ├── surveys.py                #   Sondages : CRUD, statut, export, visualisation
│   ├── students.py               #   Inscription des étudiants à un sondage
│   ├── users.py                  #   Gestion des rôles utilisateurs
│   ├── summaries.py              #   Déclenchement des synthèses LLM
│   ├── prompts.py                #   Administration des prompts
│   ├── survey_templates.py       #   Administration des modèles de sondage
│   └── sections_questions.py     #   Administration des sections et questions
│
├── database/                     # Dossier contenant la base de données (ignoré par Git)
│   └── db_oceens.db
│
├── services/                     # Logique métier
│   ├── helpers.py                # Navigation, statistiques, filtres, tri
│   ├── visualisation_data.py     # Agrégations et contexte de visualisation
│   └── export_csv.py             # Export CSV des réponses
│
├── llm-utils/                    # Outils pour intégrations LLM
│   ├── README.md                 # Documentation des utilitaires LLM
│   └── token-counting/           # Estimation des tokens et coûts Claude API
│       ├── estimate_tokens_local.py       # Estimation rapide (sans API key)
│       ├── estimate_tokens.py             # Comptage exact (requiert ANTHROPIC_API_KEY)
│       ├── estimate-tokens.sh/.bat        # Wrappers de convenance
│       ├── TOKEN_COUNTING_GUIDE.md        # Guide complet et optimisations
│       └── README_TOKENS.md               # Référence rapide
│
├── templates/                    # Templates HTML (Jinja2)
│   ├── index.html                     # Page d'accueil / login
│   ├── survey.html                    # Réponse au sondage
│   ├── survey_create.html             # Création de sondage
│   ├── visualisation.html             # Visualisation des réponses
│   ├── dashboard/
│   │   ├── admin.html
│   │   ├── student.html
│   │   ├── program_manager.html
│   │   ├── facilitator.html
│   │   ├── campus_manager.html
│   │   └── prof.html                     # Satisfaction des enseignants (campus_manager, program_manager)
│   ├── backend/                       # Pages d'administration (admin only)
│   │   ├── prompts.html               # Liste des prompts LLM
│   │   └── prompt_form.html           # Formulaire create/edit partagé
│   └── template_parts/                # Fragments réutilisables entre dashboards
│       ├── part_site_header.html
│       ├── part_dashboard_navigation.html
│       ├── part_theme_switcher.html
│       └── ...
│
├── static/
│   ├── css/                      # admin.css, student.css, program_manager.css, survey.css,
│   │                              # survey_create.css, visualisation.css, prompt_form.css,
│   │                              # theme.css, site_header.css, dashboard_navigation.css, responsive.css
│   ├── js/
│   │   └── survey.js
│   └── img/
│
└── env/                           # Environnement virtuel Python (non commité)
```

---

## Authentification (OAuth 2.0)

Le flux d'authentification repose sur **Microsoft Entra ID** via la bibliothèque MSAL :

```
1. Utilisateur clique "Se connecter"
   → FastAPI génère un state aléatoire (UUID, protection CSRF)
   → Redirection vers la page de login Microsoft

2. L'utilisateur s'authentifie chez Microsoft
   → Microsoft redirige vers /auth/callback avec un code + state

3. Le serveur échange le code contre un token d'accès
   → Récupération des infos utilisateur via Microsoft Graph
   → Consultation de la BDD pour obtenir le(s) rôle(s) et leur périmètre
   → Création de la session {name, email, roles}
   → Redirection vers le dashboard correspondant

4. À la déconnexion (/logout)
   → Suppression de la session et des cookies
   → Déconnexion côté Microsoft
   → Retour à la page d'accueil
```

L'authentification seule n'autorise aucune action métier : chaque route vérifie ensuite le rôle et le périmètre (formation ou campus) via `require_roles()` et les helpers associés.

---

## Fonctionnalités notables

### Analytique des enseignants

La route `/dashboard/teachers/analytics` (`campus_manager`, `program_manager`) agrège le score de satisfaction par `(enseignant, sondage)` à partir des réponses `QCU_Satisfaction` renseignées d'un `Answer.teacher` (sections ME). La liste des enseignants est triée avec `teacher_sort_key()`, insensible à la casse et aux accents, et reste filtrable par année scolaire, semestre, formation et enseignant.

### Filtre par enseignant dans la visualisation

Un sélecteur côté client filtre la visualisation sans rechargement : seules les modules de l'enseignant choisi restent affichées, les sections Campus et Formation étant masquées. La page lit `?teacher=<nom>` au chargement pour se pré-filtrer ; les liens depuis l'analytique transmettent ce paramètre, si bien qu'un clic sur le score d'un enseignant ouvre directement sa vue.

### Sondages importés via Excel

Les sondages chargés par `survey_loader_from_xlsx.py` n'ont pas de question `QCU_Attendance` : `services/visualisation_data.py` utilise alors `satisfaction_responses_count` comme dénominateur de repli pour le score enseignant. Les noms d'enseignants sont normalisés en `.title()` à l'import comme à l'agrégation, pour fusionner les variantes de casse (`"GADEMER Antoine"` et `"Gademer Antoine"` = une seule entrée). Les questions sont triées par `question_id` dans le template, ce qui garantit les graphes avant les verbatims quel que soit l'ordre d'insertion.

### Périmètre de la direction de campus

Le dashboard `campus_manager` n'affiche que les sondages fermés ayant au moins un répondant. Le lien vers le questionnaire et le QR code y sont masqués (`can_view_survey_link=False`) : ce rôle consulte les résultats sans diffuser les sondages. Le garde `{% if can_view_survey_link | default(true) %}` laisse les autres dashboards inchangés.

---

## Checklist de déploiement

- [ ] `.env` créé avec les vraies credentials Azure et une `SECRET_KEY` dédiée
- [ ] Certificat SSL valide (Let's Encrypt ou équivalent)
- [ ] `https_only=True` dans le SessionMiddleware
- [ ] Base de données présente (`database/db_oceens.db`) ou volume Docker monté
- [ ] Variables d'environnement sécurisées, y compris `LLM_API_KEY`
- [ ] **Docker Compose** : `.env` chargé via `env_file`, jamais copié dans l'image ; `LOCAL_DATABASE_DIR` pointant vers le bon répertoire de base
- [ ] Daemon `summaries_generator_daemon.py` lancé si les synthèses LLM sont utilisées

---

## Validation avant contribution

Le dépôt ne contient pas de suite de tests automatisés ni de CI. Avant de proposer un changement :

```bash
python -m compileall -q main.py seed.py schemas.py \
  sondage_loader.py survey_loader_from_xlsx.py summaries_generator_daemon.py \
  core models routers services
git diff --check
```

Puis tester manuellement les routes concernées sur une base SQLite jetable (jamais une copie de production), avec les rôles et statuts de sondage pertinents.

---

## Ressources

- [FastAPI](https://fastapi.tiangolo.com/)
- [Guide du logging FastAPI et Uvicorn](https://apitally.io/blog/fastapi-logging-guide)
- [MSAL Python](https://github.com/AzureAD/microsoft-authentication-library-for-python)
- [Microsoft Graph](https://learn.microsoft.com/en-us/graph/)
- [Jinja2](https://jinja.palletsprojects.com/)
- [SQLAlchemy](https://www.sqlalchemy.org/)
- [SQLModel](https://sqlmodel.tiangolo.com/)
- [Pandas](https://pandas.pydata.org/)

---

**Équipe OcéEns** — EPF
