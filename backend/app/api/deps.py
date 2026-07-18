"""Dépendances FastAPI : authentification, tenant, rôles, accès par connexion.

Résolution du principal (Module 11) :
1. En-tête `Authorization: Bearer <jwt>` → utilisateur authentifié (rôle, tenant).
2. Sinon, en dev (settings.dev_auth_fallback), en-tête `X-Tenant: <slug>` →
   admin implicite du tenant (pour les tests et l'exploration API).
3. Sinon → 401.

Isolation multi-entreprise + « un utilisateur ne peut interroger que les
sources auxquelles il a accès ».
"""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import decode_access_token
from app.core.config import settings
from app.core.db import get_db
from app.models.connection import Connection
from app.models.tenant import Tenant, TenantSettings
from app.models.user import ROLE_ADMIN, ROLE_ANALYST, ROLE_ORDER, ConnectionAccess, User

DEFAULT_TENANT_SLUG = "demo"


@dataclass
class Principal:
    tenant_id: int
    role: str
    user_id: int | None  # None = repli dev (admin implicite)
    email: str | None = None

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN

    def has_role(self, minimum: str) -> bool:
        return ROLE_ORDER.get(self.role, 0) >= ROLE_ORDER.get(minimum, 0)


def get_or_create_tenant(db: Session, slug: str) -> Tenant:
    tenant = db.execute(select(Tenant).where(Tenant.slug == slug)).scalar_one_or_none()
    if tenant is None:
        tenant = Tenant(slug=slug, name=slug.capitalize())
        tenant.settings = TenantSettings(tenant=tenant)
        db.add(tenant)
        db.flush()
        db.commit()
    elif tenant.settings is None:
        tenant.settings = TenantSettings(tenant=tenant)
        db.flush()
        db.commit()
    return tenant


def current_principal(
    authorization: str | None = Header(default=None),
    x_tenant: str | None = Header(default=None, alias="X-Tenant"),
    db: Session = Depends(get_db),
) -> Principal:
    # 1) Jeton Bearer.
    if authorization and authorization.lower().startswith("bearer "):
        payload = decode_access_token(authorization.split(" ", 1)[1].strip())
        if payload is None:
            raise HTTPException(status_code=401, detail="Jeton invalide ou expiré.")
        user = db.get(User, int(payload["sub"]))
        if user is None or not user.is_active:
            raise HTTPException(status_code=401, detail="Utilisateur inconnu ou désactivé.")
        return Principal(tenant_id=user.tenant_id, role=user.role, user_id=user.id, email=user.email)

    # 2) Repli dev via X-Tenant (admin implicite).
    if settings.dev_auth_fallback:
        tenant = get_or_create_tenant(db, x_tenant or DEFAULT_TENANT_SLUG)
        return Principal(tenant_id=tenant.id, role=ROLE_ADMIN, user_id=None)

    raise HTTPException(status_code=401, detail="Authentification requise.")


def current_tenant(
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
) -> Tenant:
    tenant = db.get(Tenant, principal.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant introuvable.")
    return tenant


def require_role(minimum: str):
    """Fabrique une dépendance exigeant au moins le rôle `minimum`."""
    def _dep(principal: Principal = Depends(current_principal)) -> Principal:
        if not principal.has_role(minimum):
            raise HTTPException(
                status_code=403,
                detail=f"Action réservée au rôle « {minimum} » ou supérieur (rôle actuel : {principal.role}).",
            )
        return principal
    return _dep


require_analyst = require_role(ROLE_ANALYST)
require_admin = require_role(ROLE_ADMIN)


def _user_can_access(db: Session, principal: Principal, connection_id: int) -> bool:
    if principal.is_admin or principal.user_id is None:
        return True  # admin (ou repli dev) : accès à toutes les sources du tenant
    access = db.execute(
        select(ConnectionAccess).where(
            ConnectionAccess.user_id == principal.user_id,
            ConnectionAccess.connection_id == connection_id,
        )
    ).scalar_one_or_none()
    return access is not None


def get_owned_connection(
    connection_id: int,
    db: Session = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> Connection:
    """Charge une connexion en garantissant tenant + droit d'accès utilisateur."""
    conn = db.execute(
        select(Connection).where(
            Connection.id == connection_id,
            Connection.tenant_id == principal.tenant_id,
        )
    ).scalar_one_or_none()
    if conn is None:
        raise HTTPException(status_code=404, detail="Connexion introuvable pour ce tenant.")
    if not _user_can_access(db, principal, conn.id):
        raise HTTPException(
            status_code=403,
            detail="Vous n'avez pas accès à cette source. Demandez l'accès à un administrateur.",
        )
    return conn
