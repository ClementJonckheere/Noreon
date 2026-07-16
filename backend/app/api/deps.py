"""Dépendances FastAPI : résolution du tenant (isolation multi-entreprise).

En V0.1, le tenant est résolu via l'en-tête `X-Tenant` (slug). L'authentification
complète (email/mot de passe, SSO SAML/OIDC, rôles, MFA — Module 11) est prévue
en V1.0. Le tenant par défaut « demo » est créé automatiquement pour faciliter
la prise en main.
"""
from __future__ import annotations

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models.connection import Connection
from app.models.tenant import Tenant, TenantSettings

DEFAULT_TENANT_SLUG = "demo"


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


def current_tenant(
    x_tenant: str = Header(default=DEFAULT_TENANT_SLUG, alias="X-Tenant"),
    db: Session = Depends(get_db),
) -> Tenant:
    return get_or_create_tenant(db, x_tenant or DEFAULT_TENANT_SLUG)


def get_owned_connection(
    connection_id: int,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(current_tenant),
) -> Connection:
    """Charge une connexion en garantissant l'isolation du tenant."""
    conn = db.execute(
        select(Connection).where(
            Connection.id == connection_id,
            Connection.tenant_id == tenant.id,
        )
    ).scalar_one_or_none()
    if conn is None:
        raise HTTPException(status_code=404, detail="Connexion introuvable pour ce tenant.")
    return conn
