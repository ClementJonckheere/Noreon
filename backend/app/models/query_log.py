from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class QueryLog(Base):
    """Journal d'audit immuable des exécutions SQL (Module 8).

    « qui a exécuté quoi, quand, sur quelle base, avec quel résultat ».
    Aucune ligne brute identifiante n'est stockée ici — uniquement les
    métadonnées d'exécution et la transparence SQL.
    """

    __tablename__ = "query_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    connection_id: Mapped[int] = mapped_column(ForeignKey("connections.id", ondelete="CASCADE"), index=True)
    user_ref: Mapped[str] = mapped_column(String(255), default="system")

    question: Mapped[str | None] = mapped_column(String, default=None)
    sql: Mapped[str] = mapped_column(String)
    tables_used: Mapped[list] = mapped_column(JSON, default=list)
    columns_used: Mapped[list] = mapped_column(JSON, default=list)
    filters: Mapped[list] = mapped_column(JSON, default=list)

    status: Mapped[str] = mapped_column(String(16), default="ok")  # ok|blocked|error
    block_reason: Mapped[str | None] = mapped_column(String, default=None)
    estimated_cost: Mapped[float | None] = mapped_column(default=None)
    row_count: Mapped[int | None] = mapped_column(default=None)
    duration_ms: Mapped[int | None] = mapped_column(default=None)
    truncated: Mapped[bool] = mapped_column(default=False)

    confidence: Mapped[dict] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
