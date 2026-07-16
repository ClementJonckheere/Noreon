from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Connection(Base):
    """Connexion à une source de données (V0.1 : PostgreSQL uniquement).

    Les credentials sont chiffrés au repos (AES-256) dans `secret_encrypted`
    et ne sont jamais renvoyés en clair par l'API ni loggés.
    """

    __tablename__ = "connections"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_connection_tenant_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)

    name: Mapped[str] = mapped_column(String(255))
    engine: Mapped[str] = mapped_column(String(32), default="postgresql")
    host: Mapped[str] = mapped_column(String(255))
    port: Mapped[int] = mapped_column(default=5432)
    database: Mapped[str] = mapped_column(String(255))
    username: Mapped[str] = mapped_column(String(255))

    # base64(AES-256-GCM) de {"password": "..."} — jamais exposé
    secret_encrypted: Mapped[str] = mapped_column(String)

    # Options non sensibles : sslmode, ssh tunnel, schema par défaut…
    options: Mapped[dict] = mapped_column(JSON, default=dict)

    # Résultat de la vérification read-only (Module 1, exigence bloquante)
    is_read_only: Mapped[bool | None] = mapped_column(default=None)
    read_only_detail: Mapped[str | None] = mapped_column(String, default=None)

    status: Mapped[str] = mapped_column(String(32), default="untested")  # untested|ok|error
    last_error: Mapped[str | None] = mapped_column(String, default=None)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    last_scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
