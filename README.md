# OCEENS II

Plateforme d'évaluation des enseignements conçue pour l'école d'ingénieurs EPF.

## Aperçu
L'application **OCEENS II** est actuellement structurée comme un **frontend autonome**. Elle permet aux utilisateurs (notamment à l'administration/scolarité) de préparer la création de sondages pour différentes filières de l'EPF.

Visuellement, l'application est habillée d'un thème "Océan" (bleu/orange) en plus de respecter les couleurs de base de l'EPF.

## Architecture
Le projet utilise pour l'instant un serveur léger **Flask** chargé uniquement de la distribution des fichiers HTML, CSS et JS. L'application est préparée pour l'intégration future d'une vraie base de données et d'une API backend.

Pour l'instant, **aucune logique backend n'est requise** (pas de SQLAlchemy, pas de SQLite). Toutes les données (Campus, Filières, UE, Professeurs) sont mockées (simulées) en JavaScript directement sur le navigateur.

### Pages de l'application :
1. **Page d'accueil** (`/`) : Hub principal avec l'image de fond et la charte graphique Oceens II (titre bicolore, boutons arrondis). Permet d'accéder au module de paramétrage.
2. **Page de paramétrage** (`/parametrage`) : Interface de création de sondage. L'utilisateur peut y sélectionner l'année, le campus, la filière, puis configurer les Unités d'Enseignement (UE), ajouter des modules et y affecter des professeurs.

## Installation et Démarrage Local

Ce projet nécessite Python (3.x) installé sur votre machine. Les dépendances sont minimalistes.

1. **Cloner ou télécharger le projet localement** dans le dossier de votre choix.
2. Ouvrez une invite de commande ou le terminal (ex: `cmd`, `powershell`, ou Anaconda Prompt).
3. **Installez la dépendance principale (Flask)** :
   ```bash
   pip install -r requirements.txt
   ```
4. **Lancez le serveur Flask** :
   ```bash
   python app.py
   ```
5. Une fois le serveur lancé (vous verrez `* Running on http://127.0.0.1:5000`), ouvrez votre navigateur web et rendez-vous à l'adresse : **http://localhost:5000**

## Structure des Dossiers

```
test_web_app/
│
├── app.py                   # Point d'entrée Flask (démarrage du serveur et rendu des pages)
├── requirements.txt         # Fichier contenant les dépendances Python (uniquement Flask)
├── README.md                # Documentation du projet (ce fichier)
│
├── static/                  # Dossier des fichiers statiques
│   ├── css/
│   │   └── parametrage.css  # Styles CSS de la page de paramétrage
│   ├── img/                 # Images et logos de l'application
│   │   ├── epf_logo.png     # Logo officiel de l'EPF
│   │   └── fond_accueil.png # Image de fond de la page d'accueil
│   └── js/
│       └── parametrage.js   # Script JS gérant l'interface de paramétrage (avec données simulées)
│
└── templates/               # Dossier des vues HTML servies par Flask
    ├── index.html           # Structure HTML de la page d'accueil
    └── parametrage.html     # Structure HTML de la page de création de sondage
```

## Évolutions futures
Dans sa version finale, ce projet est destiné à accueillir un backend complet en Python.
- Le fichier `app.py` sera enrichi avec des routes API (`/api/campus`, `/api/sondages`, etc.).
- Les données simulées en tête du fichier `static/js/parametrage.js` seront supprimées et remplacées par des appels AJAX (`fetch`) vers les nouvelles routes du backend.
- Les modèles de base de données (ex: SQLite ou PostgreSQL) seront réintégrés.
