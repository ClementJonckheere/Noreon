from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Principal, current_tenant, require_admin
from app.core.auth import hash_password
from app.core.db import get_db
from app.models.connection import Connection
from app.models.tenant import Tenant
from app.models.user import ConnectionAccess, User
from app.schemas import (
    ConnectionGrantIn,
    UserCreateIn,
    UserOut,
    UserUpdateIn,
)

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserOut])
def list_users(
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(current_tenant),
    _: Principal = Depends(require_admin),
) -> list[UserOut]:
    rows = db.execute(
        select(User).where(User.tenant_id == tenant.id).order_by(User.email)
    ).scalars().all()
    return [UserOut.model_validate(u) for u in rows]


@router.post("", response_model=UserOut, status_code=201)
def create_user(
    payload: UserCreateIn,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(current_tenant),
    _: Principal = Depends(require_admin),
) -> UserOut:
    existing = db.execute(
        select(User).where(User.tenant_id == tenant.id, User.email == payload.email.lower())
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="Un utilisateur avec cet email existe déjà.")
    user = User(
        tenant_id=tenant.id, email=payload.email.lower(), full_name=payload.full_name,
        password_hash=hash_password(payload.password), role=payload.role, is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    payload: UserUpdateIn,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(current_tenant),
    _: Principal = Depends(require_admin),
) -> UserOut:
    user = db.get(User, user_id)
    if user is None or user.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable.")
    if payload.role is not None:
        user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.password:
        user.password_hash = hash_password(payload.password)
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


@router.delete("/{user_id}", status_code=204)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(current_tenant),
    principal: Principal = Depends(require_admin),
) -> None:
    user = db.get(User, user_id)
    if user is None or user.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable.")
    if principal.user_id == user_id:
        raise HTTPException(status_code=409, detail="Vous ne pouvez pas supprimer votre propre compte.")
    db.delete(user)
    db.commit()


# --- Accès par connexion source (Module 11) ---
@router.get("/{user_id}/connections", response_model=list[int])
def list_user_connections(
    user_id: int,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(current_tenant),
    _: Principal = Depends(require_admin),
) -> list[int]:
    rows = db.execute(
        select(ConnectionAccess.connection_id).where(ConnectionAccess.user_id == user_id)
    ).scalars().all()
    return list(rows)


@router.post("/{user_id}/connections", status_code=204)
def grant_connection(
    user_id: int,
    payload: ConnectionGrantIn,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(current_tenant),
    _: Principal = Depends(require_admin),
) -> None:
    user = db.get(User, user_id)
    conn = db.get(Connection, payload.connection_id)
    if user is None or user.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable.")
    if conn is None or conn.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Connexion introuvable.")
    exists = db.execute(
        select(ConnectionAccess).where(
            ConnectionAccess.user_id == user_id,
            ConnectionAccess.connection_id == payload.connection_id,
        )
    ).scalar_one_or_none()
    if exists is None:
        db.add(ConnectionAccess(user_id=user_id, connection_id=payload.connection_id))
        db.commit()


@router.delete("/{user_id}/connections/{connection_id}", status_code=204)
def revoke_connection(
    user_id: int,
    connection_id: int,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(current_tenant),
    _: Principal = Depends(require_admin),
) -> None:
    access = db.execute(
        select(ConnectionAccess).where(
            ConnectionAccess.user_id == user_id,
            ConnectionAccess.connection_id == connection_id,
        )
    ).scalar_one_or_none()
    if access is not None:
        db.delete(access)
        db.commit()
