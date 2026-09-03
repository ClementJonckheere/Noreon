"""Phase 2 — C1 : contrat JSON strict du planificateur analytique.

Deux documents distincts, audités séparément :

- `interpretation_json` : SORTIE DU LLM. Il ne choisit que des références
  sémantiques (`concept:*`, `metric:*`, `dimension:*`) et déclare des
  dépendances entre objectifs (`depends_on`). Il ne connaît AUCUN nom physique,
  AUCUN chemin de jointure, AUCUNE cardinalité, AUCUN fanout : ces champs y sont
  INTERDITS et rejetés.
- `resolved_plan_json` : PRODUIT PAR NOREON. Le physique, le `join_graph` canonique
  (avec id de relation validée, alias et fanout par arête), le grain et le descripteur
  de multiplication de lignes, la méthode figée, et `coherence.covers_question`
  (calculé par Noreon, jamais par le LLM) n'existent QUE là.

Toute violation lève `ContractError(code=...)` — les codes sont testés.
"""
from __future__ import annotations

import logging
import hashlib
import json
import re
from dataclasses import dataclass, field

# Versions VERSIONNÉES SÉPARÉMENT (C4) :
# - INTERPRETATION_SCHEMA_VERSION : structure du document `interpretation_json`
#   (champs, imbrications, invariants). Portée sur le fil via `plan_schema_version`.
# - GOAL_TYPES_VERSION : vocabulaire fermé des types d'objectifs + leur glossaire
#   (prompt). Peut évoluer indépendamment de la structure.
# Bumper l'une n'oblige pas à bumper l'autre. Toute sortie déclarant une version
# de structure non supportée est REJETÉE (pas de réparation silencieuse).
INTERPRETATION_SCHEMA_VERSION = "1.3"
GOAL_TYPES_VERSION = "1.0"
RESOLVED_PLAN_SCHEMA_VERSION = "2.1"
CATALOG_SNAPSHOT_SCHEMA_VERSION = "1.2"
# Alias de compatibilité interne. Contrairement à l'historique, il désigne
# désormais le contrat résolu, versionné indépendamment de l'interprétation.
PLAN_SCHEMA_VERSION = RESOLVED_PLAN_SCHEMA_VERSION

logger = logging.getLogger("noreon.planner.contract")

# --- Vocabulaires fermés -----------------------------------------------------
GOAL_TYPES = frozenset({
    "count", "aggregate", "trend", "attribution", "segmentation",
    "affinity", "cohort", "correlation", "distribution", "ranking",
})
CARDINALITIES = frozenset({"many_to_one", "one_to_many", "one_to_one", "many_to_many"})
RESOLUTION_STATUS = frozenset({"SUPPORTED", "PARTIAL", "UNSUPPORTED", "NEEDS_CLARIFICATION"})
RUN_STATUS = frozenset({"pending", "running", "succeeded", "failed", "cancelled", "timed_out"})
COVERAGE_STATUS = frozenset({"full", "partial", "none", "needs_clarification"})
GOAL_RESULT_STATUS = frozenset({
    "answered", "partial", "impossible", "blocked_by_dependency", "failed", "needs_clarification",
})
UNRESOLVED_ROLES = frozenset({"entity", "metric", "dimension", "filter", "method"})

_REF_RE = re.compile(r"^(concept|metric|dimension):[a-z0-9_]+$")

_GOAL_KEYS = frozenset({
    "id", "priority", "type", "intent_text", "entity_ref", "entity_label",
    "metrics", "dimensions", "filters", "method", "depends_on",
    "ambiguities", "binning_requested", "sort", "limit", "temporal",
})
# Champs déterminés par NOREON : leur présence dans la sortie LLM est une faute.
_LLM_FORBIDDEN_KEYS = frozenset({
    "join_path", "physical", "cardinality", "fanout_risk", "grain", "traversal",
    "relations_used", "resolution", "coherence", "validated_relation_id",
    "creates_row_multiplication", "requires_pre_aggregation", "operation",
    "compile_ready", "compile_blockers", "join_graph", "catalog_snapshot",
    "pre_aggregations", "resolved_plan_schema_version",
})


class ContractError(ValueError):
    def __init__(self, code: str, path: str = "", detail: str = "") -> None:
        self.code = code
        self.path = path
        self.detail = detail
        super().__init__(f"[{code}] {path} {detail}".strip())


# --- Modèles typés -----------------------------------------------------------
@dataclass(frozen=True)
class Goal:
    id: str
    priority: int
    type: str
    intent_text: str
    entity_ref: str | None
    depends_on: tuple[str, ...] = ()
    raw: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Interpretation:
    goals: tuple[Goal, ...]
    unresolved_terms: tuple[dict, ...]

    def topological_order(self) -> list[str]:
        return topological_order(self.goals)


# --- Helpers de validation ---------------------------------------------------
def _require(cond: bool, code: str, path: str, detail: str = "") -> None:
    if not cond:
        raise ContractError(code, path, detail)


def _no_extra_keys(obj: dict, allowed: frozenset, path: str) -> None:
    extra = set(obj) - allowed
    _require(not extra, "unknown_field", path, f"champs inconnus : {sorted(extra)}")


def _is_ref(v) -> bool:
    return isinstance(v, str) and bool(_REF_RE.match(v))


# --- interpretation_json (SORTIE LLM) ---------------------------------------
def _scan_forbidden(payload: dict) -> None:
    """Invariant 3, AVANT Pydantic : un champ « Noreon-only » dans la sortie LLM
    doit produire un code précis, pas un « extra_forbidden » générique."""
    goals = payload.get("goals") if isinstance(payload, dict) else None
    if not isinstance(goals, list):
        return
    for i, g in enumerate(goals):
        if isinstance(g, dict):
            forbidden = set(g) & _LLM_FORBIDDEN_KEYS
            _require(not forbidden, "llm_forbidden_field", f"$.goals[{i}]",
                     f"réservé à Noreon : {sorted(forbidden)}")


def repair_goal_ids(payload: dict) -> dict:
    """Réparation SÛRE au bord LLM (voir `repair_goal_ids_report`). Renvoie le
    payload (réparé ou intact). La validation reste stricte en aval."""
    return repair_goal_ids_report(payload)[0]


def repair_goal_ids_report(payload: dict) -> tuple[dict, dict | None]:
    """Comme `repair_goal_ids`, mais renvoie aussi un RAPPORT de réparation
    `{type, duplicates, n_goals}` (ou `None`) — consommé par la télémétrie shadow
    pour suivre le repair rate par modèle et détecter une dérive.

    Ne renumérote QUE si aucune référence (`depends_on`, `unresolved_terms.goal_id`)
    ne pointe vers un id dupliqué — sinon plan ambigu, laissé échouer à la validation."""
    if not isinstance(payload, dict):
        return payload, None
    goals = payload.get("goals")
    if not isinstance(goals, list) or not all(isinstance(g, dict) for g in goals) or not goals:
        return payload, None
    ids = [g.get("id") for g in goals]
    if len(ids) == len(set(ids)):
        return payload, None                # déjà uniques
    from collections import Counter
    counts = Counter(ids)
    dup = {k for k, v in counts.items() if v > 1}
    referenced: set = set()
    for g in goals:
        referenced.update(g.get("depends_on") or [])
    for t in payload.get("unresolved_terms") or []:
        if isinstance(t, dict) and "goal_id" in t:
            referenced.add(t.get("goal_id"))
    if referenced & dup:
        return payload, None                # référence ambiguë → ne pas réparer
    old_to_new = {old: f"g{i}" for i, old in enumerate(ids, start=1) if counts[old] == 1}
    new = dict(payload)
    new_goals = []
    for i, g in enumerate(goals, start=1):
        ng = dict(g)
        ng["id"] = f"g{i}"
        deps = ng.get("depends_on")
        if isinstance(deps, list):
            ng["depends_on"] = [old_to_new.get(d, d) for d in deps]
        new_goals.append(ng)
    new["goals"] = new_goals
    uts = payload.get("unresolved_terms")
    if isinstance(uts, list):
        new["unresolved_terms"] = [
            ({**t, "goal_id": old_to_new.get(t.get("goal_id"), t.get("goal_id"))}
             if isinstance(t, dict) and "goal_id" in t else t)
            for t in uts]
    # Journalisée : toute réparation appliquée est un signal de DÉRIVE modèle à suivre.
    logger.warning(
        "planner_repair applied=goal_id_renumber duplicates=%s n_goals=%d "
        "schema=%s types=%s",
        sorted(dup), len(goals), INTERPRETATION_SCHEMA_VERSION, GOAL_TYPES_VERSION)
    report = {"type": "goal_id_renumber", "duplicates": sorted(dup), "n_goals": len(goals)}
    return new, report


def validate_interpretation(payload: dict) -> Interpretation:
    """Deux temps : (1) STRUCTURE via les modèles Pydantic (source unique du
    contrat, qui génère aussi le JSON Schema OVHcloud) ; (2) RÈGLES MÉTIER via
    les validateurs custom (références sémantiques, DAG, liaisons) et leurs codes."""
    _require(isinstance(payload, dict), "not_object", "$")
    _scan_forbidden(payload)

    # Échec PROPRE et précoce sur version de structure non supportée : aucune
    # tentative de réparation au-delà de repair_goal_ids (appelé en AMONT au bord LLM).
    _ver = payload.get("plan_schema_version")
    _require(_ver == INTERPRETATION_SCHEMA_VERSION, "unsupported_schema_version",
             "$.plan_schema_version",
             f"attendu {INTERPRETATION_SCHEMA_VERSION!r}, reçu {_ver!r}")

    # (1) Structure — Pydantic est la source unique du contrat structurel.
    from pydantic import ValidationError

    from app.analysis.schema_models import InterpretationDoc

    try:
        doc = InterpretationDoc.model_validate(payload)
    except ValidationError as e:
        err = e.errors()[0] if e.errors() else {}
        loc = ".".join(str(x) for x in err.get("loc", ()))
        raise ContractError("schema_invalid", f"$.{loc}", err.get("msg", "structure invalide"))

    # (2) Règles métier — codes précis.
    goals: list[Goal] = []
    for i, g in enumerate(doc.goals):
        p = f"$.goals[{i}]"
        _require(g.entity_ref is None or _is_ref(g.entity_ref), "entity_not_a_ref", p, str(g.entity_ref))
        for j, m in enumerate(g.metrics):
            mp = f"{p}.metrics[{j}]"
            _require(_is_ref(m.ref), "metric_not_a_ref", mp, str(m.ref))
            if m.of_ref is not None:
                _require(_is_ref(m.of_ref), "metric_of_not_a_ref", mp, str(m.of_ref))
        for j, d in enumerate(g.dimensions):
            _require(_is_ref(d.ref), "dimension_not_a_ref", f"{p}.dimensions[{j}]", str(d.ref))
        for j, f in enumerate(g.filters):
            _require(_is_ref(f.ref), "filter_not_a_ref", f"{p}.filters[{j}]", str(f.ref))
            _validate_filter_value(f.model_dump(), f"{p}.filters[{j}]")
        for j, s in enumerate(g.sort):
            _require(_is_ref(s.ref), "sort_not_a_ref", f"{p}.sort[{j}]", str(s.ref))
        if g.temporal is not None:
            _require(_is_ref(g.temporal.dimension_ref), "temporal_not_a_ref",
                     f"{p}.temporal.dimension_ref", str(g.temporal.dimension_ref))
        goals.append(Goal(id=g.id, priority=g.priority, type=g.type,
                          intent_text=g.intent_text, entity_ref=g.entity_ref,
                          depends_on=tuple(g.depends_on), raw=g.model_dump()))

    # Invariant 1 : DAG valide + tri topologique déterministe.
    validate_dag(goals)

    # unresolved_terms reliés à un goal existant (correction Δ4).
    ids = {g.id for g in goals}
    for i, t in enumerate(doc.unresolved_terms):
        _require(t.goal_id in ids, "unresolved_unknown_goal", f"$.unresolved_terms[{i}]", str(t.goal_id))

    _validate_goal_semantics(doc)

    return Interpretation(goals=tuple(goals),
                          unresolved_terms=tuple(t.model_dump() for t in doc.unresolved_terms))


_METHOD_REQUIRED = frozenset({"attribution", "segmentation", "affinity", "cohort", "correlation"})


def _validate_goal_semantics(doc) -> None:
    """Complétude C4 par type, sans inventer une décision analytique.

    Une absence est tolérée uniquement lorsqu'un unresolved ou une ambiguïté du
    même goal l'explique. C6 décidera ensuite si cela appelle une clarification
    ou rend le goal non supporté.
    """
    unresolved_by_goal: dict[str, list] = {}
    for term in doc.unresolved_terms:
        unresolved_by_goal.setdefault(term.goal_id, []).append(term)

    for index, goal in enumerate(doc.goals):
        path = f"$.goals[{index}]"
        reasons = unresolved_by_goal.get(goal.id, [])
        explained = bool(reasons or goal.ambiguities)
        operands = bool(
            goal.entity_ref or goal.metrics or goal.dimensions or goal.filters
            or goal.method or goal.temporal
        )
        _require(operands or explained, "goal_without_operand", path)

        metric_refs = {metric.ref for metric in goal.metrics}
        dimension_refs = {dimension.ref for dimension in goal.dimensions}
        used_refs = ({goal.entity_ref} if goal.entity_ref else set()) | metric_refs | dimension_refs
        used_refs |= {item.ref for item in goal.filters} | {item.ref for item in goal.sort}
        if goal.temporal is not None:
            used_refs.add(goal.temporal.dimension_ref)
        for term in reasons:
            _require(term.term not in used_refs, "resolved_ref_also_unresolved", path, term.term)

        if goal.type == "count":
            invalid = [metric for metric in goal.metrics
                       if metric.aggregation not in {"count", "count_distinct"}]
            _require(not invalid, "count_aggregation_mismatch", f"{path}.metrics")
            countable = bool(goal.entity_ref or any(
                metric.aggregation in {"count", "count_distinct"} for metric in goal.metrics
            ))
            _require(countable or explained, "count_operand_missing", path)

        if goal.type == "aggregate":
            _require(bool(goal.metrics) or explained, "aggregate_metric_missing", path)
            if _intent_requests_average(goal.intent_text):
                _require((not goal.metrics and explained)
                         or any(metric.aggregation == "avg" for metric in goal.metrics),
                         "average_aggregation_mismatch", f"{path}.metrics")

        if goal.type == "distribution":
            _require(bool(goal.dimensions) or explained, "distribution_dimension_missing", path)

        if goal.type == "trend":
            _require(bool(goal.metrics) or explained, "trend_metric_missing", path)
            _require(goal.temporal is not None or explained, "trend_temporal_missing", path)

        if goal.type == "ranking":
            _require(bool(goal.entity_ref or goal.dimensions),
                     "ranking_axis_missing", path)
            _require(bool(goal.metrics) or explained, "ranking_metric_missing", path)
            _require(bool(goal.sort) or explained, "ranking_sort_missing", path)
            _require(goal.limit is not None or explained, "ranking_limit_missing", path)
            for sort in goal.sort:
                _require(sort.ref in metric_refs | dimension_refs,
                         "ranking_sort_ref_not_selected", f"{path}.sort", sort.ref)

        if goal.type == "correlation":
            distinct = {metric.ref for metric in goal.metrics}
            _require(len(distinct) >= 2 or explained,
                     "correlation_requires_two_measures", path)

        if goal.type == "attribution":
            _require(bool(goal.metrics) or explained, "attribution_metric_missing", path)

        if goal.type == "cohort":
            _require(goal.temporal is not None or explained, "cohort_temporal_missing", path)

        if goal.type in _METHOD_REQUIRED:
            _require(goal.method is not None or explained, "exact_method_missing", path)


def _intent_requests_average(intent_text: str) -> bool:
    """Détecte uniquement le vocabulaire analytique AVG, jamais un terme métier."""
    normalized = (intent_text or "").casefold()
    return bool(re.search(r"\b(avg|average|mean|moyenn(?:e|es?)|moyen(?:ne|nes|s)?)\b", normalized))


def _validate_filter_value(value: dict, path: str) -> None:
    raw, value_type, operator = value.get("value"), value.get("value_type"), value.get("operator")
    if operator in {"is_null", "is_not_null", "current_period"}:
        _require(raw is None, "filter_value_must_be_null", f"{path}.value")
        return
    values = raw if operator in {"in", "not_in", "between"} else [raw]
    _require(isinstance(values, list) and values, "filter_value_not_list", f"{path}.value")
    if operator == "between":
        _require(len(values) == 2, "filter_between_arity", f"{path}.value")
    checks = {
        "string": lambda item: isinstance(item, str),
        "date": lambda item: isinstance(item, str),
        "datetime": lambda item: isinstance(item, str),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "number": lambda item: isinstance(item, (int, float)) and not isinstance(item, bool),
        "boolean": lambda item: isinstance(item, bool),
        "null": lambda item: item is None,
    }
    _require(value_type in checks and all(checks[value_type](item) for item in values),
             "filter_value_type_mismatch", f"{path}.value")


# --- DAG (invariant 1) -------------------------------------------------------
def validate_dag(goals) -> None:
    ids = [g.id for g in goals]
    _require(len(ids) == len(set(ids)), "duplicate_goal_id", "$.goals",
             f"ids en double : {[x for x in ids if ids.count(x) > 1]}")
    id_set = set(ids)
    by_id = {g.id: g for g in goals}

    for g in goals:
        for dep in g.depends_on:
            _require(dep != g.id, "self_dependency", f"$.goals#{g.id}")
            _require(dep in id_set, "unknown_dependency", f"$.goals#{g.id}", dep)
            # Priorité cohérente : un objectif ne dépend pas d'un objectif MOINS
            # prioritaire que lui (numéro strictement plus grand).
            _require(by_id[dep].priority <= g.priority, "incoherent_priority",
                     f"$.goals#{g.id}", f"dépend de {dep} moins prioritaire")

    _require(any(g.priority == 1 for g in goals), "no_primary_goal", "$.goals")

    # Kahn — détecte les cycles ; si des nœuds restent, il y a un cycle.
    order = _kahn(goals)
    _require(len(order) == len(goals), "cyclic_dependency", "$.goals")


def _kahn(goals) -> list[str]:
    by_id = {g.id: g for g in goals}
    indeg = {g.id: 0 for g in goals}
    for g in goals:
        for dep in g.depends_on:
            if dep in by_id:
                indeg[g.id] += 1
    # File déterministe : (priorité asc, id asc).
    ready = sorted([gid for gid, d in indeg.items() if d == 0],
                   key=lambda x: (by_id[x].priority, x))
    order: list[str] = []
    while ready:
        cur = ready.pop(0)
        order.append(cur)
        for g in goals:
            if cur in g.depends_on:
                indeg[g.id] -= 1
                if indeg[g.id] == 0:
                    ready.append(g.id)
        ready.sort(key=lambda x: (by_id[x].priority, x))
    return order


def topological_order(goals) -> list[str]:
    """Ordre d'exécution déterministe (tri par priorité puis id). Suppose un DAG
    déjà validé — utilisé après `validate_dag`."""
    return _kahn(goals)


# --- resolved_plan_json v2 (PRODUIT PAR NOREON) -----------------------------
_RESOLUTION_KEYS = frozenset({
    "goal_id", "status", "compile_ready", "compile_blockers", "depends_on",
    "concepts", "coverage", "operation", "physical", "join_graph", "filters",
    "sort", "limit", "temporal", "grain", "pre_aggregations", "method",
    "unsupported_reason", "clarification", "readiness",
})
_EXECUTABLE_KEYS = frozenset({
    "operation", "physical", "join_graph", "filters", "sort", "limit",
    "temporal", "grain", "pre_aggregations",
})
_AGGREGATIONS = frozenset({"sum", "avg", "min", "max", "count", "count_distinct", "none"})


def validate_resolved(payload: dict) -> dict:
    _require(isinstance(payload, dict), "not_object", "$")
    _no_extra_keys(payload, frozenset({
        "resolved_plan_schema_version", "source_interpretation_schema_version",
        "catalog_snapshot", "dag", "coherence", "resolution",
    }), "$")
    _require(payload.get("resolved_plan_schema_version") == RESOLVED_PLAN_SCHEMA_VERSION,
             "bad_resolved_schema_version", "$.resolved_plan_schema_version")
    _require(payload.get("source_interpretation_schema_version") == INTERPRETATION_SCHEMA_VERSION,
             "bad_source_schema_version", "$.source_interpretation_schema_version")

    snapshot = _validate_catalog_snapshot(payload.get("catalog_snapshot"), "$.catalog_snapshot")
    dag_dependencies = _validate_resolved_dag(payload.get("dag"), "$.dag")
    coherence = _validate_coherence(payload.get("coherence"))
    resolution = payload.get("resolution")
    _require(isinstance(resolution, list) and resolution, "empty_resolution", "$.resolution")
    _require({item.get("goal_id") for item in resolution if isinstance(item, dict)} == set(dag_dependencies),
             "dag_resolution_mismatch", "$.resolution")

    coverage_statuses: list[str] = []
    required_count = optional_count = 0
    for index, item in enumerate(resolution):
        path = f"$.resolution[{index}]"
        _validate_resolved_item(item, path, snapshot)
        _require(item["depends_on"] == dag_dependencies[item["goal_id"]],
                 "goal_dependencies_dag_mismatch", f"{path}.depends_on")
        coverage_statuses.append(item["coverage"]["status"])
        required_count += len(item["coverage"]["required_unresolved"])
        optional_count += len(item["coverage"]["optional_unresolved"])
    _require(coherence["coverage_status"] == _rollup_coverage_status(coverage_statuses),
             "incoherent_coverage_rollup", "$.coherence.coverage_status")
    _require(coherence["required_unresolved_count"] == required_count,
             "incoherent_required_unresolved_count", "$.coherence.required_unresolved_count")
    _require(coherence["optional_unresolved_count"] == optional_count,
             "incoherent_optional_unresolved_count", "$.coherence.optional_unresolved_count")
    return payload


def _validate_coherence(coherence) -> dict:
    _require(isinstance(coherence, dict), "missing_coherence", "$.coherence")
    _no_extra_keys(coherence, frozenset({
        "covers_question", "coverage_status", "computed_by",
        "required_unresolved_count", "optional_unresolved_count",
    }), "$.coherence")
    _require(isinstance(coherence.get("covers_question"), bool), "bad_covers_question", "$.coherence")
    _require(coherence.get("coverage_status") in COVERAGE_STATUS,
             "bad_coverage_status", "$.coherence.coverage_status")
    for key in ("required_unresolved_count", "optional_unresolved_count"):
        _require(isinstance(coherence.get(key), int) and not isinstance(coherence.get(key), bool)
                 and coherence[key] >= 0, "bad_unresolved_count", f"$.coherence.{key}")
    _require(coherence["covers_question"] == (coherence["coverage_status"] == "full"),
             "incoherent_coverage", "$.coherence")
    _require(coherence.get("computed_by") == "noreon",
             "coherence_not_computed_by_noreon", "$.coherence")
    return coherence


def _validate_catalog_snapshot(snapshot, path: str) -> dict:
    _require(isinstance(snapshot, dict), "missing_catalog_snapshot", path)
    _no_extra_keys(snapshot, frozenset({
        "schema_version", "snapshot_id", "captured_at", "fingerprint",
        "entities", "measures", "dimensions", "relations",
    }), path)
    _require(snapshot.get("schema_version") == CATALOG_SNAPSHOT_SCHEMA_VERSION,
             "bad_catalog_snapshot_version", f"{path}.schema_version")
    for key in ("entities", "measures", "dimensions", "relations"):
        _require(isinstance(snapshot.get(key), list), "bad_catalog_snapshot_list", f"{path}.{key}")
    body = {key: value for key, value in snapshot.items() if key != "fingerprint"}
    canonical = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    expected = hashlib.sha256(canonical.encode()).hexdigest()
    _require(snapshot.get("fingerprint") == expected, "catalog_snapshot_fingerprint_mismatch",
             f"{path}.fingerprint")
    _require(len({item.get("ref") for item in snapshot["entities"]}) == len(snapshot["entities"]),
             "duplicate_snapshot_entity", f"{path}.entities")
    _require(len({item.get("ref") for item in snapshot["measures"]}) == len(snapshot["measures"]),
             "duplicate_snapshot_measure", f"{path}.measures")
    _require(len({item.get("ref") for item in snapshot["dimensions"]}) == len(snapshot["dimensions"]),
             "duplicate_snapshot_dimension", f"{path}.dimensions")
    _require(len({item.get("id") for item in snapshot["relations"]}) == len(snapshot["relations"]),
             "duplicate_snapshot_relation", f"{path}.relations")
    for key in ("entities", "measures", "dimensions"):
        _require(all(isinstance(item.get("aliases"), list)
                     and all(isinstance(alias, str) and alias for alias in item["aliases"])
                     for item in snapshot[key]),
                 "bad_snapshot_aliases", f"{path}.{key}")
    _require(all(isinstance(item.get("executable"), bool) for item in snapshot["relations"]),
             "bad_snapshot_relation_executable", f"{path}.relations")
    return snapshot


def _validate_resolved_dag(dag, path: str) -> dict[str, list[str]]:
    _require(isinstance(dag, dict), "missing_dag", path)
    _no_extra_keys(dag, frozenset({"nodes", "edges", "topological_order"}), path)
    nodes, edges, order = dag.get("nodes"), dag.get("edges"), dag.get("topological_order")
    _require(isinstance(nodes, list) and nodes, "empty_dag", f"{path}.nodes")
    ids = [node.get("goal_id") for node in nodes if isinstance(node, dict)]
    _require(len(ids) == len(nodes) and all(isinstance(value, str) and value for value in ids),
             "bad_dag_node", f"{path}.nodes")
    _require(len(ids) == len(set(ids)), "duplicate_dag_node", f"{path}.nodes")
    for index, node in enumerate(nodes):
        _no_extra_keys(node, frozenset({"goal_id", "priority", "depends_on"}),
                       f"{path}.nodes[{index}]")
    _require(all(isinstance(node.get("priority"), int) and not isinstance(node.get("priority"), bool)
                 and node["priority"] >= 1 and isinstance(node.get("depends_on"), list)
                 and all(dependency in ids for dependency in node["depends_on"])
                 for node in nodes), "bad_dag_node", f"{path}.nodes")
    _require(isinstance(edges, list), "bad_dag_edges", f"{path}.edges")
    for index, edge in enumerate(edges):
        _require(isinstance(edge, dict), "not_object", f"{path}.edges[{index}]")
        _no_extra_keys(edge, frozenset({"from_goal_id", "to_goal_id"}),
                       f"{path}.edges[{index}]")
    expected_edges = {(dependency, node["goal_id"])
                      for node in nodes for dependency in (node.get("depends_on") or [])}
    actual_edges = {(edge.get("from_goal_id"), edge.get("to_goal_id"))
                    for edge in edges if isinstance(edge, dict)}
    _require(actual_edges == expected_edges, "incoherent_dag_edges", f"{path}.edges")
    _require(isinstance(order, list) and set(order) == set(ids) and len(order) == len(ids),
             "bad_topological_order", f"{path}.topological_order")
    positions = {goal_id: index for index, goal_id in enumerate(order)}
    _require(all(positions[parent] < positions[child] for parent, child in actual_edges),
             "non_topological_order", f"{path}.topological_order")
    return {node["goal_id"]: list(node.get("depends_on") or []) for node in nodes}


def _validate_resolved_item(item, path: str, snapshot: dict) -> None:
    _require(isinstance(item, dict), "not_object", path)
    _no_extra_keys(item, _RESOLUTION_KEYS, path)
    _require(isinstance(item.get("goal_id"), str) and item["goal_id"], "bad_goal_id", path)
    _require(item.get("status") in RESOLUTION_STATUS, "bad_status", path)
    _require(isinstance(item.get("compile_ready"), bool), "missing_compile_ready", path)
    readiness = item.get("readiness")
    _require(isinstance(readiness, dict), "missing_compile_readiness", f"{path}.readiness")
    _no_extra_keys(readiness, frozenset({
        "semantic_complete", "internally_consistent", "physically_resolved",
        "analytically_safe",
    }), f"{path}.readiness")
    _require(all(isinstance(readiness.get(key), bool) for key in (
        "semantic_complete", "internally_consistent", "physically_resolved",
        "analytically_safe",
    )), "bad_compile_readiness", f"{path}.readiness")
    if item["status"] == "SUPPORTED":
        _require(item["compile_ready"] is True, "supported_not_compile_ready", path)
    _require(item["compile_ready"] == all(readiness.values()),
             "compile_readiness_mismatch", f"{path}.compile_ready")
    blockers = item.get("compile_blockers")
    _require(isinstance(blockers, list) and all(isinstance(value, str) for value in blockers),
             "bad_compile_blockers", path)
    _require(isinstance(item.get("depends_on"), list), "bad_goal_dependencies", path)
    _validate_goal_coverage(item.get("coverage"), f"{path}.coverage")
    expected_coverage = {"SUPPORTED": "full", "PARTIAL": "partial", "UNSUPPORTED": "none",
                         "NEEDS_CLARIFICATION": "needs_clarification"}[item["status"]]
    _require(item["coverage"]["status"] == expected_coverage,
             "incoherent_goal_coverage", f"{path}.coverage.status")

    # Invariant éliminatoire P0-B : aucun SUPPORTED seulement théorique.
    if item["compile_ready"]:
        _require(not blockers, "compile_ready_with_blockers", path)
        _require(_EXECUTABLE_KEYS <= set(item), "compile_ready_missing_instruction", path)
        _validate_executable(item, path, snapshot)
    else:
        _require(item["status"] not in ("SUPPORTED",), "supported_not_compile_ready", path)
    if item["status"] == "UNSUPPORTED":
        _require(isinstance(item.get("unsupported_reason"), str) and item["unsupported_reason"],
                 "missing_unsupported_reason", path)
    if item["status"] == "NEEDS_CLARIFICATION":
        _require(isinstance(item.get("clarification"), str) and item["clarification"],
                 "missing_clarification", path)
    if "method" in item:
        _validate_method(item["method"], f"{path}.method")


def _validate_executable(item: dict, path: str, snapshot: dict) -> None:
    _validate_operation(item["operation"], f"{path}.operation")
    _validate_join_graph(item["join_graph"], f"{path}.join_graph", snapshot)
    _validate_physical(item["physical"], f"{path}.physical", snapshot)
    _validate_typed_clauses(item["filters"], f"{path}.filters", is_filter=True)
    _validate_typed_clauses(item["sort"], f"{path}.sort", is_filter=False)
    _require(item["limit"] is None or (isinstance(item["limit"], int)
             and not isinstance(item["limit"], bool) and 1 <= item["limit"] <= 10000),
             "bad_limit", f"{path}.limit")
    _validate_temporal(item["temporal"], f"{path}.temporal")
    if item["operation"]["kind"] == "ranking":
        axes = item["operation"]["parameters"].get("ranked_axis_refs")
        _require(isinstance(axes, list) and bool(axes),
                 "ranking_axis_missing", f"{path}.operation.parameters.ranked_axis_refs")
        _require(bool(item["operation"]["metrics"]),
                 "ranking_metric_missing", f"{path}.operation.metrics")
        _require(bool(item["sort"]), "ranking_sort_missing", f"{path}.sort")
        _require(item["limit"] is not None, "ranking_limit_missing", f"{path}.limit")
    _validate_snapshot_bindings(item, path, snapshot)
    _validate_grain(item["grain"], f"{path}.grain")
    preaggs = item["pre_aggregations"]
    _require(isinstance(preaggs, list), "bad_pre_aggregations", f"{path}.pre_aggregations")
    for index, instruction in enumerate(preaggs):
        _validate_pre_aggregation(instruction, f"{path}.pre_aggregations[{index}]")
    required_preaggs = {entry.get("ref") for entry in item["grain"]["measure_grains"]
                        if entry.get("aggregation_strategy") == "pre_aggregation"}
    instructed = {aggregation.get("measure_ref") for instruction in preaggs
                  for aggregation in instruction.get("aggregations", [])}
    _require(required_preaggs <= instructed, "missing_pre_aggregation_instruction",
             f"{path}.pre_aggregations")


def _validate_snapshot_bindings(item: dict, path: str, snapshot: dict) -> None:
    columns = {entry.get("ref"): entry for key in ("measures", "dimensions")
               for entry in snapshot[key]}
    mappings = list(item["operation"]["metrics"])
    mappings += list(item["physical"]["measures"]) + list(item["physical"]["dimensions"])
    mappings += list(item["filters"]) + list(item["sort"])
    for index, mapping in enumerate(mappings):
        snap = columns.get(mapping.get("ref"))
        _require(snap is not None and snap.get("physical") == mapping.get("physical"),
                 "physical_mapping_not_in_snapshot", f"{path}.mappings[{index}]")
    _require(item["operation"]["metrics"] == item["physical"]["measures"],
             "operation_physical_mismatch", path)
    if item["operation"]["operator"] == "count_distinct":
        entities = {entry.get("ref"): entry for entry in snapshot["entities"]}
        root = entities.get(item["physical"].get("root_entity_ref")) or {}
        _require(item["operation"]["count_distinct_keys"] == root.get("grain_keys"),
                 "count_key_not_in_snapshot", f"{path}.operation.count_distinct_keys")
    temporal = item["temporal"]
    if temporal["enabled"]:
        snap = columns.get(temporal.get("dimension_ref"))
        _require(snap is not None and snap.get("physical") == temporal.get("physical"),
                 "temporal_mapping_not_in_snapshot", f"{path}.temporal")


def _validate_operation(operation, path: str) -> None:
    _require(isinstance(operation, dict), "missing_operation", path)
    _no_extra_keys(operation, frozenset({
        "kind", "operator", "metrics", "count_distinct_keys", "parameters",
    }), path)
    _require(operation.get("kind") in GOAL_TYPES, "bad_operation_kind", f"{path}.kind")
    _require(isinstance(operation.get("operator"), str) and operation["operator"],
             "missing_exact_operator", f"{path}.operator")
    _require(isinstance(operation.get("metrics"), list), "bad_operation_metrics", f"{path}.metrics")
    for index, mapping in enumerate(operation["metrics"]):
        _validate_column_mapping(mapping, f"{path}.metrics[{index}]", measure=True)
    keys = operation.get("count_distinct_keys")
    _require(isinstance(keys, list), "bad_count_distinct_keys", f"{path}.count_distinct_keys")
    if operation["operator"] == "count_distinct":
        _require(bool(keys) and all(_qualified(key.get("physical")) for key in keys),
                 "count_distinct_key_missing", f"{path}.count_distinct_keys")
        _require(all(mapping.get("aggregation") in {"count", "count_distinct"}
                     for mapping in operation["metrics"]),
                 "count_aggregation_mismatch", f"{path}.metrics")
    expected_operator = {
        "count": "count_distinct", "aggregate": "aggregate",
        "trend": "time_series_aggregate", "ranking": "ranking",
        "distribution": "distribution", "attribution": "attribution",
        "segmentation": "segmentation", "affinity": "affinity",
        "cohort": "cohort", "correlation": "correlation",
    }[operation["kind"]]
    _require(operation["operator"] == expected_operator,
             "operation_kind_mismatch", f"{path}.operator")
    _require(isinstance(operation.get("parameters"), dict), "bad_operation_parameters", path)


def _validate_physical(physical, path: str, snapshot: dict) -> None:
    _require(isinstance(physical, dict), "missing_physical", path)
    _no_extra_keys(physical, frozenset({
        "root_entity_ref", "root_table", "root_alias", "entities", "measures", "dimensions",
    }), path)
    entity_index = {item.get("ref"): item for item in snapshot["entities"]}
    root = entity_index.get(physical.get("root_entity_ref"))
    _require(root is not None and root.get("physical_table") == physical.get("root_table"),
             "root_mapping_not_in_snapshot", path)
    _require(isinstance(physical.get("root_alias"), str) and physical["root_alias"],
             "missing_root_alias", path)
    for key in ("entities", "measures", "dimensions"):
        _require(isinstance(physical.get(key), list), "bad_physical_mappings", f"{path}.{key}")
    for index, mapping in enumerate(physical["measures"]):
        _validate_column_mapping(mapping, f"{path}.measures[{index}]", measure=True)
    for index, mapping in enumerate(physical["dimensions"]):
        _validate_column_mapping(mapping, f"{path}.dimensions[{index}]", measure=False)


def _validate_join_graph(graph, path: str, snapshot: dict) -> None:
    _require(isinstance(graph, dict), "missing_join_graph", path)
    _no_extra_keys(graph, frozenset({
        "root_entity_ref", "root_alias", "nodes", "edges", "execution_order",
    }), path)
    nodes, edges = graph.get("nodes"), graph.get("edges")
    _require(isinstance(nodes, list) and nodes, "empty_join_graph", f"{path}.nodes")
    _require(isinstance(edges, list), "bad_join_edges", f"{path}.edges")
    aliases = [node.get("alias") for node in nodes if isinstance(node, dict)]
    _require(len(aliases) == len(nodes) and len(set(aliases)) == len(aliases),
             "duplicate_join_alias", f"{path}.nodes")
    _require(any(node.get("entity_ref") == graph.get("root_entity_ref")
                 and node.get("alias") == graph.get("root_alias") for node in nodes),
             "join_root_missing", path)
    entity_index = {item.get("ref"): item for item in snapshot["entities"]}
    for index, node in enumerate(nodes):
        snap = entity_index.get(node.get("entity_ref"))
        _require(snap is not None and snap.get("physical_table") == node.get("physical_table")
                 and isinstance(node.get("physical_table"), str) and node["physical_table"],
                 "join_node_not_in_snapshot", f"{path}.nodes[{index}]")
    relation_index = {item.get("id"): item for item in snapshot["relations"]}
    relation_ids = []
    for index, edge in enumerate(edges):
        edge_path = f"{path}.edges[{index}]"
        _require(isinstance(edge, dict), "not_object", edge_path)
        _no_extra_keys(edge, frozenset({
            "validated_relation_id", "left_entity_ref", "left_alias", "left_key",
            "right_entity_ref", "right_alias", "right_key", "cardinality",
            "fanout_risk", "direction", "declared_direction", "origin", "status",
            "validation_status", "coverage", "target_uniqueness", "evidence",
            "provenance",
        }), edge_path)
        relation_id = edge.get("validated_relation_id")
        _require(relation_id in relation_index, "join_relation_not_in_snapshot", edge_path)
        relation = relation_index[relation_id]
        _require(relation.get("executable") is True,
                 "join_relation_not_executable", edge_path)
        forward = (
            edge.get("left_entity_ref"), edge.get("right_entity_ref"),
            edge.get("left_key"), edge.get("right_key"), edge.get("cardinality"),
        )
        inverse_cardinality = {
            "many_to_one": "one_to_many", "one_to_many": "many_to_one",
            "one_to_one": "one_to_one", "many_to_many": "many_to_many",
        }.get(relation.get("cardinality"))
        expected_forward = (
            relation.get("from_entity_ref"), relation.get("to_entity_ref"),
            relation.get("from_key"), relation.get("to_key"), relation.get("cardinality"),
        )
        expected_inverse = (
            relation.get("to_entity_ref"), relation.get("from_entity_ref"),
            relation.get("to_key"), relation.get("from_key"), inverse_cardinality,
        )
        _require(forward in (expected_forward, expected_inverse),
                 "join_edge_not_in_snapshot", edge_path)
        is_forward = forward == expected_forward
        _require(edge.get("direction") == ("forward" if is_forward else "inverse"),
                 "bad_join_direction", edge_path)
        for key in ("declared_direction", "origin", "status", "validation_status",
                    "coverage", "target_uniqueness", "evidence", "provenance"):
            _require(edge.get(key) == relation.get(key),
                     "join_provenance_not_in_snapshot", f"{edge_path}.{key}")
        _require(_qualified(edge.get("left_key")) and _qualified(edge.get("right_key")),
                 "bad_join_key", edge_path)
        _require(edge.get("cardinality") in CARDINALITIES, "bad_cardinality", edge_path)
        _require(isinstance(edge.get("fanout_risk"), bool), "bad_step_fanout", edge_path)
        _require(edge["fanout_risk"] == (edge["cardinality"] in {"one_to_many", "many_to_many"}),
                 "incoherent_step_fanout", edge_path)
        _require(edge.get("left_alias") in aliases and edge.get("right_alias") in aliases,
                 "unknown_join_alias", edge_path)
        relation_ids.append(relation_id)
    _require(len(relation_ids) == len(set(relation_ids)), "duplicate_join_relation", f"{path}.edges")
    _require(graph.get("execution_order") == relation_ids,
             "bad_join_execution_order", f"{path}.execution_order")


def _validate_column_mapping(mapping, path: str, *, measure: bool) -> None:
    _require(isinstance(mapping, dict), "not_object", path)
    required = {"ref", "source_alias", "physical", "table", "column", "data_type"}
    required |= ({"source_entity_ref", "aggregation", "output_alias"} if measure else {"home_entity_ref"})
    _require(required <= set(mapping), "incomplete_physical_mapping", path)
    _require(_qualified(mapping.get("physical")), "bad_physical_column", f"{path}.physical")
    _require(isinstance(mapping.get("source_alias"), str) and mapping["source_alias"],
             "missing_source_alias", path)
    if measure:
        _require(mapping.get("aggregation") in _AGGREGATIONS,
                 "bad_aggregation", f"{path}.aggregation")


def _validate_typed_clauses(values, path: str, *, is_filter: bool) -> None:
    _require(isinstance(values, list), "not_list", path)
    for index, value in enumerate(values):
        clause_path = f"{path}[{index}]"
        _validate_column_mapping(value, clause_path, measure=False)
        if is_filter:
            _require(isinstance(value.get("operator"), str) and value["operator"],
                     "missing_filter_operator", clause_path)
            _require(value.get("value_type") in {"string", "integer", "number", "boolean",
                                                  "date", "datetime", "null"},
                     "bad_filter_value_type", clause_path)
            _require(value.get("conjunction") in {"and", "or"}, "bad_filter_conjunction", clause_path)
        else:
            _require(value.get("direction") in {"asc", "desc"}, "bad_sort_direction", clause_path)
            _require(value.get("nulls") in {"first", "last"}, "bad_nulls_order", clause_path)


def _validate_temporal(temporal, path: str) -> None:
    _require(isinstance(temporal, dict), "missing_temporal", path)
    _no_extra_keys(temporal, frozenset({
        "enabled", "dimension_ref", "source_alias", "physical", "data_type", "grain", "timezone",
    }), path)
    _require(isinstance(temporal.get("enabled"), bool), "bad_temporal_enabled", path)
    if temporal["enabled"]:
        _require(_qualified(temporal.get("physical")), "bad_temporal_physical", path)
        _require(temporal.get("grain") in {"hour", "day", "week", "month", "quarter", "year"},
                 "bad_temporal_grain", path)
        _require(isinstance(temporal.get("timezone"), str) and temporal["timezone"],
                 "missing_timezone", path)


def _validate_grain(grain, path: str) -> None:
    _require(isinstance(grain, dict), "missing_grain", path)
    required = {"base_grain", "source_grain", "metric_additivity", "traversal", "input_grain",
                "metric_grain", "creates_row_multiplication", "requires_pre_aggregation",
                "aggregation_strategy", "measure_grains"}
    _require(required <= set(grain), "missing_grain_field", path)
    _require(grain.get("traversal") in CARDINALITIES, "bad_traversal", path)
    crm, rpa = grain.get("creates_row_multiplication"), grain.get("requires_pre_aggregation")
    _require(isinstance(crm, bool), "bad_creates_row_multiplication", path)
    _require(isinstance(rpa, bool), "bad_requires_pre_aggregation", path)
    _require(not (crm and not rpa), "fanout_without_pre_aggregation", path)
    _require(isinstance(grain.get("measure_grains"), list) and grain["measure_grains"],
             "missing_measure_grains", path)
    for index, item in enumerate(grain["measure_grains"]):
        item_path = f"{path}.measure_grains[{index}]"
        required = {"ref", "source_entity_ref", "source_grain_keys", "aggregation", "traversal",
                    "creates_row_multiplication", "requires_pre_aggregation",
                    "aggregation_strategy", "relation_ids"}
        _require(isinstance(item, dict) and required <= set(item),
                 "incomplete_measure_grain", item_path)
        _require(item.get("aggregation") in _AGGREGATIONS, "bad_aggregation", item_path)
        _require(item.get("traversal") in CARDINALITIES, "bad_traversal", item_path)
        _require(isinstance(item.get("source_grain_keys"), list), "bad_source_grain_keys", item_path)
        _require(isinstance(item.get("relation_ids"), list)
                 and all(isinstance(value, int) for value in item["relation_ids"]),
                 "bad_grain_relation_ids", item_path)


def _validate_pre_aggregation(instruction, path: str) -> None:
    _require(isinstance(instruction, dict), "not_object", path)
    required = {"required", "strategy", "source_entity_ref", "input_alias", "output_alias",
                "group_by", "aggregations", "join_back", "fanout_path_relation_ids"}
    _require(required <= set(instruction), "incomplete_pre_aggregation", path)
    _require(instruction.get("required") is True, "bad_pre_aggregation_required", path)
    _require(isinstance(instruction.get("group_by"), list) and instruction["group_by"]
             and all(_qualified(item.get("physical")) and item.get("output_alias")
                     for item in instruction["group_by"]), "bad_pre_aggregation_group_by", path)
    _require(isinstance(instruction.get("aggregations"), list) and instruction["aggregations"]
             and all(item.get("function") in _AGGREGATIONS and _qualified(item.get("input_physical"))
                     and item.get("output_alias") for item in instruction["aggregations"]),
             "bad_pre_aggregation_aggregations", path)
    _require(isinstance(instruction.get("join_back"), list), "bad_pre_aggregation_join_back", path)
    _require(all(_qualified(item.get("source_key")) and _qualified(item.get("target_key"))
                 and isinstance(item.get("target_alias"), str) and item["target_alias"]
                 and isinstance(item.get("validated_relation_id"), int)
                 and isinstance(item.get("output_key_alias"), str) and item["output_key_alias"]
                 for item in instruction["join_back"]),
             "incomplete_pre_aggregation_join_back", path)
    _require(isinstance(instruction.get("fanout_path_relation_ids"), list)
             and all(isinstance(value, int) for value in instruction["fanout_path_relation_ids"]),
             "bad_pre_aggregation_path", path)


def _qualified(value) -> bool:
    return isinstance(value, str) and "." in value and all(value.rsplit(".", 1))


def _rollup_coverage_status(statuses: list[str]) -> str:
    if not statuses or all(status == "none" for status in statuses):
        return "none"
    if any(status == "needs_clarification" for status in statuses):
        return "needs_clarification"
    if all(status == "full" for status in statuses):
        return "full"
    return "partial"


def _validate_method(method, path: str) -> None:
    _require(isinstance(method, dict), "not_object", path)
    _require(isinstance(method.get("name"), str) and method["name"], "missing_method_name", path)
    _require(isinstance(method.get("version"), str) and method["version"], "missing_method_version", path)
    _require(isinstance(method.get("params"), dict), "missing_method_params", path)


def _validate_goal_coverage(coverage, path: str) -> None:
    _require(isinstance(coverage, dict), "not_object", path)
    _no_extra_keys(coverage, frozenset({"status", "required_unresolved", "optional_unresolved"}), path)
    _require(coverage.get("status") in COVERAGE_STATUS, "bad_coverage_status", f"{path}.status")
    for key in ("required_unresolved", "optional_unresolved"):
        values = coverage.get(key)
        _require(isinstance(values, list), "bad_unresolved_refs", f"{path}.{key}")
        _require(all(isinstance(value, dict) and isinstance(value.get("role"), str)
                     and isinstance(value.get("reason_code"), str) for value in values),
                 "bad_unresolved_ref", f"{path}.{key}")
