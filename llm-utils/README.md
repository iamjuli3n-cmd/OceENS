# LLM Utilities for OceENS

Outils annexes autour des fournisseurs LLM du projet OceENS.

## Le suivi des coûts a été déplacé dans l'application

Ce dossier contenait `token-counting/`, qui estimait le nombre de tokens du
**code source du dépôt** (`*.py`) et le multipliait par un tarif codé en dur.
Cette mesure ne disait rien de ce que l'application dépense réellement : les
synthèses de verbatims consomment des tokens de *prompts et de réponses*, pas
de fichiers Python, et l'approximation « 4 caractères = 1 token » ne
correspond au tokenizer d'aucun fournisseur.

Le suivi des coûts est désormais **mesuré, pas estimé**, et intégré à
l'application :

| Où | Quoi |
| --- | --- |
| `services/llm_costs.py` | Calcul du coût à partir des tokens réellement consommés |
| `/backend/llm/prices` | Grille tarifaire par modèle, éditable (admin) |
| `/backend/llm/costs` | Coût global, détaillé par sondage et par modèle (admin) |
| Bouton 💰 sur une ligne de sondage | Coût des synthèses de ce sondage |

Le daemon enregistre les compteurs renvoyés par le fournisseur
(`Summary.input_tokens` / `output_tokens` / `model_used`) au moment de la
génération : c'est la seule occasion de les capturer, aucune API ne permet de
les redemander après coup.

Voir la section « Coût des synthèses » du README racine.

---

## Utilitaires à venir

Ce dossier reste destiné aux outils LLM hors application :

- gestion et versionnage de prompts ;
- évaluation comparative de modèles ;
- scripts de bascule entre fournisseurs.
