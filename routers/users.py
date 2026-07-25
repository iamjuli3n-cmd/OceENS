"""Gestion des roles utilisateurs."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlmodel import Session, delete, func, select
from core.database import SessionDep
from models import Program, Respondent, Role, Survey, User
from core.security import check_role, parse_role_scopes, require_roles, VALID_ROLES
from typing import List

router = APIRouter(tags=["API"], prefix="/api")


# Corps de requête PUT : la nouvelle liste de rôles à appliquer
class RoleUpdate(BaseModel):
    roles: List[str]


@router.put("/users/{user_id}/role")
def update_user_role(
    request: Request, user_id: int, body: RoleUpdate, session: SessionDep
):
    """Remplace l'ensemble des rôles d'un utilisateur (admin uniquement).

    Stratégie: on supprime tous ses rôles existants puis on réinsère la
    nouvelle liste, après avoir validé chaque rôle et son périmètre de campus.
    """
    # ── Sécurité : seul un Admin peut modifier les rôles ──
    auth_result = require_roles(request, session, ["admin"])
    if auth_result is None:
        return JSONResponse(
            content={"error": "Accès refusé. Rôle Admin requis."},
            status_code=403,
        )
    admin,roles = auth_result

    # Liste des campus réellement existants (pour valider les périmètres)
    valid_campuses = set(
        session.exec(select(Program.campus).distinct()).all()
    )
    # Valider chaque rôle demandé : nom connu ET périmètre de campus valide
    for role in body.roles:
        if not _is_valid_role([role]) or not _has_valid_campus_scope(
            role, valid_campuses
        ):
            return JSONResponse(
                content={"detail": f"Rôle invalide : '{role}'"},
                status_code=422,  # 422 = données non traitables
            )
    # Vérifier que l'utilisateur cible existe
    user = session.get(User, user_id)
    if not user:
        return JSONResponse(
            content={"detail": f"Utilisateur {user_id} introuvable"},
            status_code=409,
        )
    # Supprimer tous les rôles précédents de cet utilisateur
    session.exec(delete(Role).where(Role.user_id == user_id))
    session.commit()
    # Réinsérer les nouveaux rôles
    for role in body.roles:
        new_role = Role(user_id=user_id, role=role)
        session.add(new_role)
    session.commit()

    return {"user_id": user.user_id, "mail": user.mail, "roles": body.roles}


def _is_valid_role(roles: List[str]) -> bool:
    """Vrai si le nom de rôle fait partie des rôles valides connus."""
    return check_role(roles, list(VALID_ROLES))


def _has_valid_campus_scope(
    role: str, valid_campuses: set[str]
) -> bool:
    """Valide le périmètre campus d'un rôle campus_manager.

    Les autres rôles passent toujours (True). Pour campus_manager, il faut au
    moins un campus et que tous soient des campus réellement existants.
    """
    # Seul campus_manager a un périmètre de campus à valider
    if role.split(":", 1)[0] != "campus_manager":
        return True

    # Les campus du rôle doivent tous exister (sous-ensemble des campus valides)
    role_campuses = parse_role_scopes(role)
    return bool(role_campuses) and set(role_campuses) <= valid_campuses
