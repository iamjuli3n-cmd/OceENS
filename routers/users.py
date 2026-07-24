"""Gestion des roles utilisateurs."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlmodel import Session, delete, func, select
from database import SessionDep
from models import Program, Respondent, Role, Survey, User
from schemas import RoleUpdate
from security import check_role, parse_role_scopes, require_roles, VALID_ROLES
from typing import List

api_router = APIRouter(tags=["API"], prefix="/api")


@api_router.put("/users/{user_id}/role")
def update_user_role(
    request: Request, user_id: int, body: RoleUpdate, session: SessionDep
):
    # ── Sécurité : seul un Admin peut modifier les rôles ──
    auth_result = require_roles(request, session, ["admin"])
    if auth_result is None:
        return JSONResponse(
            content={"error": "Accès refusé. Rôle Admin requis."},
            status_code=403,
        )
    admin,roles = auth_result

    valid_campuses = set(
        session.exec(select(Program.campus).distinct()).all()
    )
    for role in body.roles:
        if not _is_valid_role([role]) or not _has_valid_campus_scope(
            role, valid_campuses
        ):
            return JSONResponse(
                content={"detail": f"Rôle invalide : '{role}'"},
                status_code=422,
            )
    user = session.get(User, user_id)
    if not user:
        return JSONResponse(
            content={"detail": f"Utilisateur {user_id} introuvable"},
            status_code=409,
        )
    # Remove all previous roles
    session.exec(delete(Role).where(Role.user_id == user_id))
    session.commit()
    for role in body.roles:
        new_role = Role(user_id=user_id, role=role)
        session.add(new_role)
    session.commit()

    return {"user_id": user.user_id, "mail": user.mail, "roles": body.roles}

# ┌─ Visualisation & Export CSV ──────────────────────────────────────┐


def _is_valid_role(roles: List[str]) -> bool:
    return check_role(roles, list(VALID_ROLES))


def _has_valid_campus_scope(
    role: str, valid_campuses: set[str]
) -> bool:
    if role.split(":", 1)[0] != "campus_manager":
        return True

    role_campuses = parse_role_scopes(role)
    return bool(role_campuses) and set(role_campuses) <= valid_campuses
