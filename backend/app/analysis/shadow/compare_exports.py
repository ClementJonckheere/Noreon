"""Comparaison déterministe de deux exports shadow de la même campagne."""
from __future__ import annotations

from collections import Counter


def _case_key(observation: dict) -> tuple[int, str]:
    case = observation.get("campaign_case") or {}
    ordinal, family = case.get("ordinal"), case.get("family")
    if not isinstance(ordinal, int) or not isinstance(family, str):
        raise ValueError("export non comparable : observation sans campaign_case")
    return ordinal, family


def _facts(observation: dict) -> dict:
    artifacts = observation.get("artifacts") or {}
    interpretation = artifacts.get("interpretation") or {}
    resolved = artifacts.get("resolved_plan") or {}
    items = resolved.get("resolution") or []
    coherence = resolved.get("coherence") or {}
    required_goal_ids = {
        term.get("goal_id") for term in (interpretation.get("unresolved_terms") or [])
        if isinstance(term, dict) and (term.get("necessity") or "required") == "required"
    }
    supported = {item.get("goal_id") for item in items if item.get("status") == "SUPPORTED"}
    coverage_status = coherence.get("coverage_status")
    if coverage_status is None:
        coverage_status = "legacy_full" if coherence.get("covers_question") else "legacy_not_full"
    return {
        "llm_status": (observation.get("statuses") or {}).get("llm"),
        "coverage_status": coverage_status,
        "covers_question": bool(coherence.get("covers_question")),
        "goal_statuses": sorted(str(item.get("status")) for item in items),
        "required_unresolved_supported": sorted(required_goal_ids & supported),
        "supported_count": len(supported),
        "supported_compile_ready": sum(
            item.get("status") == "SUPPORTED" and item.get("compile_ready") is True for item in items),
        "supported_compile_violations": sorted(
            item.get("goal_id") for item in items
            if item.get("status") == "SUPPORTED" and item.get("compile_ready") is not True),
        "resolved_plan_version": resolved.get("resolved_plan_schema_version"),
    }


def summarize(export: dict) -> dict:
    observations = export.get("observations") or []
    facts = [_facts(observation) for observation in observations]
    return {
        "rows": len(observations),
        "llm_statuses": dict(sorted(Counter(fact["llm_status"] for fact in facts).items(),
                                    key=lambda item: str(item[0]))),
        "coverage_statuses": dict(sorted(Counter(fact["coverage_status"] for fact in facts).items())),
        "covers_question": sum(fact["covers_question"] for fact in facts),
        "goal_statuses": dict(sorted(Counter(status for fact in facts
                                              for status in fact["goal_statuses"]).items())),
        "required_unresolved_supported": sum(len(fact["required_unresolved_supported"]) for fact in facts),
        "supported_goals": sum(fact["supported_count"] for fact in facts),
        "supported_compile_ready": sum(fact["supported_compile_ready"] for fact in facts),
        "supported_compile_violations": sum(len(fact["supported_compile_violations"]) for fact in facts),
        "resolved_plan_versions": dict(sorted(Counter(
            str(fact["resolved_plan_version"]) for fact in facts).items())),
    }


def compare_exports(before: dict, after: dict) -> dict:
    before_observations = before.get("observations") or []
    after_observations = after.get("observations") or []
    before_rows = {_case_key(observation): observation for observation in before_observations}
    after_rows = {_case_key(observation): observation for observation in after_observations}
    if len(before_rows) != len(before_observations) or len(after_rows) != len(after_observations):
        raise ValueError("export non comparable : campaign_case dupliqué")
    if set(before_rows) != set(after_rows):
        missing_after = sorted(set(before_rows) - set(after_rows))
        missing_before = sorted(set(after_rows) - set(before_rows))
        raise ValueError(
            f"campagnes différentes : absents après={missing_after}, absents avant={missing_before}")
    if not before_rows:
        raise ValueError("exports vides")

    cases = []
    for key in sorted(before_rows):
        before_facts, after_facts = _facts(before_rows[key]), _facts(after_rows[key])
        if before_facts != after_facts:
            cases.append({
                "ordinal": key[0], "family": key[1],
                "before": before_facts, "after": after_facts,
            })
    before_summary, after_summary = summarize(before), summarize(after)
    deltas = {
        key: after_summary[key] - before_summary[key]
        for key in (
            "covers_question", "required_unresolved_supported", "supported_goals",
            "supported_compile_ready", "supported_compile_violations",
        )
    }
    return {
        "same_campaign": True,
        "case_count": len(before_rows),
        "before": before_summary,
        "after": after_summary,
        "deltas": deltas,
        "changed_cases": cases,
    }
