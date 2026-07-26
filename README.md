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

   > Alternative en développement : définir `RUN_SUMMARIES_DAEMON=1` dans le
   > `.env` fait lancer automatiquement le daemon en process séparé au démarrage
   > d'uvicorn (et l'arrête à la fermeture). Laisser vide en production, où
   > `launch.sh` gère déjà le daemon dans sa propre session `screen`.

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
`core/dependencies.py`. Les logs applicatifs passent par le handler Uvicorn, généralement
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

## Fournisseurs LLM (synthèses de verbatims)

Les synthèses de verbatims sont générées par un LLM. Le fournisseur est
**configurable depuis l'interface** (`/backend/providers`, admin uniquement),
sans toucher au code. Le fournisseur par défaut est **Ollama EPF**
(`https://locallm.mde.epf.fr/ollama`), créé automatiquement au premier
démarrage.

### Types d'API supportés

| `api_type` | Couvre |
|------------|--------|
| `ollama`    | Serveurs Ollama (local, EPF, tiers) |
| `openai`    | OpenAI **et tout endpoint compatible OpenAI** : vLLM, Groq, Mistral, LM Studio… |
| `anthropic` | API Claude (Anthropic) |

### Principe de sécurité : aucune clé en base

La base SQLite n'est pas chiffrée et part dans les sauvegardes. **Aucune clé
d'API n'y est donc stockée.** La table `llm_providers` ne contient que le *nom*
de la variable d'environnement (`api_key_env`, ex. `OPENAI_API_KEY`) ; la valeur
reste dans le `.env` et n'est résolue qu'au moment de l'appel. Ce nom est validé
contre une liste blanche (`LLM_*` ou `*_API_KEY`) pour empêcher de pointer vers
un secret système (`SECRET_KEY`, `ENTRA_CLIENT_SECRET`…).

### Ajouter un nouveau fournisseur

1. **Ajouter la clé au `.env`** avec un nom conforme (`LLM_*` ou `*_API_KEY`) :

   ```env
   OPENAI_API_KEY=sk-...
   ```

2. **Redémarrer le daemon** de synthèses (les variables du `.env` ne sont lues
   qu'au démarrage) :

   ```bash
   python summaries_generator_daemon.py
   ```

3. **Créer le fournisseur** dans `/backend/providers` → *+ Nouveau fournisseur* :
   renseigner le nom, le type d'API, l'URL de base, le nom de la variable d'env
   (`OPENAI_API_KEY`), et un modèle par défaut. L'indicateur **« clé présente /
   absente »** confirme que la variable est bien chargée. Le bouton **Tester**
   vérifie que l'URL et la clé répondent, puis envoie une génération d'un token
   pour confirmer que le compte peut réellement générer (voir ci-dessous).

4. **Relier un prompt** au fournisseur : dans `/backend/prompts`, un `<select>`
   permet de choisir le fournisseur d'un prompt. Un prompt sans fournisseur
   (`provider_id` NULL) retombe automatiquement sur Ollama EPF.

> [!NOTE]
> Un fournisseur référencé par au moins un prompt ne peut pas être supprimé
> (pour ne pas casser la configuration de ces prompts).

### Crédit épuisé et autres erreurs de fournisseur

Chaque fournisseur signale ses pannes dans un format différent : un crédit
épuisé est un `429 insufficient_quota` chez OpenAI, mais un `400 « Your credit
balance is too low »` chez Anthropic. `services/llm_client.py` normalise ces
réponses en catégories (`quota`, `rate_limit`, `auth`, `model`, `server`) et en
tire un message lisible :

> ⚠️ Crédit ou quota épuisé chez le fournisseur : la clé est valide mais le
> compte ne peut plus générer. Rechargez le compte ou choisissez un autre
> fournisseur. (fournisseur OpenAI, modèle gpt-4o-mini, HTTP 429)

Ce message est écrit dans `Summary.metadata_text` à la place du JSON brut — il
est donc visible directement depuis l'interface quand une synthèse échoue. La
réponse brute du fournisseur reste dans les logs du daemon pour le diagnostic.

> [!IMPORTANT]
> Le bouton **Tester** ne se contente pas de lister les modèles : chez OpenAI
> comme chez Anthropic, `GET /v1/models` répond encore parfaitement avec un
> solde à zéro. Un ping de génération d'un token (coût négligeable) est donc
> envoyé ensuite — c'est le seul moyen de repérer un crédit épuisé **avant** de
> lancer une campagne de synthèses.

---

## Coût des synthèses

Le coût de chaque synthèse est **mesuré, pas estimé**. Au moment de la
génération, le daemon enregistre les compteurs de tokens renvoyés par le
fournisseur (`Summary.input_tokens`, `output_tokens`, `model_used`) : c'est la
seule occasion de les capturer, aucune API ne permet de les redemander après
coup. Le montant est ensuite obtenu en croisant ces compteurs avec la grille
tarifaire.

> [!NOTE]
> Cette section remplace les anciens scripts `llm-utils/token-counting/`, qui
> comptaient les tokens du **code source du dépôt** et les multipliaient par un
> tarif codé en dur. Cette mesure ne disait rien de la dépense réelle de
> l'application. Le suivi porte désormais sur les appels effectivement facturés.

### Grille tarifaire — `/backend/llm/prices`

Les tarifs vivent en base (table `llm_model_prices`), en **dollars par million
de tokens**, comme les publient les fournisseurs. Ils sont éditables depuis
l'administration : pas besoin de livrer une version pour suivre une révision de
prix, ni pour couvrir un fournisseur ajouté localement.

Sont pré-remplis au démarrage (`seed_model_prices`, idempotent — un tarif
corrigé à la main n'est jamais réécrit) :

| Modèle | Entrée $/M | Sortie $/M |
| --- | ---: | ---: |
| `claude-opus-5` | 5.00 | 25.00 |
| `claude-sonnet-5` | 3.00 | 15.00 |
| `claude-haiku-4-5` | 1.00 | 5.00 |
| `gemma4:26b` (Ollama EPF, auto-hébergé) | 0.00 | 0.00 |

Les tarifs des autres fournisseurs (OpenAI, Mistral, Groq…) sont **à saisir** :
ils ne sont pas devinés. Un tarif spécifique à un fournisseur l'emporte sur un
tarif générique portant le même nom de modèle.

### Consultation

| Où | Quoi |
| --- | --- |
| `/backend/llm/costs` | Coût global, détaillé par sondage et par modèle (admin) |
| Bouton 💰 sur une ligne de sondage | Coût des synthèses de ce sondage |

### Ce qui n'est pas chiffré

Une synthèse n'est pas chiffrable quand ses compteurs manquent (générée avant
cette fonctionnalité, ou fournisseur qui ne les expose pas) ou quand son modèle
n'a pas de tarif enregistré. Elle est alors **comptée à part**, jamais estimée
ni ramenée à zéro : un montant inventé serait plus nuisible qu'un montant
absent, puisqu'il s'afficherait avec l'autorité d'un montant réel. Les écrans
signalent explicitement qu'un total est partiel.

À distinguer d'un coût **nul** : les modèles auto-hébergés valent réellement
0,00 $, ce qui n'est pas la même information que « inconnu ».

> [!IMPORTANT]
> Le suivi démarre à la mise en service : les synthèses générées auparavant
> n'ont pas de compteurs en base et ne peuvent pas être chiffrées
> rétroactivement.

---

## Structure du projet

```
OceENS/
├── main.py                       # Fabrique FastAPI, middlewares et assemblage des routeurs
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
│   ├── dependencies.py           #   templates Jinja et logger partagés
│   └── seed.py                   #   Données initiales et synchronisation des formations
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
│   ├── sections_questions.py     #   Administration des sections et questions
│   └── llm/                      #   Administration LLM (URLs inchangées)
│       ├── _access.py            #     Contrôle d'accès partagé des écrans LLM
│       ├── providers.py          #     Fournisseurs LLM (CRUD + test de connexion)
│       ├── prices.py             #     Grille tarifaire par modèle
│       └── costs.py              #     Coût global et coût par sondage
│
├── database/                     # Dossier contenant la base de données (ignoré par Git)
│   └── db_oceens.db
│
├── services/                     # Logique métier
│   ├── helpers.py                # Navigation, statistiques, filtres, tri
│   ├── visualisation_data.py     # Agrégations et contexte de visualisation
│   ├── llm_client.py             # Client LLM multi-fournisseur (ollama/openai/anthropic)
│   ├── llm_costs.py              # Coût des synthèses (tokens mesurés × grille tarifaire)
│   └── export_csv.py             # Export CSV des réponses
│
├── llm-utils/                    # Outils LLM hors application
│   └── README.md                 # (le suivi des coûts est passé dans l'app, voir ci-dessus)
│
├── templates/                    # Templates HTML (Jinja2)
│   ├── index.html                     # Page d'accueil / login
│   ├── dashboard/
│   │   ├── admin.html
│   │   ├── student.html
│   │   ├── program_manager.html
│   │   ├── facilitator.html
│   │   ├── campus_manager.html
│   │   ├── teachers-analytics.html       # Satisfaction des enseignants (campus_manager, program_manager)
│   │   ├── survey.html                   # Réponse au sondage
│   │   ├── survey_create.html            # Création de sondage
│   │   └── visualisation.html            # Visualisation des réponses
│   ├── backend/                       # Pages d'administration (admin only)
│   │   ├── prompts.html               # Liste des prompts LLM
│   │   ├── prompt_form.html           # Formulaire create/edit partagé
│   │   └── llm/                       # Écrans LLM (fournisseurs, tarifs, coûts)
│   │       ├── providers.html
│   │       ├── provider_form.html
│   │       ├── prices.html            # Grille tarifaire éditable
│   │       └── costs.html             # Coût global et par sondage
│   └── template_parts/                # Fragments réutilisables entre dashboards
│       ├── part_site_header.html
│       ├── part_dashboard_navigation.html
│       ├── part_theme_switcher.html
│       └── ...
│
├── static/
│   ├── css/                      # admin.css, student.css, program_manager.css, survey.css,
│   │                              # survey_create.css, visualisation.css, prompt_form.css,
│   │                              # llm_backend.css (écrans LLM), theme.css, site_header.css,
│   │                              # dashboard_navigation.css, responsive.css
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

### Nettoyage des étudiants orphelins

Lors de la suppression d'un sondage, les étudiants qui ne sont plus rattachés à
**aucun autre** sondage sont également supprimés, pour éviter d'accumuler des
comptes inutilisés (`services/helpers.py`, `_delete_orphan_students`). Un
garde-fou protège les utilisateurs à rôle privilégié (`admin`,
`program_manager`, `facilitator`, `campus_manager`) : un enseignant ou un
gestionnaire ayant répondu à un sondage n'est jamais effacé.

### Ajout d'un utilisateur par mail

L'onglet « Utilisateurs » du dashboard administrateur propose un bouton
**« + Ajouter un utilisateur »** : un mail suffit pour créer le compte, avec le
rôle `student` par défaut (`POST /api/users`, admin uniquement). Le mail est
validé (format + domaine autorisé) et les doublons sont refusés.

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
python -m compileall -q main.py \
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
