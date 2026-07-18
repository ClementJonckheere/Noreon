from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Tenant(Base):
    """Espace entreprise strictement isolé (multi-tenant)."""

    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    settings: Mapped["TenantSettings"] = relationship(
        back_populates="tenant", uselist=False, cascade="all, delete-orphan"
    )


class TenantSettings(Base):
    """Réglages configurables par entreprise (garde-fous, LLM, pondérations qualité)."""

    __tablename__ = "tenant_settings"

    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True)

    llm_provider: Mapped[str] = mapped_column(String(32), default="heuristic")
    llm_model: Mapped[str] = mapped_column(String(128), default="")

    sql_timeout_seconds: Mapped[int] = mapped_column(default=60)
    sql_row_limit: Mapped[int] = mapped_column(default=10_000)
    sql_max_cost: Mapped[float] = mapped_column(default=1_000_000.0)
    sql_max_concurrent_per_connection: Mapped[int] = mapped_column(default=1)

    # Pondérations du score qualité (Module 4) — préparé pour V0.2
    quality_weights: Mapped[dict] = mapped_column(
        JSON,
        default=lambda: {
            "completeness": 0.30,
            "validity": 0.25,
            "uniqueness": 0.15,
            "consistency": 0.15,
            "freshness": 0.15,
        },
    )

    # Préférences de l'entreprise (V0.4) : type de graphique par défaut,
    # apprentissage automatique inter-connexions, etc.
    preferences: Mapped[dict] = mapped_column(
        JSON,
        default=lambda: {
            "preferred_chart_type": None,  # None = choix automatique
            "auto_learn": True,            # mémoire sémantique inter-connexions
            "auto_save_definitions": True, # proposer d'enregistrer les définitions clarifiées
        },
    )

    tenant: Mapped[Tenant] = relationship(back_populates="settings")
