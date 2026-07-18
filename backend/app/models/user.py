from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base

# Rôles (Module 11) : administrateur > analyste > lecteur.
ROLE_ADMIN = "admin"
ROLE_ANALYST = "analyst"
ROLE_READER = "reader"
ROLE_ORDER = {ROLE_READER: 0, ROLE_ANALYST: 1, ROLE_ADMIN: 2}


class User(Base):
    """Utilisateur d'un espace entreprise (tenant), avec rôle et MFA (Module 11)."""

    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("tenant_id", "email", name="uq_user_tenant_email"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)

    email: Mapped[str] = mapped_column(String(255), index=True)
    full_name: Mapped[str] = mapped_column(String(255), default="")
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default=ROLE_ANALYST)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    mfa_secret: Mapped[str | None] = mapped_column(String(64), default=None)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class ConnectionAccess(Base):
    """Droit d'accès d'un utilisateur à une connexion source (Module 11).

    « Un utilisateur ne peut interroger que les sources auxquelles il a accès. »
    Les administrateurs accèdent à tout sans entrée explicite.
    """

    __tablename__ = "connection_access"
    __table_args__ = (
        UniqueConstraint("user_id", "connection_id", name="uq_access_user_connection"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    connection_id: Mapped[int] = mapped_column(ForeignKey("connections.id", ondelete="CASCADE"), index=True)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
