from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ProfilingJob(Base):
    """Tâche asynchrone de profilage (Module 3).

    Exécutée à faible priorité par le worker, avec limitation de charge
    (une requête de profilage à la fois par connexion).
    """

    __tablename__ = "profiling_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    connection_id: Mapped[int] = mapped_column(ForeignKey("connections.id", ondelete="CASCADE"), index=True)
    scope: Mapped[str] = mapped_column(String(32), default="all")  # all|table:<name>
    status: Mapped[str] = mapped_column(String(16), default="queued")  # queued|running|done|error
    priority: Mapped[int] = mapped_column(default=10)  # + grand = + faible priorité
    tables_total: Mapped[int] = mapped_column(default=0)
    tables_done: Mapped[int] = mapped_column(default=0)
    error: Mapped[str | None] = mapped_column(String, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class ColumnProfile(Base):
    """Statistiques de contenu d'une colonne (Module 3)."""

    __tablename__ = "column_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    connection_id: Mapped[int] = mapped_column(ForeignKey("connections.id", ondelete="CASCADE"), index=True)
    schema_name: Mapped[str] = mapped_column(String(255))
    table_name: Mapped[str] = mapped_column(String(255))
    column_name: Mapped[str] = mapped_column(String(255))

    sampled: Mapped[bool] = mapped_column(Boolean, default=False)
    sample_size: Mapped[int] = mapped_column(default=0)
    row_count_estimate: Mapped[int | None] = mapped_column(default=None)

    null_rate: Mapped[float | None] = mapped_column(Float, default=None)
    null_count: Mapped[int | None] = mapped_column(default=None)
    non_null_count: Mapped[int | None] = mapped_column(default=None)
    # Audit de la validité : nombre exact de valeurs non conformes au format
    # attendu (email, téléphone, IBAN, SIRET, date-en-texte) + format vérifié.
    invalid_count: Mapped[int | None] = mapped_column(default=None)
    format_checked: Mapped[str | None] = mapped_column(String(32), default=None)
    distinct_count: Mapped[int | None] = mapped_column(default=None)
    distinct_ratio: Mapped[float | None] = mapped_column(Float, default=None)
    min_value: Mapped[str | None] = mapped_column(String, default=None)
    max_value: Mapped[str | None] = mapped_column(String, default=None)
    mean_value: Mapped[float | None] = mapped_column(Float, default=None)
    avg_length: Mapped[float | None] = mapped_column(Float, default=None)

    declared_type: Mapped[str | None] = mapped_column(String(128), default=None)
    detected_type: Mapped[str | None] = mapped_column(String(64), default=None)  # type réel inféré
    pii_type: Mapped[str | None] = mapped_column(String(32), default=None)  # email|phone|iban|...

    top_values: Mapped[list] = mapped_column(JSON, default=list)
    sample_values: Mapped[list] = mapped_column(JSON, default=list)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
