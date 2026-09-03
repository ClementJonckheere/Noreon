from __future__ import annotations

import pytest

from app.analysis.shadow.compare_exports import compare_exports, summarize


def _export(*observations):
    return {"observations": list(observations)}


def _observation(ordinal, *, status="SUPPORTED", compile_ready=None, covers=True,
                 unresolved=True, version=None):
    item = {"goal_id": "g1", "status": status}
    if compile_ready is not None:
        item["compile_ready"] = compile_ready
    return {
        "campaign_case": {"ordinal": ordinal, "family": "impossible"},
        "statuses": {"llm": "ok"},
        "artifacts": {
            "interpretation": {"unresolved_terms": ([{
                "goal_id": "g1", "necessity": "required",
            }] if unresolved else [])},
            "resolved_plan": {
                "resolved_plan_schema_version": version,
                "coherence": {"covers_question": covers,
                              **({"coverage_status": "full" if covers else "none"} if version else {})},
                "resolution": [item],
            },
        },
    }


def test_compare_exposes_sincerity_and_compile_ready_improvements():
    before = _export(_observation(1))
    after = _export(_observation(
        1, status="UNSUPPORTED", compile_ready=False, covers=False, version="2.0"))
    comparison = compare_exports(before, after)
    assert comparison["same_campaign"]
    assert comparison["deltas"]["required_unresolved_supported"] == -1
    assert comparison["before"]["supported_compile_violations"] == 1
    assert comparison["after"]["supported_compile_violations"] == 0


def test_compare_rejects_different_campaign_cases():
    with pytest.raises(ValueError, match="campagnes différentes"):
        compare_exports(_export(_observation(1)), _export(_observation(2)))


def test_summary_exposes_p0c_acceptance_diagnostics():
    observation = {
        "campaign_case": {"ordinal": 1, "family": "simple"},
        "statuses": {"llm": "contract_error"},
        "repair": {"applied": True},
        "artifacts": {
            "normalized_interpretation": {
                "goals": [
                    {"id": "g1", "entity_ref": "concept:customer", "metrics": [],
                     "dimensions": [], "filters": [], "method": None, "temporal": None,
                     "ambiguities": []},
                    {"id": "g2", "entity_ref": None, "metrics": [], "dimensions": [],
                     "filters": [], "method": None, "temporal": None, "ambiguities": []},
                    {"id": "g3", "entity_ref": "concept:customer", "metrics": [],
                     "dimensions": [], "filters": [], "method": None, "temporal": None,
                     "ambiguities": []},
                ],
                "unresolved_terms": [
                    {"goal_id": "g1", "term": "benchmark externe", "necessity": "optional"},
                    {"goal_id": "g3", "term": "Clients", "necessity": "required"},
                ],
            },
            "capability_resolution": {"goals": [{
                "goal_id": "g3", "requirements": [
                    {"kind": "root_entity", "state": "unresolved",
                     "reason_code": "root_entity_missing"},
                    {"kind": "join_path", "state": "unresolved",
                     "reason_code": "no_validated_relation"},
                ],
            }]},
            "resolved_plan": {
                "catalog_snapshot": {
                    "entities": [{"ref": "concept:customer", "aliases": ["clients"]}],
                    "measures": [], "dimensions": [],
                    "relations": [
                        {"id": 1, "origin": "constraint", "executable": True,
                         "validation_status": "system_validated"},
                        {"id": 2, "origin": "inferred", "executable": False,
                         "validation_status": "unvalidated"},
                    ],
                },
                "coherence": {"covers_question": False, "coverage_status": "none"},
                "resolution": [
                    {"goal_id": "g1", "status": "SUPPORTED", "compile_ready": True,
                     "readiness": {"semantic_complete": True}},
                    {"goal_id": "g2", "status": "UNSUPPORTED", "compile_ready": False,
                     "readiness": {"semantic_complete": False}},
                    {"goal_id": "g3", "status": "UNSUPPORTED", "compile_ready": False,
                     "readiness": {"semantic_complete": False},
                     "operation": {"operator": "count_distinct", "metrics": [
                         {"aggregation": "sum"},
                     ]}},
                ],
            },
        },
    }
    result = summarize(_export(observation))
    assert result["goal_semantic_completeness"] == {
        "complete": 2, "total": 3, "rate": pytest.approx(2 / 3),
    }
    assert result["goal_without_operand_and_without_reason"] == 1
    assert result["diagnostic_cascade_count"] == 1
    assert result["known_refs_false_unresolved"] == 1
    assert result["goal_statuses"] == {"SUPPORTED": 1, "UNSUPPORTED": 2}
    assert result["compile_ready_goals"] == 1
    assert result["resolved_semantic_ready_goals"] == 1
    assert result["required_unresolved"] == 1
    assert result["optional_unresolved"] == 1
    assert result["relations_constraint_present"] == 1
    assert result["relations_inferred_nonvalidated_ignored"] == 1
    assert result["aggregation_contradictions"] == 1
    assert result["repairs"] == 1
    assert result["contract_errors"] == 1
    assert result["provider_errors"] == 0
