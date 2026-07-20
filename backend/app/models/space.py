"""Espaces (workspaces d'équipe) et gouvernance des données par espace.

Modèle hiérarchique :
    Univers (= Tenant) ── contient ──▶ Espaces ── rattache ──▶ Connexions (BDD)

Chaque espace est le périmètre d'une équipe (CRM, Achat…) : son propre chat,
son propre schéma, ses propres droits. Un univers importe des BDD (au niveau
tenant) ; l'administrateur DSI les rattache aux espaces et **gouverne** ce qui
est accessible : cocher/décocher des tables et des colonnes par espace.

Politique de gouvernance : par défaut TOUT est accessible ; on ne stocke que les
EXCEPTIONS (une ligne `enabled=false` = élément masqué pour l'espace). C'est
léger (pas une ligne par colonne) et explicite.
"""
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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Space(Base):
    __tablename__ = "spaces"
    __table_args__ = (UniqueConstraint("tenant_id", "slug", name="uq_space_tenant_slug"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    connections: Mapped[list["SpaceConnection"]] = relationship(
        back_populates="space", cascade="all, delete-orphan"
    )
    members: Mapped[list["SpaceMember"]] = relationship(
        back_populates="space", cascade="all, delete-orphan"
    )


class SpaceConnection(Base):
    """Rattachement d'une BDD (connexion tenant) à un espace (n-n)."""

    __tablename__ = "space_connections"
    __table_args__ = (UniqueConstraint("space_id", "connection_id", name="uq_space_connection"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    space_id: Mapped[int] = mapped_column(ForeignKey("spaces.id", ondelete="CASCADE"), index=True)
    connection_id: Mapped[int] = mapped_column(ForeignKey("connections.id", ondelete="CASCADE"), index=True)

    space: Mapped[Space] = relationship(back_populates="connections")


class SpaceMember(Base):
    """Appartenance d'un utilisateur à un espace (qui peut l'ouvrir/l'utiliser)."""

    __tablename__ = "space_members"
    __table_args__ = (UniqueConstraint("space_id", "user_id", name="uq_space_member"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    space_id: Mapped[int] = mapped_column(ForeignKey("spaces.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16), default="member")  # member|manager

    space: Mapped[Space] = relationship(back_populates="members")


class SpaceTableAccess(Base):
    """Exception de gouvernance au niveau TABLE (enabled=false → masquée)."""

    __tablename__ = "space_table_access"
    __table_args__ = (
        UniqueConstraint("space_id", "connection_id", "schema_name", "table_name",
                         name="uq_space_table_access"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    space_id: Mapped[int] = mapped_column(ForeignKey("spaces.id", ondelete="CASCADE"), index=True)
    connection_id: Mapped[int] = mapped_column(ForeignKey("connections.id", ondelete="CASCADE"), index=True)
    schema_name: Mapped[str] = mapped_column(String(255))
    table_name: Mapped[str] = mapped_column(String(255))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class SpaceColumnAccess(Base):
    """Exception de gouvernance au niveau COLONNE (enabled=false → masquée)."""

    __tablename__ = "space_column_access"
    __table_args__ = (
        UniqueConstraint("space_id", "connection_id", "schema_name", "table_name", "column_name",
                         name="uq_space_column_access"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    space_id: Mapped[int] = mapped_column(ForeignKey("spaces.id", ondelete="CASCADE"), index=True)
    connection_id: Mapped[int] = mapped_column(ForeignKey("connections.id", ondelete="CASCADE"), index=True)
    schema_name: Mapped[str] = mapped_column(String(255))
    table_name: Mapped[str] = mapped_column(String(255))
    column_name: Mapped[str] = mapped_column(String(255))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
