from __future__ import annotations

import pytest

from app.analysis.shadow.compare_exports import compare_exports


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
