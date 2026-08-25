"""Phase 2 — C6 : orchestration du CapabilityResolver.

Produit DEUX artefacts couplés : un `CapabilityResolution` riche (états/causes/
réserves, pour narration/coverage/shadow) et le `resolved_plan_json` (contrat C1,
validé par `validate_resolved`, consommé par le PlanCompiler).

Ordre : capability sémantique → accès (orthogonal) → qualité → join path
(safety-first) → grain/fanout → roll-up. Rien n'est jamais inventé.
"""
from __future__ import annotations

from app.analysis.capability.grain import analyze_measure, overall_traversal
from app.analysis.capability.joinpath import find_path
from app.analysis.capability.model import (
    ADD_FULL,
    CAUSE_ACCESS,
    CAUSE_CAPABILITY,
    CAUSE_QUALITY,
    ONE_TO_ONE,
    S_AVAILABLE,
    S_BLOCKED,
    S_RESERVE,
    S_UNRESOLVED,
    STRAT_NONE,
    CapabilityRequirement,
    CapabilityResolution,
    GoalResolution,
    ResolutionContext,
)
from app.analysis.contracts import PLAN_SCHEMA_VERSION, validate_resolved


def _access_of(context: ResolutionContext, ref: str) -> tuple[str, str | None]:
    """(access_state, reason_code). Axe ACCÈS, orthogonal à la capability (#5)."""
    if not context.access.get("source_reachable", True):
        return "blocked", "source_unreachable"
    if ref in (context.access.get("hidden") or set()):
        return "blocked", "not_permitted"
    return "granted", None


def _quality_state(context: ResolutionContext, ref: str):
    """(capability_state, cause, code, reserve). Qualité : hard-stop = blocked(quality)
    (#7), stale-in-tolérance = reserve, jamais unresolved (qui = manque de structure)."""
    score = (context.quality or {}).get(ref)
    stale = bool((context.freshness or {}).get(ref, {}).get("stale"))
    if score is not None and score < context.policy.quality_hard_stop:
        return S_BLOCKED, CAUSE_QUALITY, "quality_hard_stop", {"type": "quality", "score": score}
    if stale:
        if context.policy.staleness_mode == "strict":
            return S_BLOCKED, CAUSE_QUALITY, "stale_hard_stop", {"type": "stale"}
        return S_RESERVE, CAUSE_QUALITY, "stale_within_tolerance", {"type": "stale"}
    return S_AVAILABLE, None, None, None


def _resolve_ref(context: ResolutionContext, kind: str, ref: str, present: bool) -> CapabilityRequirement:
    """Résout un ref atomique : présence (capability) → accès → qualité."""
    req = CapabilityRequirement(kind=kind, ref=ref)
    if not present:                                   # jamais inventé
        req.capability_state = S_UNRESOLVED
        req.cause_class = CAUSE_CAPABILITY
        req.reason_code = f"{kind}_not_in_catalog"
        return req
    acc, acc_code = _access_of(context, ref)
    if acc == "blocked":
        req.access_state = "blocked"
        req.cause_class = CAUSE_ACCESS
        req.reason_code = acc_code
        return req
    qstate, qcause, qcode, qreserve = _quality_state(context, ref)
    if qstate == S_BLOCKED:
        req.capability_state, req.cause_class, req.reason_code, req.reserve = S_BLOCKED, qcause, qcode, qreserve
    elif qstate == S_RESERVE:
        req.capability_state, req.cause_class, req.reason_code, req.reserve = S_RESERVE, qcause, qcode, qreserve
    return req


_STATUS_RANK = {S_AVAILABLE: 0, S_RESERVE: 1, S_UNRESOLVED: 2, S_BLOCKED: 2}


def _goal_status(reqs: list[CapabilityRequirement], *, ambiguous: bool) -> str:
    if ambiguous:
        return "NEEDS_CLARIFICATION"
    if any(r.state == S_BLOCKED for r in reqs) or any(r.state == S_UNRESOLVED for r in reqs):
        return "UNSUPPORTED"
    if any(r.state == S_RESERVE for r in reqs):
        return "PARTIAL"
    return "SUPPORTED"


def resolve(interp, context: ResolutionContext):
    """Renvoie (CapabilityResolution, resolved_plan_json). Le second passe
    `validate_resolved`."""
    resolution = CapabilityResolution()
    plan_items = []

    for g in interp.goals:
        reqs: list[CapabilityRequirement] = []
        entity_ref = g.entity_ref
        metric_refs = [m["ref"] for m in (g.raw.get("metrics") or []) if isinstance(m, dict) and m.get("ref")]
        dim_refs = [d["ref"] for d in (g.raw.get("dimensions") or []) if isinstance(d, dict) and d.get("ref")]

        # 1-3. Capability + accès + qualité par ref.
        if entity_ref is not None:
            reqs.append(_resolve_ref(context, "entity", entity_ref, entity_ref in context.entities))
        for mref in metric_refs:
            reqs.append(_resolve_ref(context, "measure", mref, mref in context.measures))
        for dref in dim_refs:
            reqs.append(_resolve_ref(context, "dimension", dref, dref in context.dimensions))

        # 4. Join path (safety-first) source = home de la mesure, sinon l'entité du goal.
        measure0 = context.measures.get(metric_refs[0]) if metric_refs else None
        source_entity = (measure0.home_entity if measure0 else entity_ref) or entity_ref
        steps, cardinalities, ambiguous = [], [], False
        blocking_missing = any(r.state in (S_UNRESOLVED, S_BLOCKED) for r in reqs)
        for dref in dim_refs:
            dim = context.dimensions.get(dref)
            if dim is None or source_entity is None:
                continue
            if dim.home_entity == source_entity:
                continue
            pr = find_path(context, source_entity, dim.home_entity)
            rreq = CapabilityRequirement(kind="relation", ref=f"{source_entity}->{dim.home_entity}")
            if pr.status == "none":
                rreq.capability_state, rreq.cause_class, rreq.reason_code = S_UNRESOLVED, CAUSE_CAPABILITY, "no_validated_relation"
                reqs.append(rreq); blocking_missing = True
            elif pr.status == "ambiguous":
                ambiguous = True
                rreq.capability_state, rreq.cause_class, rreq.reason_code = S_UNRESOLVED, CAUSE_CAPABILITY, "ambiguous_join_path"
                rreq.reserve = {"alternatives": pr.alternatives}
                reqs.append(rreq)
            else:
                reqs.append(rreq)
                steps.extend(pr.steps)
                cardinalities.extend(s.cardinality for s in pr.steps)

        # 5. Grain / fanout (le cœur anti-double-comptage).
        is_count = (g.type == "count") or not metric_refs
        grain = analyze_measure(measure0, cardinalities, agg_dims=frozenset(dim_refs), is_count=is_count)
        greq = CapabilityRequirement(kind="grain", ref=(measure0.ref if measure0 else (entity_ref or "grain")),
                                     capability_state=grain.state, strategy=grain.strategy,
                                     reason_code=grain.reason_code, reason_detail=grain.reason_detail,
                                     reserve=grain.reserve, creates_row_multiplication=grain.creates_row_multiplication,
                                     cause_class=(CAUSE_CAPABILITY if grain.state != S_AVAILABLE else None))
        reqs.append(greq)

        # 6. Roll-up + item resolved_plan.
        status = _goal_status(reqs, ambiguous=ambiguous)
        resolution.goals.append(GoalResolution(goal_id=g.id, status=status, requirements=reqs))
        plan_items.append(_plan_item(g, status, reqs, steps, cardinalities, grain,
                                     entity_ref, source_entity, measure0, context, ambiguous))

    covers = all(it["status"] in ("SUPPORTED", "PARTIAL") for it in plan_items) and bool(plan_items)
    resolved = {
        "plan_schema_version": PLAN_SCHEMA_VERSION,
        "coherence": {"covers_question": covers, "computed_by": "noreon"},
        "resolution": plan_items,
    }
    validate_resolved(resolved)                    # garantit le contrat (fanout_without_pre_aggregation impossible)
    return resolution, resolved


def _grain_str(entity_ref: str | None, context: ResolutionContext) -> str:
    ent = context.entities.get(entity_ref or "")
    if ent and ent.grain_keys:
        return ",".join(ent.grain_keys)
    return entity_ref or "row"


def _join_step_json(step, path_prefix="") -> dict:
    frm = step.from_key or f"{step.from_entity}._key"
    to = step.to_key or f"{step.to_entity}._key"
    return {"from": frm, "to": to, "cardinality": step.cardinality,
            "validated_relation_id": int(step.relation_id),
            "fanout_risk": step.cardinality in ("one_to_many", "many_to_many")}


def _plan_item(g, status, reqs, steps, cardinalities, grain, entity_ref, source_entity,
               measure0, context, ambiguous) -> dict:
    concepts = [entity_ref] if entity_ref else []
    concepts += [m["ref"] for m in (g.raw.get("metrics") or []) if isinstance(m, dict) and m.get("ref")]
    concepts += [d["ref"] for d in (g.raw.get("dimensions") or []) if isinstance(d, dict) and d.get("ref")]

    if status == "NEEDS_CLARIFICATION":
        return {"goal_id": g.id, "status": status, "concepts": concepts,
                "clarification": "chemin de jointure ambigu — préciser la relation à utiliser"}
    if status == "UNSUPPORTED":
        bad = next((r for r in reqs if r.state in (S_UNRESOLVED, S_BLOCKED)), None)
        reason = f"{bad.kind}:{bad.reason_code}" if bad else "non résolu"
        return {"goal_id": g.id, "status": status, "concepts": concepts, "unsupported_reason": reason}

    metric_grain = source_entity or entity_ref or "row"
    input_grain = (steps[-1].to_entity if steps else metric_grain)
    grain_json = {
        "base_grain": _grain_str(entity_ref, context),
        "source_grain": _grain_str(source_entity, context),
        "metric_grain": _grain_str(metric_grain, context),
        "input_grain": _grain_str(input_grain, context),
        "traversal": overall_traversal(cardinalities) if cardinalities else ONE_TO_ONE,
        "metric_additivity": (measure0.additivity if measure0 else ADD_FULL),
        "creates_row_multiplication": grain.creates_row_multiplication,
        "requires_pre_aggregation": grain.requires_pre_aggregation,
        "aggregation_strategy": grain.strategy,
    }
    item = {
        "goal_id": g.id, "status": status, "concepts": concepts,
        "physical": {"source_entity": source_entity, "strategy": grain.strategy},
        "join_path": [_join_step_json(s) for s in steps],
        "grain": grain_json,
    }
    method = g.raw.get("method")
    if isinstance(method, dict) and method.get("name"):
        item["method"] = {"name": method["name"], "version": str(method.get("version") or "1.0"),
                          "params": method.get("params") or {}}
    return item
