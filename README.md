# OcéEns II

Plateforme d'évaluation des enseignements conçue pour l'école d'ingénieurs EPF.

## Aperçu

L'application **OcéEns II** permet à l'administration et à la scolarité de créer et gérer des sondages d'évaluation pour les différentes filières de l'EPF. L'interface est habillée de la charte graphique officielle de l'EPF.

### Stack technique

| Composant | Technologie |
|-----------|-------------|
| **Framework** | FastAPI (Python) |
| **Authentification** | Microsoft Entra ID (Azure AD) via OAuth2.0 / MSAL |
| **Base de données** | SQLite (via SQLAlchemy + SQLModel) |
| **Templating** | Jinja2 |
| **Frontend** | HTML / CSS / JavaScript |
| **Serveur** | Uvicorn |

---

## Pages de l'application

| Route | Page | Description |
|-------|------|-------------|
| `/` | Accueil | Hub principal avec la charte graphique EPF. Accès à l'authentification. |
| `/dasboard/survey_create` | Paramétrage | Interface de création de sondage : sélection année, campus, filière, configuration des UE, modules et professeurs. |
| `/survey/{id_sondage}` | Questionnaire | Interface de réponse au sondage avec affichage dynamique des sections et questions (choix unique, multiple, ouverte). |
| `/dashboard/admin` | Dashboard Admin | Tableau de bord administrateur. |
| `/dashboard/student` | Dashboard Étudiant | Tableau de bord étudiant. |
| `/dashboard/program_manager` | Dashboard RP/RM | Tableau de bord responsable pédagogique / responsable de module. |

---

## Installation et démarrage

### Prérequis

- Python 3.x
- Un fichier `.env` configuré (voir section [Configuration](#configuration))

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
  Créer un dossier database/ puis y coller le fichier db_oceens.db

5. **Lancez l'application** :
   ```bash
   fastapi dev
   ```


   Ou directement avec Uvicorn :

   ```bash
   uvicorn app:app --host 0.0.0.0 --port 8000
   ```

6. Ouvrez votre navigateur à l'adresse **http://localhost:8000**.

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

```

> [!CAUTION]
> Ne jamais commiter le fichier `.env`. Il est déjà listé dans le `.gitignore`.

---

## Structure du projet

```
OceENS/
├── app.py                  # Point d'entrée – routes et configuration FastAPI
├── auth.py                 # Authentification Microsoft Entra ID (login, logout, callback)
├── database.py             # Configuration SQLAlchemy + modèle UserRole (rôles)
├── models.py               # Modèles SQLModel (tables, relations, structure des données)
├── remplir_db.py           # Script d'initialisation des données
├── launch.sh               # Script de lancement
├── requirements.txt        # Dépendances Python
├── .env                    # Variables d'environnement (⚠️ non commité)
├── .gitignore              # Fichiers et dossiers ignorés par Git
│
├── database/                # Dossier contenant la base de données (à ajouter manuellement)
│   └── db_oceens.db         # Fichier de la base de données (à ajouter manuellement)
|
├── templates/              # Templates HTML (Jinja2)
│   ├── index.html               # Page d'accueil / login
│   ├── parametrage.html         # Création de sondage
│   ├── questionnaire.html       # Réponse au sondage
│   └── dashboard/
│       ├── admin.html           # Dashboard administrateur
│       ├── student.html        # Dashboard étudiant
│       └── program_manager.html            # Dashboard RP/RM
│
├── static/                 # Fichiers statiques
│   ├── css/
│   │   ├── admin.css            # Styles dashboard admin
│   │   ├── etudiant.css         # Styles dashboard étudiant
│   │   ├── parametrage.css      # Styles page paramétrage
│   │   └── questionnaire.css    # Styles page questionnaire
│   ├── js/
│   │   ├── admin.js             # Scripts dashboard admin
│   │   ├── etudiant.js          # Scripts dashboard étudiant
│   │   ├── parametrage.js       # Scripts page paramétrage
│   │   └── questionnaire.js     # Scripts page questionnaire
│   └── img/
│       ├── epf_logo.png         # Logo EPF
│       ├── epf_logo_blanc.png   # Logo EPF (blanc)
│       ├── hautpage.png         # Image en-tête
│       └── logo.png             # Logo application
│
└── env/                    # Environnement virtuel Python (non commité)
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
   → Récupération des infos utilisateur
   → Consultation de la BDD pour obtenir le rôle
   → Création de la session {name, email, role}
   → Redirection vers /dashboard/{role}

4. À la déconnexion (/logout)
   → Suppression de la session et des cookies
   → Déconnexion côté Microsoft
   → Retour à la page d'accueil
```

---

## Checklist de déploiement

- [ ] `.env` créé avec les vraies credentials Azure
- [ ] Certificat SSL valide (Let's Encrypt ou équivalent)
- [ ] `https_only=True` dans le SessionMiddleware
- [ ] Base de données présente
- [ ] Variables d'environnement sécurisées

---

## Évolutions futures

- Fonctionnalité de visualisation des réponses des questionnaires. Un début de cette fonctionnalité a été implémenté dans la branche feat/visualisation.
- Implémenter des tests et du CI/CD.
- Migration vers une base de données plus robuste (PostgreSQL)

---

## Maquette de la visualisation

[générée par IA]
<img width="945" height="646" alt="image" src="https://github.com/user-attachments/assets/f4654635-346c-42a5-b935-15edbdfddfe2" />
<img width="945" height="558" alt="image" src="https://github.com/user-attachments/assets/da2d185e-efa1-4408-9aa4-230d5bacba89" />

---

## Ressources

- [FastAPI](https://fastapi.tiangolo.com/)
- [MSAL Python](https://github.com/AzureAD/microsoft-authentication-library-for-python)
- [Microsoft Graph](https://learn.microsoft.com/en-us/graph/)
- [Jinja2](https://jinja.palletsprojects.com/)
- [SQLAlchemy](https://www.sqlalchemy.org/)
- [SQLModel](https://sqlmodel.tiangolo.com/)

---

**Équipe OcéEns** — EPF
