"""Espaces (workspaces d'équipe) + gouvernance des données.

Hiérarchie : Univers (tenant) → Espaces → Connexions (BDD). L'administrateur
(DSI) crée les espaces, y rattache des BDD, gère les membres et **gouverne** les
données (cocher/décocher tables et colonnes). Tout le paramétrage est réservé
aux administrateurs ; les membres peuvent utiliser le chat de leurs espaces.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Principal, current_principal, require_admin
from app.core.db import get_db
from app.models.connection import Connection
from app.models.space import Space, SpaceConnection, SpaceMember
from app.models.user import User
from app.schemas import (
    GovernanceToggle,
    SpaceChatRequest,
    SpaceConnectionIn,
    SpaceCreate,
    SpaceMemberIn,
)
from app.services import chat as chat_svc
from app.services import spaces as spaces_svc
from app.services.connections import get_source_adapter

router = APIRouter(prefix="/spaces", tags=["spaces"])


# --------------------------------------------------------------------------
# Accès
# --------------------------------------------------------------------------
def _is_member(db: Session, space_id: int, principal: Principal) -> bool:
    if principal.user_id is None:
        return True  # repli dev (admin implicite)
    return db.execute(
        select(SpaceMember.id).where(
            SpaceMember.space_id == space_id, SpaceMember.user_id == principal.user_id
        )
    ).scalar_one_or_none() is not None


def get_space(
    space_id: int,
    db: Session = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> Space:
    space = db.execute(
        select(Space).where(Space.id == space_id, Space.tenant_id == principal.tenant_id)
    ).scalar_one_or_none()
    if space is None:
        raise HTTPException(status_code=404, detail="Espace introuvable.")
    if not principal.is_admin and not _is_member(db, space.id, principal):
        raise HTTPException(status_code=403, detail="Vous n'êtes pas membre de cet espace.")
    return space


def _owned_connection(db: Session, principal: Principal, connection_id: int) -> Connection:
    conn = db.execute(
        select(Connection).where(
            Connection.id == connection_id, Connection.tenant_id == principal.tenant_id
        )
    ).scalar_one_or_none()
    if conn is None:
        raise HTTPException(status_code=404, detail="Connexion introuvable pour cet univers.")
    return conn


# --------------------------------------------------------------------------
# Espaces
# --------------------------------------------------------------------------
@router.get("")
def list_spaces(
    db: Session = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> list[dict]:
    q = select(Space).where(Space.tenant_id == principal.tenant_id).order_by(Space.name)
    spaces = db.execute(q).scalars().all()
    if not principal.is_admin and principal.user_id is not None:
        member_ids = set(db.execute(
            select(SpaceMember.space_id).where(SpaceMember.user_id == principal.user_id)
        ).scalars().all())
        spaces = [s for s in spaces if s.id in member_ids]
    return [spaces_svc.space_dict(db, s) for s in spaces]


@router.post("", dependencies=[Depends(require_admin)])
def create_space(
    payload: SpaceCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> dict:
    slug = spaces_svc.slugify(payload.name)
    exists = db.execute(
        select(Space).where(Space.tenant_id == principal.tenant_id, Space.slug == slug)
    ).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(status_code=409, detail="Un espace porte déjà ce nom.")
    space = Space(
        tenant_id=principal.tenant_id, name=payload.name.strip(),
        slug=slug, description=payload.description or "",
    )
    db.add(space)
    db.commit()
    db.refresh(space)
    return spaces_svc.space_dict(db, space)


@router.get("/{space_id}")
def get_space_detail(space: Space = Depends(get_space), db: Session = Depends(get_db)) -> dict:
    conns = db.execute(
        select(Connection).join(
            SpaceConnection, SpaceConnection.connection_id == Connection.id
        ).where(SpaceConnection.space_id == space.id)
    ).scalars().all()
    members = db.execute(
        select(SpaceMember, User).join(User, User.id == SpaceMember.user_id)
        .where(SpaceMember.space_id == space.id)
    ).all()
    return {
        **spaces_svc.space_dict(db, space),
        "connections": [
            {"id": c.id, "name": c.name, "engine": c.engine, "is_read_only": c.is_read_only}
            for c in conns
        ],
        "members": [
            {"user_id": m.user_id, "email": u.email, "role": m.role} for m, u in members
        ],
    }


@router.delete("/{space_id}", dependencies=[Depends(require_admin)])
def delete_space(space: Space = Depends(get_space), db: Session = Depends(get_db)) -> dict:
    db.delete(space)
    db.commit()
    return {"deleted": space.id}


# --------------------------------------------------------------------------
# Rattachement des BDD (admin)
# --------------------------------------------------------------------------
@router.post("/{space_id}/connections", dependencies=[Depends(require_admin)])
def attach_connection(
    payload: SpaceConnectionIn,
    space: Space = Depends(get_space),
    db: Session = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> dict:
    _owned_connection(db, principal, payload.connection_id)
    if not spaces_svc.is_connection_in_space(db, space.id, payload.connection_id):
        db.add(SpaceConnection(space_id=space.id, connection_id=payload.connection_id))
        db.commit()
    return get_space_detail(space=space, db=db)


@router.delete("/{space_id}/connections/{connection_id}", dependencies=[Depends(require_admin)])
def detach_connection(
    connection_id: int,
    space: Space = Depends(get_space),
    db: Session = Depends(get_db),
) -> dict:
    link = db.execute(
        select(SpaceConnection).where(
            SpaceConnection.space_id == space.id,
            SpaceConnection.connection_id == connection_id,
        )
    ).scalar_one_or_none()
    if link is not None:
        db.delete(link)
        db.commit()
    return get_space_detail(space=space, db=db)


# --------------------------------------------------------------------------
# Membres (admin)
# --------------------------------------------------------------------------
@router.post("/{space_id}/members", dependencies=[Depends(require_admin)])
def add_member(
    payload: SpaceMemberIn,
    space: Space = Depends(get_space),
    db: Session = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> dict:
    user = db.execute(
        select(User).where(User.id == payload.user_id, User.tenant_id == principal.tenant_id)
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable dans cet univers.")
    existing = db.execute(
        select(SpaceMember).where(
            SpaceMember.space_id == space.id, SpaceMember.user_id == payload.user_id
        )
    ).scalar_one_or_none()
    if existing is None:
        db.add(SpaceMember(space_id=space.id, user_id=payload.user_id, role=payload.role))
    else:
        existing.role = payload.role
    db.commit()
    return get_space_detail(space=space, db=db)


@router.delete("/{space_id}/members/{user_id}", dependencies=[Depends(require_admin)])
def remove_member(
    user_id: int,
    space: Space = Depends(get_space),
    db: Session = Depends(get_db),
) -> dict:
    m = db.execute(
        select(SpaceMember).where(
            SpaceMember.space_id == space.id, SpaceMember.user_id == user_id
        )
    ).scalar_one_or_none()
    if m is not None:
        db.delete(m)
        db.commit()
    return get_space_detail(space=space, db=db)


# --------------------------------------------------------------------------
# Gouvernance : cocher/décocher tables & colonnes (admin)
# --------------------------------------------------------------------------
def _require_attached(db: Session, space: Space, connection_id: int) -> None:
    if not spaces_svc.is_connection_in_space(db, space.id, connection_id):
        raise HTTPException(status_code=404, detail="Cette BDD n'est pas rattachée à l'espace.")


@router.get("/{space_id}/connections/{connection_id}/governance",
            dependencies=[Depends(require_admin)])
def get_governance(
    connection_id: int,
    space: Space = Depends(get_space),
    db: Session = Depends(get_db),
) -> dict:
    _require_attached(db, space, connection_id)
    return spaces_svc.governance_view(db, space.id, connection_id)


@router.put("/{space_id}/connections/{connection_id}/tables/{schema}/{table}",
            dependencies=[Depends(require_admin)])
def toggle_table(
    connection_id: int, schema: str, table: str, payload: GovernanceToggle,
    space: Space = Depends(get_space), db: Session = Depends(get_db),
) -> dict:
    _require_attached(db, space, connection_id)
    spaces_svc.set_table_enabled(db, space.id, connection_id, schema, table, payload.enabled)
    db.commit()
    return {"table": table, "enabled": payload.enabled}


@router.put("/{space_id}/connections/{connection_id}/columns/{schema}/{table}/{column}",
            dependencies=[Depends(require_admin)])
def toggle_column(
    connection_id: int, schema: str, table: str, column: str, payload: GovernanceToggle,
    space: Space = Depends(get_space), db: Session = Depends(get_db),
) -> dict:
    _require_attached(db, space, connection_id)
    spaces_svc.set_column_enabled(db, space.id, connection_id, schema, table, column, payload.enabled)
    db.commit()
    return {"table": table, "column": column, "enabled": payload.enabled}


# --------------------------------------------------------------------------
# Chat d'espace : applique la gouvernance de l'espace sur la BDD choisie
# --------------------------------------------------------------------------
@router.post("/{space_id}/chat")
def space_chat(
    payload: SpaceChatRequest,
    space: Space = Depends(get_space),
    db: Session = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> dict:
    _require_attached(db, space, payload.connection_id)
    conn = _owned_connection(db, principal, payload.connection_id)
    response = chat_svc.answer_question(
        db, conn, payload.question,
        run_analysis=payload.run_analysis, deep_analysis=payload.deep_analysis,
        hidden_tables=spaces_svc.hidden_tables(db, space.id, payload.connection_id),
        hidden_columns=spaces_svc.hidden_columns(db, space.id, payload.connection_id),
    )
    db.commit()
    return response.as_dict()
