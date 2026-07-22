# Instructions de contribution — OceENS

> Périmètre : tout le dépôt. Ces consignes reflètent `main` au commit
> `9e4d987` (22 juillet 2026), avec les compléments en cours de la branche
> `docs`. La pull request documentaire de `docs` n'est pas encore mergée :
> elle doit continuer à être alimentée au fil des changements. Si le projet
> évolue, le code et le schéma présents sur la branche de travail restent la
> source de vérité.

## 1. Finalité du projet

OceENS est la plateforme d'évaluation des enseignements de l'EPF. Elle permet :

- aux étudiants de répondre aux sondages auxquels ils sont inscrits ;
- aux responsables de programme, animateurs, directions de campus et
  administrateurs de gérer ou consulter les sondages selon leur périmètre ;
- d'exporter et de visualiser les réponses ;
- de générer, via un processus séparé, des synthèses de verbatims par LLM.

Les données de sondage et les règles d'accès sont sensibles. La sécurité et la
non-régression métier priment sur les refactorings esthétiques.

## 2. Stack et organisation

- Python 3.12, FastAPI et Uvicorn ;
- SQLModel / SQLAlchemy avec SQLite ;
- authentification Microsoft Entra ID via MSAL et Microsoft Graph ;
- rendu serveur Jinja2, avec HTML, CSS et JavaScript sans framework frontend ;
- Pandas pour les exports CSV ;
- un daemon séparé pour les synthèses LLM.

Repères principaux :

- `app.py` : fabrique FastAPI, routes, autorisations et orchestration métier ;
- `auth.py` : connexion, callback et déconnexion Entra ID ;
- `models.py` : schéma SQLModel ;
- `database.py` : moteur SQLite et dépendance `SessionDep` ;
- `seed.py` : données initiales et synchronisation des formations ;
- `services/visualisation_data.py` : agrégations et contexte de visualisation ;
- `services/export_csv.py` : export CSV ;
- `sondage_loader.py` : chargement d'un sondage complet pour l'export ;
- `summaries_generator_daemon.py` : traitement asynchrone des synthèses LLM ;
- `templates/` : pages et fragments Jinja réutilisables ;
- `static/css/` et `static/js/` : présentation et interactions côté client ;
- `database/` et les fichiers `*.db` : données locales ignorées par Git.

Les commandes doivent être lancées depuis la racine : le chemin SQLite,
`templates/`, `static/` et plusieurs imports de données sont relatifs au dépôt.

## 3. Règles de travail

1. Lire le chemin d'exécution complet avant de modifier une route : handler,
   helper d'autorisation, modèle, template, JavaScript et service associé.
2. Faire un changement ciblé. Ne pas reformater ou réécrire du code sans lien
   avec la demande.
3. Préserver le comportement existant sauf si la demande exige explicitement
   de le changer. Documenter toute rupture d'API, de schéma ou d'interface.
4. Réutiliser les helpers et fragments existants avant d'ajouter une nouvelle
   variante de logique.
5. Garder les textes visibles par l'utilisateur en français soigné. Préserver
   les variantes françaises et anglaises des questions lorsqu'elles existent.
6. Ne pas masquer une exception sans stratégie explicite. Pour une mutation en
   base, effectuer un `rollback()` avant de retourner une erreur.
7. Quand une modification change une convention partagée, mettre aussi à jour
   `database/instruction.md` et, si pertinent, le README de la branche `docs`.
   La documentation de la PR `docs` est cumulative et peut rester ouverte tant
   que les évolutions fonctionnelles ne sont pas stabilisées.

## 4. Authentification et autorisations

L'authentification seule n'autorise aucune action métier.

- Utiliser `get_current_user()` pour identifier la session.
- Utiliser `require_roles()` pour le contrôle de rôle, puis vérifier le
  périmètre de la formation ou du campus concerné.
- Réutiliser `parse_role_scopes()`, `get_role_scopes()`,
  `get_results_program_codes()`, `can_manage_survey()` et
  `can_duplicate_survey()` selon le besoin.
- Ne jamais faire confiance à un `program`, un campus, un `survey_id` ou un
  `user_id` reçu du navigateur sans le recouper avec la base et les rôles.
- Appliquer les contrôles côté serveur, même si l'action est masquée dans le
  template.

Rôles reconnus :

- `student` ;
- `admin` ;
- `program_manager:<code>[;<code>...]` ;
- `facilitator:<code>[;<code>...]` ;
- `campus_manager:<campus>[;<campus>...]`.

Le texte avant `:` est le rôle et les valeurs après `:` sont ses périmètres,
séparés par `;`. Ne pas analyser ces chaînes avec une nouvelle logique locale.
Le rôle `admin` n'implique pas automatiquement toutes les vues : respecter les
choix explicites de navigation et d'autorisation déjà présents.

## 5. Invariants métier et base de données

- `Survey.status == 1` : sondage ouvert ;
- `Survey.status == 0` : sondage fermé ;
- `Survey.status == 2` : génération des synthèses en cours.

Ne pas remplacer ces vérifications par un simple test booléen : l'état `2` a
un sens métier distinct.

- Un répondant est identifié par la clé composite `(survey_id, user_id)`.
- Une réponse appartient à une `Submission`; la soumission et la mise à jour de
  `Respondent.submission_date` doivent rester atomiques.
- Les réponses liées à une soumission ou à un module doivent être supprimées
  avant leurs parents. Réutiliser `delete_survey_with_relations()` ou conserver
  le même ordre de suppression.
- Les statistiques reposent sur les types de section `C`, `P`, `ME`, `R` et sur
  les types de question existants, notamment `QCU_Satisfaction`,
  `QCU_Attendance`, `QCM_Insatisfaction`, `Question_ouverte` et `NPS`.
- Les listes de professeurs affichées dans la création de sondage doivent être
  triées avec `teacher_sort_key()` : le tri est insensible à la casse, aux
  accents et aux espaces multiples. Ne pas revenir à un simple `sorted()`, qui
  décale les noms accentués et rend la sélection moins prévisible.
- L'export CSV est contractuel : conserver l'encodage UTF-8 avec BOM, le
  séparateur `;`, l'ordre des colonnes et le tri, sauf demande contraire.

Toute mutation regroupant plusieurs écritures doit suivre ce modèle :

1. valider l'utilisateur, son rôle et son périmètre ;
2. valider les données avant la première écriture ;
3. effectuer les écritures dans une seule session ;
4. faire un seul `commit()` lorsque l'opération est cohérente ;
5. faire `rollback()` en cas d'échec et retourner une erreur sans donnée
   sensible.

`SQLModel.metadata.create_all()` crée les tables manquantes mais ne migre pas
une base existante. Toute évolution de `models.py` doit donc prévoir la
compatibilité des bases déjà déployées ou fournir une stratégie de migration.
Ne jamais modifier manuellement une base réelle pour simuler cette migration.

Au démarrage, `seed_all_if_necessary()` synchronise toujours les formations,
puis initialise le reste seulement si aucun utilisateur n'existe. Toute
modification du seed doit rester relançable sans doublons ni perte de données.

## 6. Routes et réponses HTTP

- Conserver la fabrique `create_app()` et les préfixes existants :
  `dashboard_router` sous `/dashboard`, `api_router` sous `/api`.
- Les pages HTML utilisent `TemplateResponse`; les appels JavaScript utilisent
  des réponses JSON explicites.
- Après une mutation issue d'un formulaire HTML, préférer une redirection `303`
  afin d'éviter une nouvelle soumission au rafraîchissement.
- Employer des statuts cohérents : `401` pour une authentification absente,
  `403` pour un droit insuffisant, `404` pour une ressource absente, `409` pour
  un conflit d'état métier et `500` pour une erreur serveur inattendue.
- Ne pas inclure de secret, jeton, requête SQL complète ou détail interne dans
  les messages d'erreur retournés au navigateur.

## 7. Templates, CSS et JavaScript

- Réutiliser `templates/template_parts/` pour les éléments partagés entre
  dashboards.
- Préserver le thème clair/sombre et la préférence `localStorage` gérés par
  `part_theme_switcher.html` et `static/css/theme.css`.
- Vérifier les mises en page bureau et mobile ; les règles transversales sont
  notamment dans `responsive.css`, `site_header.css` et
  `dashboard_navigation.css`.
- Éviter de dupliquer une règle visuelle commune dans chaque dashboard.
- Si le contexte Jinja change, mettre à jour dans le même changement tous les
  templates et scripts qui consomment les clés concernées.
- Pour les requêtes `fetch`, gérer les réponses non réussies et afficher un
  message compréhensible sans révéler les détails techniques.
- La page `templates/survey_create.html` charge actuellement SheetJS, jQuery et
  Select2 depuis CDN. Toute évolution de cette page doit vérifier que ces
  dépendances restent chargées dans le bon ordre : jQuery avant Select2, puis le
  code qui initialise les champs concernés.
- Les listes longues de professeurs doivent rester ergonomiques dans l'interface
  de création de sondage. Si Select2 est ajusté ou remplacé, conserver une
  recherche clavier utilisable, le thème visuel existant et la compatibilité
  avec les fragments de `templates/template_parts/part_add_ues_and_modules.html`.

## 8. Journalisation et diagnostics

- Préférer le logger `uvicorn` au `print()` pour les diagnostics applicatifs
  durables. Le README de la branche `docs` documente déjà cette convention.
- Utiliser `logger.info()` pour les opérations normales, `logger.warning()` pour
  une ressource attendue absente ou une situation non bloquante, et
  `logger.exception()` dans les blocs `except` où la traceback est utile.
- Les logs ne doivent jamais contenir de secret, de jeton, de cookie, de contenu
  brut de `.env` ou de données personnelles non nécessaires au diagnostic.
- Les traces temporaires ajoutées pendant une correction doivent être retirées
  avant livraison, sauf si elles deviennent de vrais logs utiles et calibrés.

## 9. Secrets, données et services externes

Ne jamais lire, afficher, modifier ni commiter les valeurs réelles de :

- `.env` ;
- `ENTRA_CLIENT_ID`, `ENTRA_CLIENT_SECRET`, `ENTRA_TENANT_ID` ;
- `SECRET_KEY`, `LLM_API_KEY` ;
- les jetons ou cookies de session ;
- `database/db_oceens.db`, `cache_llm.db` ou tout autre fichier `*.db`.

Documenter uniquement les noms de variables et utiliser des valeurs factices.
Ne pas désactiver `https_only=True`, la validation du domaine ou la protection
`state` OAuth pour faciliter un test. Si un mode de développement HTTP devient
nécessaire, il doit être explicite, limité au développement et sûr par défaut.

Ne pas appeler Microsoft Graph, Entra ID ou le serveur LLM réel pendant les
tests. Les appels doivent être simulés. Ne pas lancer
`summaries_generator_daemon.py` sans demande explicite : il boucle, écrit en
base et contacte un service externe.

## 10. Validation avant livraison

Le dépôt ne contient actuellement ni suite de tests automatisés ni CI. Ne pas
annoncer qu'un changement est testé si seule une lecture du code a été faite.

Validation minimale depuis la racine :

```powershell
python -m compileall -q app.py auth.py database.py models.py seed.py `
  sondage_loader.py survey_loader_from_xlsx.py summaries_generator_daemon.py services
git diff --check
```

Puis, selon le changement :

- tester les helpers métier avec des cas autorisés, interdits et sans données ;
- vérifier les routes avec une base SQLite jetable, jamais avec une copie de
  production ;
- contrôler les rôles `admin`, `student` et les rôles à périmètre concernés ;
- tester un sondage ouvert, fermé et en génération si le statut intervient ;
- vérifier les écrans concernés en clair/sombre et en largeur mobile/bureau ;
- pour la création de sondage, vérifier le tri des professeurs avec des noms
  accentués, en majuscules/minuscules variées et avec espaces multiples ;
- vérifier l'encodage, les colonnes et le tri pour tout changement d'export.

Ajouter des tests de non-régression pour toute nouvelle logique isolable. Si un
outil de test ou de qualité devient obligatoire, l'ajouter explicitement aux
dépendances et documenter sa commande ; ne pas supposer qu'il est installé.

## 11. Critères de fin

Un changement est prêt lorsque :

- le besoin demandé est couvert sans modification hors périmètre ;
- les contrôles d'accès sont présents côté serveur ;
- les transactions et erreurs préservent l'intégrité de la base ;
- aucun secret ni fichier de données n'apparaît dans le diff ;
- la validation pertinente a été exécutée et son résultat est communiqué ;
- la documentation est mise à jour si une commande, une variable, un rôle, une
  route ou un comportement observable a changé.
