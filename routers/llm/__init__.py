"""Administration LLM : fournisseurs, tarifs et coûts.

Regroupée en paquet parce que la partie LLM représente désormais trois écrans
distincts (fournisseurs, grille tarifaire, coûts) qui partagent le même
contrôle d'accès et les mêmes modèles.

Les URLs publiques restent inchangées (`/backend/providers`, …) : ce
regroupement range le code, il ne déplace pas les pages. Les liens, signets et
redirections existants continuent donc de fonctionner.
"""

from routers.llm import costs, prices, providers

__all__ = ["costs", "prices", "providers"]
