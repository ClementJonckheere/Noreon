"""Phase 2 — C5 : télémétrie du Shadow Planner.

Domaine de persistance STRICTEMENT séparé (correctif utilisateur) :
- `analysis_plans` = plans réellement utilisés (n'existe pas encore) ;
- `analysis_runs`  = exécutions réelles (n'existe pas encore) ;
- `planner_shadow_evaluations` = candidats LLM + télémétrie expérimentale (ICI).

Le shadow ne doit JAMAIS écrire ailleurs. Aucun prompt brut, aucune PII :
`question_hash` (HMAC serveur, tenant-scoped) par défaut ; le plan complet est
opt-in avec rétention courte ; projections/comparaisons conservées plus longtemps.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class PlannerShadowEvaluation(Base):
    __tablename__ = "planner_shadow_evaluations"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    # Corrélation
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    space_id: Mapped[int | None] = mapped_column(default=None)
    conversation_id: Mapped[int | None] = mapped_column(default=None)
    connection_id: Mapped[int | None] = mapped_column(default=None)
    request_id: Mapped[str] = mapped_column(String(64), index=True)

    # Confidentialité : HMAC (jamais le prompt brut) ; sanitizé opt-in.
    question_hash: Mapped[str] = mapped_column(String(64))
    question_sanitized: Mapped[str | None] = mapped_column(String, default=None)

    # Mode & sampling
    planner_mode: Mapped[str] = mapped_column(String(16))
    sample_rate: Mapped[float] = mapped_column(default=1.0)

    # Routeur (candidat)
    candidate_model: Mapped[str | None] = mapped_column(String(64), default=None)
    routing_reason: Mapped[str | None] = mapped_column(String, default=None)
    routing_matched_rule: Mapped[str | None] = mapped_column(String(128), default=None)
    routing_tier: Mapped[str | None] = mapped_column(String(16), default=None)
    escalated: Mapped[bool] = mapped_column(default=False)
    previous_model: Mapped[str | None] = mapped_column(String(64), default=None)
    escalation_reason: Mapped[str | None] = mapped_column(String, default=None)

    # Versions du contrat ET du système d'observation (correctif #6)
    interpretation_schema_version: Mapped[str | None] = mapped_column(String(16), default=None)
    goal_types_version: Mapped[str | None] = mapped_column(String(16), default=None)
    router_version: Mapped[str | None] = mapped_column(String(16), default=None)
    planner_prompt_version: Mapped[str | None] = mapped_column(String(16), default=None)
    comparator_version: Mapped[str | None] = mapped_column(String(16), default=None)
    projection_version: Mapped[str | None] = mapped_column(String(16), default=None)

    # Statuts
    llm_status: Mapped[str] = mapped_column(String(24), default="skipped")   # ok|contract_error|network_error|provider_error|timeout|skipped
    fallback_status: Mapped[str | None] = mapped_column(String(24), default=None)

    # Plans / projections (rétention différenciée)
    llm_plan_json: Mapped[dict | None] = mapped_column(JSON, default=None)          # rétention COURTE (opt-in)
    llm_projection_json: Mapped[dict | None] = mapped_column(JSON, default=None)     # durable
    fallback_projection_json: Mapped[dict | None] = mapped_column(JSON, default=None)  # durable
    plan_purge_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    # Comparaison (renommé : comparison_outcome, pas divergence_class)
    comparison_outcome: Mapped[str | None] = mapped_column(String(24), default=None, index=True)
    comparison_json: Mapped[dict | None] = mapped_column(JSON, default=None)

    # Réparation
    repair_applied: Mapped[bool] = mapped_column(default=False)
    repair_type: Mapped[str | None] = mapped_column(String(32), default=None)
    repair_details_json: Mapped[dict | None] = mapped_column(JSON, default=None)

    # Perf / coût
    llm_latency_ms: Mapped[int | None] = mapped_column(default=None)
    fallback_latency_ms: Mapped[int | None] = mapped_column(default=None)
    tokens_prompt: Mapped[int | None] = mapped_column(default=None)
    tokens_completion: Mapped[int | None] = mapped_column(default=None)
    tokens_total: Mapped[int | None] = mapped_column(default=None)
    estimated_cost: Mapped[float | None] = mapped_column(default=None)

    # Erreurs
    error_kind: Mapped[str | None] = mapped_column(String(24), default=None)
    error_detail: Mapped[str | None] = mapped_column(String, default=None)

    # Revue humaine échantillonnée des divergences matérielles
    review_status: Mapped[str] = mapped_column(String(24), default="none")   # none|sampled_for_review|reviewed
