"""Diagnostics d'acceptation P0-C calculés depuis les artefacts shadow.

Le module est volontairement pur : il accepte les observations sérialisées par
``shadow_export`` et ne consulte ni la base ni le catalogue vivant.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter


def _normalized_text(value) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").casefold())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(re.findall(r"[a-z0-9_:]+", text))


def _artifacts(observation: dict) -> tuple[dict, dict, dict]:
    artifacts = observation.get("artifacts") or {}
    interpretation = (
        artifacts.get("normalized_interpretation")
        or artifacts.get("interpretation")
        or {}
    )
    return (
        interpretation,
        artifacts.get("capability_resolution") or {},
        artifacts.get("resolved_plan") or {},
    )


def _goal_has_operand(goal: dict) -> bool:
    return bool(
        goal.get("entity_ref")
        or goal.get("metrics")
        or goal.get("dimensions")
        or goal.get("filters")
        or goal.get("method")
        or goal.get("temporal")
    )


def _known_names(snapshot: dict) -> set[str]:
    names: set[str] = set()
    for key in ("entities", "measures", "dimensions"):
        for item in snapshot.get(key) or []:
            if not isinstance(item, dict):
                continue
            for value in [item.get("ref"), *(item.get("aliases") or [])]:
                normalized = _normalized_text(value)
                if normalized:
                    names.add(normalized)
    return names


def _aggregation_contradictions(goals: list[dict], items: list[dict]) -> int:
    goals_by_id = {goal.get("id"): goal for goal in goals if isinstance(goal, dict)}
    count = 0
    for item in items:
        operation = item.get("operation") or {}
        metrics = operation.get("metrics") or []
        aggregations = {metric.get("aggregation") for metric in metrics if isinstance(metric, dict)}
        if operation.get("operator") == "count_distinct" and "sum" in aggregations:
            count += 1
            continue
        goal = goals_by_id.get(item.get("goal_id")) or {}
        intent = _normalized_text(goal.get("intent_text"))
        if re.search(r"\b(avg|average|mean|moyenne?s?|moyens?)\b", intent) and "sum" in aggregations:
            count += 1
    return count


def observation_diagnostics(observation: dict) -> dict:
    interpretation, capability, resolved = _artifacts(observation)
    goals = [goal for goal in (interpretation.get("goals") or []) if isinstance(goal, dict)]
    unresolved = [
        term for term in (interpretation.get("unresolved_terms") or [])
        if isinstance(term, dict)
    ]
    unresolved_by_goal = Counter(term.get("goal_id") for term in unresolved)
    items = [item for item in (resolved.get("resolution") or []) if isinstance(item, dict)]
    items_by_goal = {item.get("goal_id"): item for item in items}

    resolved_semantic_ready = sum(
        (items_by_goal.get(goal.get("id"), {}).get("readiness") or {}).get(
            "semantic_complete"
        ) is True
        for goal in goals
    )
    without_operand_or_reason = sum(
        not _goal_has_operand(goal)
        and not goal.get("ambiguities")
        and not unresolved_by_goal.get(goal.get("id"), 0)
        for goal in goals
    )
    # Complétude de l'interprétation C4 : un goal porte un opérande exploitable,
    # ou explique explicitement son absence. Elle reste donc atteignable à 100 %
    # même quand une donnée réellement absente rend le goal non supporté.
    semantic_complete = len(goals) - without_operand_or_reason

    cascade = 0
    for capability_goal in capability.get("goals") or []:
        requirements = [
            requirement for requirement in (capability_goal.get("requirements") or [])
            if isinstance(requirement, dict)
        ]
        root_missing = any(
            requirement.get("state") == "unresolved"
            and requirement.get("reason_code") == "root_entity_missing"
            for requirement in requirements
        )
        if root_missing:
            cascade += sum(
                requirement.get("state") == "unresolved"
                and requirement.get("reason_code") != "root_entity_missing"
                for requirement in requirements
            )

    snapshot = resolved.get("catalog_snapshot") or {}
    known_names = _known_names(snapshot)
    false_unresolved = sum(
        _normalized_text(term.get("term")) in known_names
        for term in unresolved
        if _normalized_text(term.get("term"))
    )
    relations = [
        relation for relation in (snapshot.get("relations") or [])
        if isinstance(relation, dict)
    ]
    statuses = Counter(str(item.get("status")) for item in items if item.get("status"))
    status = (observation.get("statuses") or {}).get("llm")
    return {
        "goal_semantic_complete": semantic_complete,
        "resolved_semantic_ready_goals": resolved_semantic_ready,
        "goal_total": len(goals),
        "goal_without_operand_and_without_reason": without_operand_or_reason,
        "diagnostic_cascade_count": cascade,
        "known_refs_false_unresolved": false_unresolved,
        "goal_statuses": dict(sorted(statuses.items())),
        "compile_ready_goals": sum(item.get("compile_ready") is True for item in items),
        "required_unresolved": sum(
            (term.get("necessity") or "required") == "required" for term in unresolved
        ),
        "optional_unresolved": sum(term.get("necessity") == "optional" for term in unresolved),
        "relations_constraint_present": sum(
            relation.get("origin") == "constraint" and relation.get("executable") is True
            for relation in relations
        ),
        "relations_inferred_nonvalidated_ignored": sum(
            relation.get("origin") != "constraint"
            and relation.get("validation_status") == "unvalidated"
            and relation.get("executable") is False
            for relation in relations
        ),
        "aggregation_contradictions": _aggregation_contradictions(goals, items),
        "repairs": int(bool((observation.get("repair") or {}).get("applied"))),
        "contract_errors": int(status == "contract_error"),
        "provider_errors": int(status in {"network_error", "provider_error", "timeout"}),
    }


def summarize_observations(observations: list[dict]) -> dict:
    diagnostics = [observation_diagnostics(observation) for observation in observations]
    complete = sum(item["goal_semantic_complete"] for item in diagnostics)
    total = sum(item["goal_total"] for item in diagnostics)
    statuses = Counter()
    for diagnostic in diagnostics:
        statuses.update(diagnostic["goal_statuses"])
    constraint_relations: set[tuple] = set()
    ignored_relations: set[tuple] = set()
    for observation in observations:
        _interpretation, _capability, resolved = _artifacts(observation)
        snapshot = resolved.get("catalog_snapshot") or {}
        snapshot_key = snapshot.get("snapshot_id") or snapshot.get("fingerprint") or "unknown"
        for relation in snapshot.get("relations") or []:
            if not isinstance(relation, dict):
                continue
            key = (
                snapshot_key, relation.get("id"), relation.get("from_entity_ref"),
                relation.get("to_entity_ref"), relation.get("from_key"), relation.get("to_key"),
            )
            if relation.get("origin") == "constraint" and relation.get("executable") is True:
                constraint_relations.add(key)
            if (relation.get("origin") != "constraint"
                    and relation.get("validation_status") == "unvalidated"
                    and relation.get("executable") is False):
                ignored_relations.add(key)
    scalar_keys = (
        "goal_without_operand_and_without_reason", "diagnostic_cascade_count",
        "known_refs_false_unresolved", "compile_ready_goals", "required_unresolved",
        "resolved_semantic_ready_goals",
        "optional_unresolved", "relations_constraint_present",
        "relations_inferred_nonvalidated_ignored", "aggregation_contradictions",
        "repairs", "contract_errors", "provider_errors",
    )
    return {
        "goal_semantic_completeness": {
            "complete": complete,
            "total": total,
            "rate": (complete / total if total else 0.0),
        },
        "goal_statuses": dict(sorted(statuses.items())),
        **{key: sum(item[key] for item in diagnostics) for key in scalar_keys},
        "relations_constraint_present": len(constraint_relations),
        "relations_inferred_nonvalidated_ignored": len(ignored_relations),
    }
