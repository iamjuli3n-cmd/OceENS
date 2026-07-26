"""Contrôle d'accès partagé par les écrans d'administration LLM.

Les trois routeurs du paquet appliquent exactement la même règle : être
connecté et porter le rôle `admin`. La factoriser ici évite d'en avoir trois
copies qui divergent — le jour où la règle change, il n'y a qu'un endroit à
modifier, et pas d'écran oublié.
"""

from sqlmodel import func, select

from core.auth import get_current_user
from models import Role, User


def current_roles(request, session):
    """Retourne `(utilisateur, rôles)`, ou `(None, [])` si non authentifié."""
    user = get_current_user(request)
    if not user:
        return None, []

    roles_query = session.exec(
        select(func.group_concat(Role.role))
        .join(User, Role.user_id == User.user_id, isouter=True)
        .where(User.mail == user["email"].casefold())
    ).first()

    return user, roles_query.split(",") if roles_query else ["student"]


def is_admin(request, session):
    """Vrai si la requête émane d'un administrateur authentifié."""
    user, roles = current_roles(request, session)
    return bool(user) and "admin" in roles
