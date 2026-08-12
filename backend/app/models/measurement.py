"""Mesure d'une action — protocole défini à la RÉTENTION, baseline figé au moment
réel de la MISE EN ŒUVRE (`implemented_at`), résultat CONTRÔLÉ (vs témoins).

Séparation stricte : un `MeasurementPlan` par décision (le protocole), plusieurs
`MeasurementRun` (J+30, J+90…) — on n'écrase jamais une mesure. Une mesure ne
proclame pas la causalité : `raw_delta` vs `adjusted_delta` (écart au témoin), et
le résultat est classé `objectif_atteint | objectif_non_atteint | inconclusif` —
jamais « réussie » automatique.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class MeasurementPlan(Base):
    __tablename__ = "measurement_plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    decision_id: Mapped[int] = mapped_column(ForeignKey("decision_records.id", ondelete="CASCADE"), index=True)
    tenant_id: Mapped[int] = mapped_column(Integer, index=True)
    connection_id: Mapped[int] = mapped_column(Integer)

    # impact | performance | completion | diagnostic — le KPI de l'ACTION, pas du diagnostic.
    measure_type: Mapped[str] = mapped_column(String(16), default="impact")
    metric_concept_id: Mapped[str] = mapped_column(String(64), default="revenue")
    metric_label: Mapped[str] = mapped_column(String(128), default="Chiffre d'affaires")

    scope: Mapped[dict] = mapped_column(JSON, default=dict)          # {table, dim, column, values:[...]}
    control_scope: Mapped[dict | None] = mapped_column(JSON, default=None)  # {values:[...]}
    # Sélection des témoins FIGÉE avant l'observation (jamais choisie à J+30 pour
    # produire un beau résultat) : {control_ids, matching_features, matching_score,
    # pretrend_score, selection_at}. C'est la garantie méthodologique.
    control_selection: Mapped[dict | None] = mapped_column(JSON, default=None)
    comparison: Mapped[str] = mapped_column(String(24), default="matched_control")
    baseline_window_days: Mapped[int] = mapped_column(Integer, default=30)
    observation_window_days: Mapped[int] = mapped_column(Integer, default=30)
    threshold: Mapped[float] = mapped_column(Float, default=0.02)     # objectif (fraction)
    protocol_version: Mapped[int] = mapped_column(Integer, default=1)

    # Figés à la MISE EN ŒUVRE (jamais avant, jamais envoyés par le front).
    implemented_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    baseline_target: Mapped[float | None] = mapped_column(Float, default=None)
    baseline_control: Mapped[float | None] = mapped_column(Float, default=None)
    baseline_frozen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    baseline_sql: Mapped[str | None] = mapped_column(String, default=None)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    runs: Mapped[list["MeasurementRun"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan", order_by="MeasurementRun.created_at",
    )


class MeasurementRun(Base):
    __tablename__ = "measurement_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("measurement_plans.id", ondelete="CASCADE"), index=True)

    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    horizon_days: Mapped[int] = mapped_column(Integer, default=30)   # J+N depuis implemented_at

    baseline_target: Mapped[float | None] = mapped_column(Float, default=None)
    baseline_control: Mapped[float | None] = mapped_column(Float, default=None)
    observed_target: Mapped[float | None] = mapped_column(Float, default=None)
    observed_control: Mapped[float | None] = mapped_column(Float, default=None)

    raw_delta: Mapped[float | None] = mapped_column(Float, default=None)       # % cible
    control_delta: Mapped[float | None] = mapped_column(Float, default=None)   # % témoins
    adjusted_delta: Mapped[float | None] = mapped_column(Float, default=None)  # points (cible − témoins)

    # objectif_atteint | objectif_non_atteint | inconclusif
    result: Mapped[str] = mapped_column(String(24), default="inconclusif")
    limitations: Mapped[list] = mapped_column(JSON, default=list)
    observation_sql: Mapped[str | None] = mapped_column(String, default=None)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    plan: Mapped[MeasurementPlan] = relationship(back_populates="runs")
