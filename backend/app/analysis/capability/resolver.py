"""Phase 2 — C6 : résolution de capability et plan physique compile-ready.

Le resolved_plan v2 est autosuffisant : snapshot du catalogue, DAG, opérations,
mappings, arbre de jointure aliasé, filtres/tri/temps et protections de grain.
C7 n'aura ni catalogue vivant à consulter ni décision analytique à reprendre.
"""
from __future__ import annotations

from app.analysis.capability.grain import analyze_measure, overall_traversal, step_multiplies
from app.analysis.capability.joinpath import find_path
from app.analysis.capability.model import (
    ADD_FULL,
    CAUSE_ACCESS,
    CAUSE_CAPABILITY,
    CAUSE_QUALITY,
    ONE_TO_ONE,
    S_AVAILABLE,
    S_BLOCKED,
    S_NOT_EVALUATED,
    S_RESERVE,
    S_UNRESOLVED,
    CapabilityRequirement,
    CapabilityResolution,
    GoalResolution,
    ResolutionContext,
)
from app.analysis.capability.resolved_plan import (
    catalog_snapshot,
    entity_grain_keys,
    join_graph,
    physical_parts,
    select_join_tree,
    tree_path,
)
from app.analysis.contracts import (
    INTERPRETATION_SCHEMA_VERSION,
    RESOLVED_PLAN_SCHEMA_VERSION,
    validate_resolved,
)


_OPERATOR_BY_GOAL_TYPE = {
    "count": "count_distinct",
    "aggregate": "aggregate",
    "trend": "time_series_aggregate",
    "attribution": "attribution",
    "segmentation": "segmentation",
    "affinity": "affinity",
    "cohort": "cohort",
    "correlation": "correlation",
    "distribution": "distribution",
    "ranking": "ranking",
}
_METHOD_REQUIRED = frozenset({"attribution", "segmentation", "affinity", "cohort", "correlation"})
_MEASURE_REQUIRED = frozenset({"aggregate", "trend", "attribution", "correlation", "ranking"})
_TEMPORAL_REQUIRED = frozenset({"trend", "cohort"})


def _access_of(context: ResolutionContext, ref: str) -> tuple[str, str | None]:
    if not context.access.get("source_reachable", True):
        return "blocked", "source_unreachable"
    if ref in (context.access.get("hidden") or set()):
        return "blocked", "not_permitted"
    return "granted", None


def _quality_state(context: ResolutionContext, ref: str):
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
    req = CapabilityRequirement(kind=kind, ref=ref)
    if not present:
        req.capability_state = S_UNRESOLVED
        req.cause_class = CAUSE_CAPABILITY
        req.reason_code = f"{kind}_not_in_catalog"
        return req
    access, access_code = _access_of(context, ref)
    if access == "blocked":
        req.access_state = "blocked"
        req.cause_class = CAUSE_ACCESS
        req.reason_code = access_code
        return req
    state, cause, code, reserve = _quality_state(context, ref)
    if state == S_BLOCKED:
        req.capability_state, req.cause_class = S_BLOCKED, cause
        req.reason_code, req.reserve = code, reserve
    elif state == S_RESERVE:
        req.capability_state, req.cause_class = S_RESERVE, cause
        req.reason_code, req.reserve = code, reserve
    return req


def _missing_requirement(kind: str, ref: str, reason_code: str,
                         detail: str | None = None) -> CapabilityRequirement:
    return CapabilityRequirement(
        kind=kind, ref=ref, capability_state=S_UNRESOLVED,
        cause_class=CAUSE_CAPABILITY, reason_code=reason_code, reason_detail=detail)


def _not_evaluated(kind: str, ref: str, prerequisite: str) -> CapabilityRequirement:
    return CapabilityRequirement(
        kind=kind,
        ref=ref,
        capability_state=S_NOT_EVALUATED,
        reason_code=f"prerequisite_{prerequisite}",
        reason_detail=f"contrôle non évalué : prérequis {prerequisite}",
    )


def _physical_requirement(kind: str, ref: str, physical: str | None, *,
                          qualified: bool = False) -> CapabilityRequirement:
    valid = bool(physical) and (not qualified or physical_parts(physical)[0] is not None)
    if valid:
        return CapabilityRequirement(kind=kind, ref=ref)
    return _missing_requirement(kind, ref, "physical_mapping_missing")


def _goal_status(reqs: list[CapabilityRequirement], *, ambiguous: bool) -> str:
    if ambiguous:
        return "NEEDS_CLARIFICATION"
    if any(req.state in (S_BLOCKED, S_UNRESOLVED) for req in reqs):
        return "UNSUPPORTED"
    if any(req.state == S_RESERVE for req in reqs):
        return "PARTIAL"
    return "SUPPORTED"


def _goal_has_resolved_core(goal) -> bool:
    if goal.entity_ref:
        return True
    if any(isinstance(item, dict) and item.get("ref")
           for key in ("metrics", "dimensions") for item in (goal.raw.get(key) or [])):
        return True
    method = goal.raw.get("method")
    return isinstance(method, dict) and bool(method.get("name"))


def _unresolved_requirements(interp, goal) -> list[CapabilityRequirement]:
    requirements: list[CapabilityRequirement] = []
    has_core = _goal_has_resolved_core(goal)
    for index, term in enumerate(interp.unresolved_terms):
        if not isinstance(term, dict) or term.get("goal_id") != goal.id:
            continue
        declared = term["necessity"]
        optional = declared == "optional" and has_core
        role = str(term.get("role") or "unknown")
        if optional:
            requirements.append(CapabilityRequirement(
                kind="unresolved_term", ref=f"unresolved:{goal.id}:{index}",
                capability_state=S_RESERVE, cause_class=CAUSE_CAPABILITY,
                reason_code="optional_term_unresolved", reason_detail=term.get("reason"),
                reserve={"type": "optional_unresolved", "role": role},
                necessity="optional", unresolved_role=role))
        else:
            requirements.append(CapabilityRequirement(
                kind="unresolved_term", ref=f"unresolved:{goal.id}:{index}",
                capability_state=S_UNRESOLVED, cause_class=CAUSE_CAPABILITY,
                reason_code=("optional_term_without_resolved_core"
                             if declared == "optional" else "required_term_unresolved"),
                reason_detail=term.get("reason"), necessity="required", unresolved_role=role))
    return requirements


def _coverage_status(goal_statuses: list[str]) -> str:
    if not goal_statuses or all(status == "UNSUPPORTED" for status in goal_statuses):
        return "none"
    if any(status == "NEEDS_CLARIFICATION" for status in goal_statuses):
        return "needs_clarification"
    if all(status == "SUPPORTED" for status in goal_statuses):
        return "full"
    return "partial"


def _semantic_requirement(context: ResolutionContext, ref: str) -> CapabilityRequirement:
    if ref.startswith("concept:"):
        return _resolve_ref(context, "entity", ref, ref in context.entities)
    if ref.startswith("metric:"):
        return _resolve_ref(context, "measure", ref, ref in context.measures)
    return _resolve_ref(context, "dimension", ref, ref in context.dimensions)


def _home_entity(context: ResolutionContext, ref: str) -> str | None:
    if ref.startswith("concept:"):
        return ref if ref in context.entities else None
    if ref.startswith("metric:"):
        measure = context.measures.get(ref)
        return measure.home_entity if measure else None
    dimension = context.dimensions.get(ref)
    return dimension.home_entity if dimension else None


def _physical_of(context: ResolutionContext, ref: str) -> tuple[str | None, str]:
    if ref.startswith("metric:"):
        item = context.measures.get(ref)
        return (item.physical if item else None), ((item.data_type or "unknown") if item else "unknown")
    if ref.startswith("dimension:"):
        item = context.dimensions.get(ref)
        return (item.physical if item else None), ((item.data_type or "unknown") if item else "unknown")
    return None, "unknown"


def _resolved_temporal(goal, context: ResolutionContext, dimension_refs: list[str],
                       reqs: list[CapabilityRequirement]) -> dict | None:
    raw = goal.raw.get("temporal")
    if isinstance(raw, dict):
        return raw
    if goal.type not in _TEMPORAL_REQUIRED:
        return None
    reqs.append(_missing_requirement("temporal", goal.id, "exact_temporal_spec_missing"))
    return None


def _resolved_sort(goal, metric_refs: list[str], reqs: list[CapabilityRequirement]) -> list[dict]:
    raw = list(goal.raw.get("sort") or [])
    if raw:
        return raw
    if goal.type == "ranking":
        reqs.append(_missing_requirement("sort", goal.id, "ranking_sort_missing"))
    return []


def _select_root_entity(goal, context: ResolutionContext, metric_refs: list[str],
                        dimension_refs: list[str]) -> tuple[str | None, bool, list[str]]:
    """Choisit une racine depuis l'ensemble des opérandes, jamais leur ordre.

    Une racine métrique est préférée à une racine uniquement dimensionnelle. Si
    plusieurs candidates ont la même sûreté de traversée, le choix est ambigu.
    """
    if goal.entity_ref is not None:
        return goal.entity_ref, False, []

    metric_homes = {
        measure.home_entity for ref in metric_refs
        if (measure := context.measures.get(ref)) is not None and measure.home_entity
    }
    dimension_homes = {
        dimension.home_entity for ref in dimension_refs
        if (dimension := context.dimensions.get(ref)) is not None and dimension.home_entity
    }
    all_homes = metric_homes | dimension_homes
    candidates = metric_homes or dimension_homes
    if not candidates:
        return None, False, []
    if len(candidates) == 1:
        return next(iter(candidates)), False, []

    scored: list[tuple[tuple[int, int, int], str]] = []
    for candidate in sorted(candidates):
        paths = [find_path(context, candidate, target) for target in sorted(all_homes - {candidate})]
        if any(path.status == "none" for path in paths):
            continue
        if any(path.status == "ambiguous" for path in paths):
            continue
        steps = [step for path in paths for step in path.steps]
        score = (
            sum(step.cardinality == "many_to_many" for step in steps),
            sum(step_multiplies(step.cardinality) for step in steps),
            len(steps),
        )
        scored.append((score, candidate))
    if not scored:
        return None, True, sorted(candidates)
    scored.sort()
    best_score = scored[0][0]
    best = [candidate for score, candidate in scored if score == best_score]
    if len(best) != 1:
        return None, True, best
    return best[0], False, []


def _readiness(goal, reqs: list[CapabilityRequirement], graph: dict, *, ambiguous: bool) -> dict:
    required_unresolved = any(
        req.kind == "unresolved_term" and req.necessity == "required"
        for req in reqs
    )
    semantic_kinds = {
        "entity", "measure", "dimension", "operation", "method", "temporal",
        "root_entity", "measure_home", "unresolved_term",
    }
    semantic_complete = not ambiguous and not required_unresolved and not any(
        req.kind in semantic_kinds and req.state in (S_UNRESOLVED, S_BLOCKED)
        for req in reqs
    )
    internally_consistent = not ambiguous and not any(
        req.kind == "consistency" and req.state in (S_UNRESOLVED, S_BLOCKED)
        for req in reqs
    )
    physical_kinds = {
        "root_entity", "relation", "physical_entity", "physical_column",
        "physical_join", "pre_aggregation_key", "count_key",
    }
    physically_resolved = bool(graph.get("root_entity_ref") and graph.get("nodes")) and not any(
        req.kind in physical_kinds and req.state in (S_UNRESOLVED, S_BLOCKED, S_NOT_EVALUATED)
        for req in reqs
    )
    analytically_safe = not any(
        req.kind in {"grain", "fanout", "pre_aggregation_key", "count_key"}
        and req.state in (S_UNRESOLVED, S_BLOCKED, S_RESERVE, S_NOT_EVALUATED)
        for req in reqs
    )
    return {
        "semantic_complete": semantic_complete,
        "internally_consistent": internally_consistent,
        "physically_resolved": physically_resolved,
        "analytically_safe": analytically_safe,
    }


def _dedupe_semantic_requirements(context: ResolutionContext, refs: list[str]) -> list[CapabilityRequirement]:
    return [_semantic_requirement(context, ref) for ref in dict.fromkeys(refs)]


def _add_physical_requirements(context: ResolutionContext, reqs: list[CapabilityRequirement],
                               entity_refs: set[str], column_refs: set[str]) -> None:
    for ref in sorted(entity_refs):
        entity = context.entities.get(ref)
        reqs.append(_physical_requirement("physical_entity", ref, entity.physical if entity else None))
    for ref in sorted(column_refs):
        physical, _ = _physical_of(context, ref)
        reqs.append(_physical_requirement("physical_column", ref, physical, qualified=True))


def resolve(interp, context: ResolutionContext):
    """Produit C6 + resolved_plan v2, puis applique le contrat éliminatoire."""
    resolution = CapabilityResolution()
    plan_items: list[dict] = []

    for goal in interp.goals:
        reqs: list[CapabilityRequirement] = []
        metric_specs = [item for item in (goal.raw.get("metrics") or [])
                        if isinstance(item, dict) and item.get("ref")]
        metric_refs = [item["ref"] for item in metric_specs]
        dimension_refs = [item["ref"] for item in (goal.raw.get("dimensions") or [])
                          if isinstance(item, dict) and item.get("ref")]
        filter_specs = list(goal.raw.get("filters") or [])
        filter_refs = [item["ref"] for item in filter_specs if isinstance(item, dict) and item.get("ref")]
        sort_specs = _resolved_sort(goal, metric_refs, reqs)
        sort_refs = [item["ref"] for item in sort_specs if isinstance(item, dict) and item.get("ref")]
        temporal_spec = _resolved_temporal(goal, context, dimension_refs, reqs)
        temporal_ref = temporal_spec.get("dimension_ref") if temporal_spec else None

        semantic_refs = ([goal.entity_ref] if goal.entity_ref else []) + metric_refs + dimension_refs
        semantic_refs += filter_refs + sort_refs + ([temporal_ref] if temporal_ref else [])
        reqs.extend(_dedupe_semantic_requirements(context, semantic_refs))
        reqs.extend(_unresolved_requirements(interp, goal))

        if temporal_ref:
            temporal_dimension = context.dimensions.get(temporal_ref)
            if temporal_dimension is not None and not temporal_dimension.is_temporal:
                reqs.append(_missing_requirement(
                    "temporal", temporal_ref, "temporal_dimension_type_unsupported"))

        if goal.type in _MEASURE_REQUIRED and not metric_specs:
            reqs.append(_missing_requirement("operation", goal.id, "operation_measure_missing"))
        if goal.type == "correlation" and len(metric_specs) < 2:
            reqs.append(_missing_requirement("operation", goal.id, "correlation_requires_two_measures"))
        if goal.type == "distribution" and not dimension_refs:
            reqs.append(_missing_requirement("operation", goal.id, "distribution_dimension_missing"))
        if goal.type in _METHOD_REQUIRED and not (goal.raw.get("method") or {}).get("name"):
            reqs.append(_missing_requirement("method", goal.id, "exact_method_missing"))

        root_entity, root_ambiguous, root_alternatives = _select_root_entity(
            goal, context, metric_refs, dimension_refs,
        )
        c4_ambiguous = bool(goal.raw.get("ambiguities"))
        ambiguous = c4_ambiguous or root_ambiguous
        if root_ambiguous:
            reqs.append(_missing_requirement(
                "root_entity", goal.id, "ambiguous_root_entity",
                f"racines également plausibles : {root_alternatives}",
            ))
        elif root_entity is None:
            reqs.append(_missing_requirement("root_entity", goal.id, "root_entity_missing"))

        if root_entity is None:
            prerequisite = "ambiguous_root_entity" if root_ambiguous else "root_entity_missing"
            reqs.append(_not_evaluated("join_path", goal.id, prerequisite))
            if goal.type == "count":
                reqs.append(_not_evaluated("count_key", goal.id, prerequisite))
            reqs.append(_not_evaluated("fanout", goal.id, prerequisite))
            tree = select_join_tree(context, None, set())
            graph = join_graph(context, tree)
            readiness = _readiness(goal, reqs, graph, ambiguous=ambiguous)
            status = _goal_status(reqs, ambiguous=ambiguous)
            resolution.goals.append(GoalResolution(
                goal_id=goal.id, status=status, requirements=reqs,
            ))
            plan_items.append(_plan_item(
                goal, status, reqs, context, graph, [], metric_specs, dimension_refs,
                filter_specs, sort_specs, temporal_spec, readiness,
            ))
            continue

        target_entities = {home for ref in metric_refs + dimension_refs + filter_refs + sort_refs
                           if (home := _home_entity(context, ref))}
        if temporal_ref and (home := _home_entity(context, temporal_ref)):
            target_entities.add(home)
        if root_entity:
            target_entities.add(root_entity)

        tree = select_join_tree(context, root_entity, target_entities)
        ambiguous = ambiguous or tree.status == "ambiguous"
        if tree.status == "none":
            reqs.append(_missing_requirement(
                "relation", f"{root_entity}->{tree.missing_target}", "no_validated_relation"))
        elif tree.status == "ambiguous":
            reqs.append(CapabilityRequirement(
                kind="relation", ref=f"{root_entity}->{tree.ambiguous_target}",
                capability_state=S_UNRESOLVED, cause_class=CAUSE_CAPABILITY,
                reason_code="ambiguous_join_path", reserve={"alternatives": tree.alternatives}))

        graph = join_graph(context, tree)
        graph_entities = {node["entity_ref"] for node in graph["nodes"]}
        _add_physical_requirements(
            context, reqs, graph_entities,
            set(metric_refs + dimension_refs + filter_refs + sort_refs + ([temporal_ref] if temporal_ref else [])))
        for edge in graph["edges"]:
            reqs.append(_physical_requirement(
                "physical_join", f"relation:{edge['validated_relation_id']}:left", edge.get("left_key"),
                qualified=True))
            reqs.append(_physical_requirement(
                "physical_join", f"relation:{edge['validated_relation_id']}:right", edge.get("right_key"),
                qualified=True))

        aggregation_dimensions = set(dimension_refs)
        analyses: list[dict] = []
        for index, metric_spec in enumerate(metric_specs):
            ref = metric_spec["ref"]
            measure = context.measures.get(ref)
            source = measure.home_entity if measure else None
            if measure is not None and not source:
                reqs.append(_missing_requirement("measure_home", ref, "measure_home_entity_missing"))
            path_source = source or root_entity
            paths = [tree_path(context, tree, path_source, _home_entity(context, dim_ref))
                     for dim_ref in sorted(aggregation_dimensions)
                     if path_source and _home_entity(context, dim_ref)]
            unique_steps = {step.relation_id: step for path in paths for step in path}
            cardinalities = [unique_steps[key].cardinality for key in sorted(unique_steps)]
            grain = analyze_measure(
                measure, cardinalities, agg_dims=frozenset(aggregation_dimensions), is_count=False)
            reqs.append(CapabilityRequirement(
                kind="grain", ref=ref, capability_state=grain.state, strategy=grain.strategy,
                reason_code=grain.reason_code, reason_detail=grain.reason_detail,
                reserve=grain.reserve, creates_row_multiplication=grain.creates_row_multiplication,
                cause_class=(CAUSE_CAPABILITY if grain.state != S_AVAILABLE else None)))
            if grain.requires_pre_aggregation:
                keys = entity_grain_keys(context, source)
                if not keys or any(not key.get("physical") for key in keys):
                    reqs.append(_missing_requirement(
                        "pre_aggregation_key", ref, "pre_aggregation_key_missing"))
            analyses.append({
                "index": index, "ref": ref, "measure": measure, "source": source or path_source,
                "aggregation": metric_spec["aggregation"], "grain": grain,
                "relation_ids": sorted(unique_steps), "cardinalities": cardinalities,
            })

        if not metric_specs:
            paths = [tree_path(context, tree, root_entity, _home_entity(context, dim_ref))
                     for dim_ref in sorted(aggregation_dimensions)
                     if root_entity and _home_entity(context, dim_ref)]
            unique_steps = {step.relation_id: step for path in paths for step in path}
            cardinalities = [unique_steps[key].cardinality for key in sorted(unique_steps)]
            is_count_operation = goal.type in {"count", "distribution"}
            grain = analyze_measure(
                None, cardinalities, agg_dims=frozenset(aggregation_dimensions),
                is_count=is_count_operation,
            )
            reqs.append(CapabilityRequirement(
                kind="grain", ref=root_entity or "grain", capability_state=grain.state,
                strategy=grain.strategy, reason_code=grain.reason_code,
                creates_row_multiplication=grain.creates_row_multiplication,
                cause_class=(CAUSE_CAPABILITY if grain.state != S_AVAILABLE else None)))
            if goal.type == "count":
                keys = entity_grain_keys(context, root_entity)
                if not keys or any(not key.get("physical") for key in keys):
                    reqs.append(_missing_requirement("count_key", goal.id, "count_distinct_key_missing"))
            analyses.append({
                "index": 0, "ref": root_entity or "count", "measure": None,
                "source": root_entity,
                "aggregation": "count_distinct" if is_count_operation else "none",
                "grain": grain,
                "relation_ids": sorted(unique_steps), "cardinalities": cardinalities,
            })

        readiness = _readiness(goal, reqs, graph, ambiguous=ambiguous)
        status = _goal_status(reqs, ambiguous=ambiguous)
        if status == "SUPPORTED" and not all(readiness.values()):
            reqs.append(_missing_requirement(
                "compile_readiness", goal.id, "compile_readiness_incomplete",
            ))
            status = "UNSUPPORTED"
        resolution.goals.append(GoalResolution(goal_id=goal.id, status=status, requirements=reqs))
        plan_items.append(_plan_item(
            goal, status, reqs, context, graph, analyses, metric_specs, dimension_refs,
            filter_specs, sort_specs, temporal_spec, readiness))

    goal_statuses = [item["status"] for item in plan_items]
    coverage_status = _coverage_status(goal_statuses)
    unresolved_reqs = [req for resolved_goal in resolution.goals for req in resolved_goal.requirements
                       if req.kind == "unresolved_term"]
    resolved = {
        "resolved_plan_schema_version": RESOLVED_PLAN_SCHEMA_VERSION,
        "source_interpretation_schema_version": INTERPRETATION_SCHEMA_VERSION,
        "catalog_snapshot": catalog_snapshot(context),
        "dag": _dag(interp),
        "coherence": {
            "covers_question": coverage_status == "full",
            "coverage_status": coverage_status,
            "computed_by": "noreon",
            "required_unresolved_count": sum(req.necessity == "required" for req in unresolved_reqs),
            "optional_unresolved_count": sum(req.necessity == "optional" for req in unresolved_reqs),
        },
        "resolution": plan_items,
    }
    validate_resolved(resolved)
    return resolution, resolved


def _dag(interp) -> dict:
    return {
        "nodes": [{"goal_id": goal.id, "priority": goal.priority,
                   "depends_on": list(goal.depends_on)} for goal in interp.goals],
        "edges": [{"from_goal_id": dependency, "to_goal_id": goal.id}
                  for goal in interp.goals for dependency in goal.depends_on],
        "topological_order": interp.topological_order(),
    }


def _compile_blockers(reqs: list[CapabilityRequirement]) -> list[str]:
    return sorted({f"{req.kind}:{req.reason_code or req.state}"
                   for req in reqs if req.state in (S_UNRESOLVED, S_BLOCKED)})


def _plan_item(goal, status, reqs, context, graph, analyses, metric_specs,
               dimension_refs, filter_specs, sort_specs, temporal_spec,
               readiness: dict) -> dict:
    concepts = ([goal.entity_ref] if goal.entity_ref else [])
    concepts += [item["ref"] for item in metric_specs]
    concepts += dimension_refs
    concepts = list(dict.fromkeys(concepts))
    coverage = _goal_coverage(reqs, status)
    base = {
        "goal_id": goal.id,
        "status": status,
        "compile_ready": all(readiness.values()),
        "readiness": readiness,
        "compile_blockers": _compile_blockers(reqs),
        "depends_on": list(goal.depends_on),
        "concepts": concepts,
        "coverage": coverage,
    }
    if status == "NEEDS_CLARIFICATION":
        return {**base, "compile_ready": False,
                "clarification": "décision analytique ambiguë — préciser l'opérande ou la relation"}
    if status == "UNSUPPORTED":
        blocker = base["compile_blockers"][0] if base["compile_blockers"] else "non_resolved"
        return {**base, "compile_ready": False, "unsupported_reason": blocker}

    aliases = {node["entity_ref"]: node["alias"] for node in graph["nodes"]}
    metrics = [_measure_mapping(context, item, aliases) for item in analyses if item["measure"] is not None]
    dimensions = [_column_mapping(context, ref, aliases) for ref in dimension_refs]
    count_keys = (entity_grain_keys(context, graph["root_entity_ref"])
                  if goal.type == "count" else [])
    pre_aggregations = [_pre_aggregation(context, item, graph, aliases)
                        for item in analyses if item["grain"].requires_pre_aggregation
                        and item["measure"] is not None]
    grain = _grain_json(context, goal.entity_ref, graph["root_entity_ref"], analyses)
    method = goal.raw.get("method")
    item = {
        **base,
        "operation": {
            "kind": goal.type,
            "operator": _OPERATOR_BY_GOAL_TYPE[goal.type],
            "metrics": metrics,
            "count_distinct_keys": count_keys,
            "parameters": {
                "binning_requested": goal.raw["binning_requested"],
                "ranked_axis_refs": (
                    ([goal.entity_ref] if goal.entity_ref else []) + dimension_refs
                    if goal.type == "ranking" else []
                ),
            },
        },
        "physical": {
            "root_entity_ref": graph["root_entity_ref"],
            "root_table": next(node["physical_table"] for node in graph["nodes"]
                               if node["entity_ref"] == graph["root_entity_ref"]),
            "root_alias": graph["root_alias"],
            "entities": graph["nodes"],
            "measures": metrics,
            "dimensions": dimensions,
        },
        "join_graph": graph,
        "filters": [_filter_mapping(context, spec, aliases) for spec in filter_specs],
        "sort": [_sort_mapping(context, spec, aliases) for spec in sort_specs],
        "limit": goal.raw.get("limit"),
        "temporal": _temporal_mapping(context, temporal_spec, aliases),
        "grain": grain,
        "pre_aggregations": pre_aggregations,
    }
    if isinstance(method, dict) and method.get("name"):
        item["method"] = {
            "name": method["name"], "version": method["version"],
            "params": method["params"],
        }
    return item


def _measure_mapping(context: ResolutionContext, analysis: dict, aliases: dict[str, str]) -> dict:
    measure = analysis["measure"]
    table, column = physical_parts(measure.physical)
    return {
        "ref": measure.ref,
        "source_entity_ref": measure.home_entity,
        "source_alias": aliases.get(measure.home_entity),
        "physical": measure.physical,
        "table": table,
        "column": column,
        "data_type": measure.data_type or "unknown",
        "aggregation": analysis["aggregation"],
        "output_alias": f"m{analysis['index']}",
    }


def _column_mapping(context: ResolutionContext, ref: str, aliases: dict[str, str]) -> dict:
    physical, data_type = _physical_of(context, ref)
    table, column = physical_parts(physical)
    return {
        "ref": ref, "home_entity_ref": _home_entity(context, ref),
        "source_alias": aliases.get(_home_entity(context, ref) or ""),
        "physical": physical, "table": table, "column": column, "data_type": data_type,
    }


def _filter_mapping(context: ResolutionContext, spec: dict, aliases: dict[str, str]) -> dict:
    return {
        **_column_mapping(context, spec["ref"], aliases),
        "operator": spec["operator"], "value_type": spec["value_type"],
        "value": spec["value"], "conjunction": spec["conjunction"],
    }


def _sort_mapping(context: ResolutionContext, spec: dict, aliases: dict[str, str]) -> dict:
    return {
        **_column_mapping(context, spec["ref"], aliases),
        "direction": spec["direction"], "nulls": spec["nulls"],
    }


def _temporal_mapping(context: ResolutionContext, spec: dict | None,
                      aliases: dict[str, str]) -> dict:
    if not spec:
        return {"enabled": False, "dimension_ref": None, "source_alias": None,
                "physical": None, "data_type": None, "grain": None, "timezone": None}
    mapping = _column_mapping(context, spec["dimension_ref"], aliases)
    return {
        "enabled": True,
        "dimension_ref": spec["dimension_ref"],
        "source_alias": mapping["source_alias"],
        "physical": mapping["physical"],
        "data_type": mapping["data_type"],
        "grain": spec["grain"],
        "timezone": spec["timezone"],
    }


def _grain_json(context: ResolutionContext, entity_ref: str | None, root_entity: str | None,
                analyses: list[dict]) -> dict:
    strategies = {item["grain"].strategy for item in analyses}
    cards = [cardinality for item in analyses for cardinality in item["cardinalities"]]
    additivities = {item["measure"].additivity if item["measure"] else ADD_FULL for item in analyses}
    measure_grains = [
        {
            "ref": item["ref"],
            "source_entity_ref": item["source"],
            "source_grain_keys": entity_grain_keys(context, item["source"]),
            "aggregation": item["aggregation"],
            "traversal": overall_traversal(item["cardinalities"]) if item["cardinalities"] else ONE_TO_ONE,
            "creates_row_multiplication": item["grain"].creates_row_multiplication,
            "requires_pre_aggregation": item["grain"].requires_pre_aggregation,
            "aggregation_strategy": item["grain"].strategy,
            "relation_ids": item["relation_ids"],
        }
        for item in analyses
    ]
    return {
        "base_grain": _grain_label(context, entity_ref),
        "source_grain": _grain_label(context, root_entity),
        "metric_grain": (measure_grains[0]["source_entity_ref"] if len(measure_grains) == 1 else "per_measure"),
        "input_grain": root_entity or "row",
        "traversal": overall_traversal(cards) if cards else ONE_TO_ONE,
        "metric_additivity": next(iter(additivities)) if len(additivities) == 1 else "mixed",
        "creates_row_multiplication": any(item["grain"].creates_row_multiplication for item in analyses),
        "requires_pre_aggregation": any(item["grain"].requires_pre_aggregation for item in analyses),
        "aggregation_strategy": next(iter(strategies)) if len(strategies) == 1 else "per_measure",
        "measure_grains": measure_grains,
    }


def _grain_label(context: ResolutionContext, entity_ref: str | None) -> str:
    keys = entity_grain_keys(context, entity_ref)
    values = [key["physical"] for key in keys if key.get("physical")]
    return ",".join(values) if values else (entity_ref or "row")


def _pre_aggregation(context: ResolutionContext, analysis: dict, graph: dict,
                     aliases: dict[str, str]) -> dict:
    source = analysis["source"]
    source_alias = aliases.get(source)
    group_keys = [key["physical"] for key in entity_grain_keys(context, source) if key.get("physical")]
    incident = []
    for edge in graph["edges"]:
        if edge["left_entity_ref"] == source:
            source_key, target_alias, target_key = edge["left_key"], edge["right_alias"], edge["right_key"]
        elif edge["right_entity_ref"] == source:
            source_key, target_alias, target_key = edge["right_key"], edge["left_alias"], edge["left_key"]
        else:
            continue
        if source_key not in group_keys:
            group_keys.append(source_key)
        incident.append({
            "source_key": source_key,
            "target_alias": target_alias,
            "target_key": target_key,
            "validated_relation_id": edge["validated_relation_id"],
        })
    key_aliases = {key: f"k{index}" for index, key in enumerate(group_keys)}
    join_back = [{**edge, "output_key_alias": key_aliases[edge["source_key"]]} for edge in incident]
    return {
        "required": True,
        "strategy": analysis["grain"].strategy,
        "source_entity_ref": source,
        "input_alias": source_alias,
        "output_alias": f"pa{analysis['index']}",
        "group_by": [{"physical": key, "output_alias": alias}
                     for key, alias in key_aliases.items()],
        "aggregations": [{
            "measure_ref": analysis["ref"],
            "input_physical": analysis["measure"].physical,
            "function": analysis["aggregation"],
            "output_alias": f"m{analysis['index']}",
        }],
        "join_back": join_back,
        "fanout_path_relation_ids": analysis["relation_ids"],
    }


def _goal_coverage(reqs: list[CapabilityRequirement], status: str) -> dict:
    def refs(necessity: str) -> list[dict]:
        return [{"role": req.unresolved_role or "unknown",
                 "reason_code": req.reason_code or "unresolved"}
                for req in reqs
                if req.kind == "unresolved_term" and req.necessity == necessity]

    if status == "NEEDS_CLARIFICATION":
        coverage_status = "needs_clarification"
    elif status == "SUPPORTED":
        coverage_status = "full"
    elif status == "PARTIAL":
        coverage_status = "partial"
    else:
        coverage_status = "none"
    return {
        "status": coverage_status,
        "required_unresolved": refs("required"),
        "optional_unresolved": refs("optional"),
    }
