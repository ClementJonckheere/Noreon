from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Alert(Base):
    """Alerte simple (V0.4).

    Surveille une mesure scalaire (définition métier ou expression) et se
    déclenche selon une condition simple :
    - gt / lt : la valeur dépasse / passe sous un seuil ;
    - pct_drop : chute de plus de N% par rapport à la mesure précédente ;
    - pct_change : variation (hausse ou baisse) de plus de N%.

    L'évaluation passe par les garde-fous d'exécution (read-only, timeout,
    EXPLAIN). Chaque évaluation produit un AlertEvent (historique).
    """

    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    connection_id: Mapped[int] = mapped_column(ForeignKey("connections.id", ondelete="CASCADE"), index=True)

    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(String, default="")

    # Source de la mesure : soit une définition, soit une expression directe.
    definition_id: Mapped[int | None] = mapped_column(
        ForeignKey("business_definitions.id", ondelete="SET NULL"), default=None
    )
    schema_name: Mapped[str] = mapped_column(String(255), default="public")
    table_name: Mapped[str | None] = mapped_column(String(255), default=None)
    expression: Mapped[str | None] = mapped_column(String, default=None)  # ex. "sum(amount_ttc)"
    filter_sql: Mapped[str | None] = mapped_column(String, default=None)

    comparison: Mapped[str] = mapped_column(String(16))  # gt|lt|pct_drop|pct_change
    threshold: Mapped[float] = mapped_column(Float)

    last_value: Mapped[float | None] = mapped_column(Float, default=None)
    previous_value: Mapped[float | None] = mapped_column(Float, default=None)
    last_status: Mapped[str] = mapped_column(String(16), default="new")  # new|ok|triggered|error
    last_message: Mapped[str | None] = mapped_column(String, default=None)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    events: Mapped[list["AlertEvent"]] = relationship(
        back_populates="alert", cascade="all, delete-orphan"
    )


class AlertEvent(Base):
    """Historique d'évaluation d'une alerte."""

    __tablename__ = "alert_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    alert_id: Mapped[int] = mapped_column(ForeignKey("alerts.id", ondelete="CASCADE"), index=True)
    value: Mapped[float | None] = mapped_column(Float, default=None)
    status: Mapped[str] = mapped_column(String(16))  # ok|triggered|error
    message: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    alert: Mapped[Alert] = relationship(back_populates="events")
