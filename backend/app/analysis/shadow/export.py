"""Export read-only d'une baseline Shadow Planner.

Une baseline contient les artefacts d'observation nécessaires à une comparaison
avant/après, mais jamais la question brute. Les questions d'une campagne connue
sont rapprochées par leur HMAC tenant-scoped ; seules leur position et leur
famille sont exportées.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from app.analysis.planner_privacy import sanitize_question
from app.analysis.shadow.service import question_hash
from app.models.planner_shadow import PlannerShadowEvaluation

SHADOW_EXPORT_SCHEMA_VERSION = "1.1"


def latest_rows(session, *, limit: int, tenant_id: int | None = None):
    """Charge les ``limit`` observations les plus récentes, puis les remet dans
    l'ordre chronologique. Aucune mutation ni verrou d'écriture."""
    query = select(PlannerShadowEvaluation).order_by(
        PlannerShadowEvaluation.created_at.desc(),
        PlannerShadowEvaluation.id.desc(),
    )
    if tenant_id is not None:
        query = query.where(PlannerShadowEvaluation.tenant_id == tenant_id)
    rows = list(session.execute(query.limit(limit)).scalars().all())
    return sorted(rows, key=lambda row: (row.created_at, row.id))


def campaign_case_index(questions, *, tenant_ids: set[int], secret_key: str) -> dict:
    """Indexe un corpus connu par le même HMAC que le worker shadow.

    ``questions`` contient ``(family, question)``. Le texte ne sort jamais de
    cette fonction : l'export ne conserve que l'ordinal et la famille.
    """
    index: dict[tuple[int, str], dict] = {}
    for ordinal, (family, question) in enumerate(questions, start=1):
        safe_question, _ = sanitize_question(question)
        for tenant_id in tenant_ids:
            digest = question_hash(safe_question, tenant_id, secret_key)
            index[(tenant_id, digest)] = {"ordinal": ordinal, "family": family}
    return index


def serialize_row(row, *, matched_case: dict | None = None,
                  include_sanitized_question: bool = False) -> dict:
    """Projection stable d'une observation, sans prompt brut."""
    payload = {
        "id": row.id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "tenant_id": row.tenant_id,
        "space_id": row.space_id,
        "conversation_id": row.conversation_id,
        "connection_id": row.connection_id,
        "request_id": row.request_id,
        "question_hash": row.question_hash,
        "campaign_case": matched_case,
        "planner": {
            "mode": row.planner_mode,
            "sample_rate": row.sample_rate,
            "candidate_model": row.candidate_model,
            "routing_reason": row.routing_reason,
            "routing_matched_rule": row.routing_matched_rule,
            "routing_tier": row.routing_tier,
            "escalated": row.escalated,
            "previous_model": row.previous_model,
            "escalation_reason": row.escalation_reason,
        },
        "versions": {
            "interpretation_schema": row.interpretation_schema_version,
            "goal_types": row.goal_types_version,
            "router": row.router_version,
            "planner_prompt": row.planner_prompt_version,
            "comparator": row.comparator_version,
            "projection": row.projection_version,
            "analytical_safety": row.analytical_safety_version,
        },
        "statuses": {
            "llm": row.llm_status,
            "fallback": row.fallback_status,
            "comparison": row.comparison_outcome,
            "analytical_safety": row.analytical_safety,
            "review": row.review_status,
        },
        "artifacts": {
            "interpretation": row.llm_plan_json,
            "provider_raw": getattr(row, "provider_raw_json", None),
            "normalized_interpretation": getattr(row, "normalized_interpretation_json", None),
            "capability_resolution": row.capability_resolution_json,
            "resolved_plan": row.resolved_plan_json,
            "legacy_execution_projection": row.legacy_execution_projection_json,
            "llm_projection": row.llm_projection_json,
            "fallback_projection": row.fallback_projection_json,
            "capability_states": row.capability_states_json,
            "comparison": row.comparison_json,
            "analytical_safety": row.analytical_safety_json,
        },
        "repair": {
            "applied": row.repair_applied,
            "type": row.repair_type,
            "details": row.repair_details_json,
        },
        "performance": {
            "llm_latency_ms": row.llm_latency_ms,
            "fallback_latency_ms": row.fallback_latency_ms,
            "tokens_prompt": row.tokens_prompt,
            "tokens_completion": row.tokens_completion,
            "tokens_total": row.tokens_total,
            "estimated_cost": row.estimated_cost,
        },
        "error": {"kind": row.error_kind, "detail": row.error_detail},
    }
    if include_sanitized_question:
        payload["question_sanitized"] = row.question_sanitized
    return payload


def build_export(rows, *, questions, secret_key: str, expected_count: int,
                 include_sanitized_question: bool = False,
                 exported_at: datetime | None = None) -> dict:
    """Construit et valide un document de baseline sérialisable en JSON."""
    if len(rows) != expected_count:
        raise ValueError(f"baseline incomplète : {len(rows)} observations, {expected_count} attendues")
    request_ids = [row.request_id for row in rows]
    if len(set(request_ids)) != len(request_ids):
        raise ValueError("baseline invalide : request_id dupliqué")

    tenant_ids = {int(row.tenant_id) for row in rows}
    cases = campaign_case_index(questions, tenant_ids=tenant_ids, secret_key=secret_key)
    serialized = [
        serialize_row(
            row,
            matched_case=cases.get((int(row.tenant_id), row.question_hash)),
            include_sanitized_question=include_sanitized_question,
        )
        for row in rows
    ]
    matched = sum(item["campaign_case"] is not None for item in serialized)
    now = exported_at or datetime.now(timezone.utc)
    return {
        "shadow_export_schema_version": SHADOW_EXPORT_SCHEMA_VERSION,
        "exported_at": now.isoformat(),
        "row_count": len(serialized),
        "expected_count": expected_count,
        "distinct_request_ids": len(set(request_ids)),
        "matched_campaign_cases": matched,
        "privacy": {
            "raw_questions_included": False,
            "sanitized_questions_included": include_sanitized_question,
            "campaign_text_included": False,
        },
        "observations": serialized,
    }
