"""Phase 2 — C1 : contrat JSON strict du planificateur analytique.

Deux documents distincts, audités séparément :

- `interpretation_json` : SORTIE DU LLM. Il ne choisit que des références
  sémantiques (`concept:*`, `metric:*`, `dimension:*`) et déclare des
  dépendances entre objectifs (`depends_on`). Il ne connaît AUCUN nom physique,
  AUCUN chemin de jointure, AUCUNE cardinalité, AUCUN fanout : ces champs y sont
  INTERDITS et rejetés.
- `resolved_plan_json` : PRODUIT PAR NOREON. Le physique, le `join_path` orienté
  (avec id de relation validée et fanout par étape), le grain et le descripteur
  de multiplication de lignes, la méthode figée, et `coherence.covers_question`
  (calculé par Noreon, jamais par le LLM) n'existent QUE là.

Toute violation lève `ContractError(code=...)` — les codes sont testés.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

PLAN_SCHEMA_VERSION = "1.0"

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
    "ambiguities", "binning_requested",
})
# Champs déterminés par NOREON : leur présence dans la sortie LLM est une faute.
_LLM_FORBIDDEN_KEYS = frozenset({
    "join_path", "physical", "cardinality", "fanout_risk", "grain", "traversal",
    "relations_used", "resolution", "coherence", "validated_relation_id",
    "creates_row_multiplication", "requires_pre_aggregation",
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
def validate_interpretation(payload: dict) -> Interpretation:
    _require(isinstance(payload, dict), "not_object", "$")
    _no_extra_keys(payload, frozenset({"plan_schema_version", "goals", "unresolved_terms"}), "$")
    _require(payload.get("plan_schema_version") == PLAN_SCHEMA_VERSION,
             "bad_schema_version", "$.plan_schema_version", str(payload.get("plan_schema_version")))

    goals_raw = payload.get("goals")
    _require(isinstance(goals_raw, list) and goals_raw, "empty_goals", "$.goals")

    goals: list[Goal] = []
    for i, g in enumerate(goals_raw):
        p = f"$.goals[{i}]"
        _require(isinstance(g, dict), "not_object", p)
        # Invariant 3 : aucun champ « Noreon-only » dans la sortie LLM.
        forbidden = set(g) & _LLM_FORBIDDEN_KEYS
        _require(not forbidden, "llm_forbidden_field", p, f"réservé à Noreon : {sorted(forbidden)}")
        _no_extra_keys(g, _GOAL_KEYS, p)

        gid = g.get("id")
        _require(isinstance(gid, str) and gid, "bad_goal_id", p)
        prio = g.get("priority")
        _require(isinstance(prio, int) and not isinstance(prio, bool) and prio >= 1,
                 "bad_priority", p, str(prio))
        _require(g.get("type") in GOAL_TYPES, "bad_goal_type", p, str(g.get("type")))
        _require(isinstance(g.get("intent_text"), str) and g["intent_text"].strip(),
                 "missing_intent_text", p)

        entity_ref = g.get("entity_ref", None)
        # entity_ref est SOIT une référence sémantique, SOIT null (→ terme non résolu).
        _require(entity_ref is None or _is_ref(entity_ref), "entity_not_a_ref", p, str(entity_ref))

        # metrics : références sémantiques uniquement.
        for j, m in enumerate(g.get("metrics", []) or []):
            mp = f"{p}.metrics[{j}]"
            _require(isinstance(m, dict), "not_object", mp)
            _no_extra_keys(m, frozenset({"ref", "of_ref"}), mp)
            _require(_is_ref(m.get("ref")), "metric_not_a_ref", mp, str(m.get("ref")))
            if "of_ref" in m:
                _require(_is_ref(m["of_ref"]), "metric_of_not_a_ref", mp, str(m["of_ref"]))

        for j, d in enumerate(g.get("dimensions", []) or []):
            dp = f"{p}.dimensions[{j}]"
            _require(isinstance(d, dict) and _is_ref(d.get("ref")), "dimension_not_a_ref", dp, str(d))

        deps = g.get("depends_on", []) or []
        _require(isinstance(deps, list) and all(isinstance(x, str) for x in deps),
                 "bad_depends_on", p)

        goals.append(Goal(id=gid, priority=prio, type=g["type"],
                          intent_text=g["intent_text"], entity_ref=entity_ref,
                          depends_on=tuple(deps), raw=g))

    # Invariant 1 : DAG valide (unicité, existence, pas d'auto-dép, pas de cycle,
    # priorités cohérentes) + tri topologique déterministe.
    validate_dag(goals)

    # unresolved_terms : chaque terme est RELIÉ à un goal existant (correction Δ4).
    ut_raw = payload.get("unresolved_terms", []) or []
    _require(isinstance(ut_raw, list), "bad_unresolved_terms", "$.unresolved_terms")
    ids = {g.id for g in goals}
    for i, t in enumerate(ut_raw):
        tp = f"$.unresolved_terms[{i}]"
        _require(isinstance(t, dict), "not_object", tp)
        _no_extra_keys(t, frozenset({"goal_id", "term", "role", "source_span", "reason"}), tp)
        _require(t.get("goal_id") in ids, "unresolved_unknown_goal", tp, str(t.get("goal_id")))
        _require(isinstance(t.get("term"), str) and t["term"].strip(), "missing_term", tp)
        _require(t.get("role") in UNRESOLVED_ROLES, "bad_unresolved_role", tp, str(t.get("role")))

    return Interpretation(goals=tuple(goals), unresolved_terms=tuple(ut_raw))


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


# --- resolved_plan_json (PRODUIT PAR NOREON) --------------------------------
_GRAIN_KEYS = frozenset({
    "base_grain", "source_grain", "metric_additivity", "traversal",
    "input_grain", "metric_grain", "creates_row_multiplication",
    "requires_pre_aggregation", "aggregation_strategy",
})
_JOIN_STEP_KEYS = frozenset({"from", "to", "cardinality", "validated_relation_id", "fanout_risk"})
_RESOLUTION_KEYS = frozenset({
    "goal_id", "status", "concepts", "physical", "join_path", "grain",
    "quality", "method", "unsupported_reason", "clarification",
})


def validate_resolved(payload: dict) -> dict:
    _require(isinstance(payload, dict), "not_object", "$")
    _no_extra_keys(payload, frozenset({"plan_schema_version", "coherence", "resolution"}), "$")
    _require(payload.get("plan_schema_version") == PLAN_SCHEMA_VERSION,
             "bad_schema_version", "$.plan_schema_version")

    coh = payload.get("coherence")
    _require(isinstance(coh, dict), "missing_coherence", "$.coherence")
    _no_extra_keys(coh, frozenset({"covers_question", "computed_by"}), "$.coherence")
    _require(isinstance(coh.get("covers_question"), bool), "bad_covers_question", "$.coherence")
    # Invariant : covers_question est calculé par NOREON, jamais déclaré par le LLM.
    _require(coh.get("computed_by") == "noreon", "coherence_not_computed_by_noreon", "$.coherence")

    res = payload.get("resolution")
    _require(isinstance(res, list) and res, "empty_resolution", "$.resolution")
    for i, r in enumerate(res):
        p = f"$.resolution[{i}]"
        _require(isinstance(r, dict), "not_object", p)
        _no_extra_keys(r, _RESOLUTION_KEYS, p)
        _require(isinstance(r.get("goal_id"), str), "bad_goal_id", p)
        _require(r.get("status") in RESOLUTION_STATUS, "bad_status", p, str(r.get("status")))

        if r["status"] in ("SUPPORTED", "PARTIAL"):
            _require(isinstance(r.get("physical"), dict), "missing_physical", p)
            _validate_join_path(r.get("join_path"), f"{p}.join_path")
            _validate_grain(r.get("grain"), f"{p}.grain")
        if r["status"] == "UNSUPPORTED":
            _require(isinstance(r.get("unsupported_reason"), str) and r["unsupported_reason"].strip(),
                     "missing_unsupported_reason", p)
        if "method" in r and r["method"] is not None:
            _validate_method(r["method"], f"{p}.method")
    return payload


def _validate_join_path(jp, path: str) -> None:
    _require(isinstance(jp, list), "missing_join_path", path)
    for k, step in enumerate(jp):
        sp = f"{path}[{k}]"
        _require(isinstance(step, dict), "not_object", sp)
        _no_extra_keys(step, _JOIN_STEP_KEYS, sp)
        _require(isinstance(step.get("from"), str) and "." in step["from"], "bad_join_from", sp)
        _require(isinstance(step.get("to"), str) and "." in step["to"], "bad_join_to", sp)
        _require(step.get("cardinality") in CARDINALITIES, "bad_cardinality", sp, str(step.get("cardinality")))
        _require(isinstance(step.get("validated_relation_id"), int)
                 and not isinstance(step["validated_relation_id"], bool),
                 "missing_validated_relation_id", sp)
        _require(isinstance(step.get("fanout_risk"), bool), "bad_step_fanout", sp)


def _validate_grain(grain, path: str) -> None:
    _require(isinstance(grain, dict), "missing_grain", path)
    _no_extra_keys(grain, _GRAIN_KEYS, path)
    for key in ("base_grain", "source_grain", "metric_grain", "input_grain", "traversal"):
        _require(isinstance(grain.get(key), str) and grain[key], "missing_grain_field", path, key)
    _require(grain.get("traversal") in CARDINALITIES, "bad_traversal", path, str(grain.get("traversal")))
    crm = grain.get("creates_row_multiplication")
    rpa = grain.get("requires_pre_aggregation")
    _require(isinstance(crm, bool), "bad_creates_row_multiplication", path)
    _require(isinstance(rpa, bool), "bad_requires_pre_aggregation", path)
    # Invariant 2 : le fanout est un CALCUL (sens de parcours + grains), pas un OR
    # statique. Contrat minimal : s'il multiplie les lignes, il EXIGE une
    # pré-agrégation — sinon la mesure serait dupliquée.
    _require(not (crm and not rpa), "fanout_without_pre_aggregation", path)


def _validate_method(method, path: str) -> None:
    _require(isinstance(method, dict), "not_object", path)
    _require(isinstance(method.get("name"), str) and method["name"], "missing_method_name", path)
    _require(isinstance(method.get("version"), str) and method["version"], "missing_method_version", path)
    _require(isinstance(method.get("params"), dict), "missing_method_params", path)
