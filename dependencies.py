"""Objets applicatifs partages par tous les routeurs.

`templates` etait une variable locale de `create_app()`, capturee par
fermeture par les routes. La sortir ici est ce qui rend le decoupage en
modules possible.
"""

import logging

from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="templates")
templates.env.policies["json.dumps_kwargs"] = {"sort_keys": False}

logger = logging.getLogger("uvicorn")
logger.level=logging.DEBUG
