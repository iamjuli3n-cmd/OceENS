"""Schéma SQLModel, un fichier par table.

Sans ce fichier, `models/` serait un paquet-espace de noms implicite : une
instruction comme `from models import User` résoudrait alors vers le
*module* `models/User.py` plutôt que vers la classe `User` qu'il contient,
et tout appel `User(mail=...)` échouerait avec « 'module' object is not
callable ». Les imports groupés utilisés dans tout le dépôt
(`from models import Answer, Module, ...`) dépendent donc de ce ré-export
explicite : toute nouvelle classe ajoutée dans `models/` doit être déclarée
ici, sans quoi elle reste invisible depuis l'extérieur du paquet.

Aucun fichier de `models/` n'importe un autre fichier de `models/` : les
clés étrangères SQLAlchemy sont déclarées par nom de table (chaîne), pas par
référence de classe, donc il n'y a pas de risque d'import circulaire ici.
"""

from models.Answer import Answer
from models.LLMProvider import LLMProvider
from models.Module import Module
from models.Option import Option
from models.Program import Program
from models.Prompt import Prompt
from models.Question import Question
from models.Respondent import Respondent
from models.Role import Role
from models.Section import Section
from models.Stat import Stat
from models.StatValue import StatValue
from models.Submission import Submission
from models.Summary import Summary
from models.Survey import Survey
from models.Template import Template
from models.User import User

__all__ = [
    "Answer",
    "LLMProvider",
    "Module",
    "Option",
    "Program",
    "Prompt",
    "Question",
    "Respondent",
    "Role",
    "Section",
    "Stat",
    "StatValue",
    "Submission",
    "Summary",
    "Survey",
    "Template",
    "User",
]
