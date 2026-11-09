"""Baseline shadow : export complet, déterministe et sans prompt brut."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.analysis.planner_privacy import sanitize_question
from app.analysis.shadow.export import build_export
from app.analysis.shadow.service import question_hash


def _row(request_id: str, question: str, *, tenant_id: int = 7, secret: str = "secret"):
    safe, _ = sanitize_question(question)
    values = {
        "id": 1,
        "created_at": datetime(2026, 8, 26, tzinfo=timezone.utc),
        "tenant_id": tenant_id,
        "space_id": None,
        "conversation_id": None,
        "connection_id": 4,
        "request_id": request_id,
        "question_hash": question_hash(safe, tenant_id, secret),
        "question_sanitized": safe,
        "planner_mode": "shadow",
        "sample_rate": 1.0,
        "candidate_model": "main",
        "routing_reason": "test",
        "routing_matched_rule": None,
        "routing_tier": "complex",
        "escalated": False,
        "previous_model": None,
        "escalation_reason": None,
        "interpretation_schema_version": "1.0",
        "goal_types_version": "1.0",
        "router_version": "1.0",
        "planner_prompt_version": "1.0",
        "comparator_version": "1.1",
        "projection_version": "1.1",
        "analytical_safety_version": "1.0",
        "llm_status": "ok",
        "fallback_status": "answered",
        "comparison_outcome": "not_comparable",
        "analytical_safety": "not_comparable",
        "review_status": "none",
        "llm_plan_json": {"goals": []},
        "capability_resolution_json": {"goals": []},
        "resolved_plan_json": {"resolution": []},
        "legacy_execution_projection_json": {"sql_present": True},
        "llm_projection_json": {},
        "fallback_projection_json": {},
        "capability_states_json": {"available": 1},
        "comparison_json": {},
        "analytical_safety_json": {},
        "repair_applied": False,
        "repair_type": None,
        "repair_details_json": None,
        "llm_latency_ms": 10,
        "fallback_latency_ms": 5,
        "tokens_prompt": 1,
        "tokens_completion": 2,
        "tokens_total": 3,
        "estimated_cost": None,
        "error_kind": None,
        "error_detail": None,
    }
    return SimpleNamespace(**values)


def test_export_matches_known_cases_without_question_text():
    questions = [("simple", "Combien d'entités ?"), ("optional", "Résume avec un axe externe")]
    rows = [_row("r1", questions[0][1]), _row("r2", questions[1][1])]
    payload = build_export(
        rows,
        questions=questions,
        secret_key="secret",
        expected_count=2,
        exported_at=datetime(2026, 8, 26, tzinfo=timezone.utc),
    )

    assert payload["row_count"] == payload["distinct_request_ids"] == 2
    assert payload["matched_campaign_cases"] == 2
    assert payload["observations"][0]["campaign_case"] == {"ordinal": 1, "family": "simple"}
    assert "question_sanitized" not in payload["observations"][0]
    assert payload["privacy"]["raw_questions_included"] is False
    assert payload["observations"][0]["artifacts"]["resolved_plan"] == {"resolution": []}


def test_export_refuses_incomplete_or_duplicate_baseline():
    row = _row("same", "Question")
    with pytest.raises(ValueError, match="incomplète"):
        build_export([row], questions=[], secret_key="secret", expected_count=2)
    with pytest.raises(ValueError, match="dupliqué"):
        build_export([row, _row("same", "Autre")], questions=[], secret_key="secret", expected_count=2)
