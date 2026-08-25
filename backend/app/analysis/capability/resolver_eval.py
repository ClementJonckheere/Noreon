"""Phase 2 — C6 : benchmark DÉTERMINISTE du CapabilityResolver.

Compact (multi-domaines Retail/SaaS/Solo), il FIGE les comportements analytiques
structurants : état de résolution, grain, join path, fanout, stratégie de sécurité,
additivité, unresolved et blockers.

Pas de score global opaque : on affiche des taux PAR DIMENSION. Toute VIOLATION DE
SÉCURITÉ ANALYTIQUE est éliminatoire (fanout ignoré, somme non-additive, relation/
grain inventé, COUNT incorrect sous fanout, accès contourné, unresolved transformé
silencieusement en available). Chaque cas produit une SIGNATURE normalisée
comparée à un snapshot de référence (détection de dérive du resolver).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from app.analysis.capability.adapter import DictCatalogAdapter
from app.analysis.capability.model import (
    S_AVAILABLE,
    S_BLOCKED,
    S_RESERVE,
    S_UNRESOLVED,
    STRAT_COUNT_DISTINCT,
    STRAT_NONE,
    STRAT_PRE_AGG,
    STRAT_SEMI_ADDITIVE,
)
from app.analysis.capability.resolver import resolve
from app.analysis.contracts import validate_interpretation

_SNAPSHOT_PATH = Path(__file__).resolve().parent / "eval_snapshots.json"
_FANOUT_CARDS = {"one_to_many", "many_to_many"}

# Codes de VIOLATION éliminatoires (sécurité analytique).
V_FANOUT_IGNORED = "fanout_ignored"
V_NON_ADDITIVE_SUM = "non_additive_sum"
V_INVENTED_RELATION = "invented_relation"
V_INVENTED_GRAIN = "invented_grain"
V_COUNT_UNDER_FANOUT = "count_incorrect_under_fanout"
V_ACCESS_BYPASSED = "access_bypassed"
V_UNRESOLVED_TO_AVAILABLE = "unresolved_silently_available"

DIMENSIONS = ("status", "strategy", "fanout", "key_state")


# --- corpus -----------------------------------------------------------------
@dataclass(frozen=True)
class ResolverCase:
    id: str
    domain: str
    catalog: dict
    goal: dict
    safety: str                              # dimension de sécurité observée
    expect_status: str
    expect_strategy: str
    expect_fanout: bool
    expect_key_state: str                    # état de l'exigence décisive
    note: str = ""


def _goal(gtype, *, entity="concept:e", metrics=(), dims=()):
    g = {"id": "g1", "priority": 1, "type": gtype, "intent_text": "x", "entity_ref": entity}
    if metrics:
        g["metrics"] = [{"ref": m} for m in metrics]
    if dims:
        g["dimensions"] = [{"ref": d} for d in dims]
    return g


# Catalogues partagés (déclaratifs, domain-agnostic — les noms ne servent qu'aux fixtures).
def _retail():
    return {
        "entities": [
            {"ref": "concept:order", "grain_keys": ["order_id"], "physical": "orders"},
            {"ref": "concept:customer", "grain_keys": ["customer_id"], "physical": "customers"},
            {"ref": "concept:order_item", "grain_keys": ["order_item_id"], "physical": "order_items"},
            {"ref": "concept:tag", "grain_keys": ["tag_id"], "physical": "tags"}],
        "measures": [{"ref": "metric:net_revenue", "home_entity": "concept:order", "additivity": "full"}],
        "dimensions": [
            {"ref": "dimension:region", "home_entity": "concept:customer"},
            {"ref": "dimension:product", "home_entity": "concept:order_item"},
            {"ref": "dimension:tag", "home_entity": "concept:tag"}],
        "relations": [
            {"id": 1, "from_entity": "concept:order", "to_entity": "concept:customer", "cardinality": "n-1",
             "status": "validated", "from_key": "orders.customer_id", "to_key": "customers.id", "coverage": 1.0},
            {"id": 2, "from_entity": "concept:order", "to_entity": "concept:order_item", "cardinality": "1-n",
             "status": "validated", "from_key": "orders.id", "to_key": "order_items.order_id", "coverage": 1.0},
            {"id": 3, "from_entity": "concept:order", "to_entity": "concept:tag", "cardinality": "n-n",
             "status": "validated", "from_key": "orders.id", "to_key": "tags.id"}],
    }


def _retail_inferred():
    r = _retail()
    # dimension atteignable seulement via une relation INFÉRÉE (non validée)
    r["dimensions"].append({"ref": "dimension:supplier", "home_entity": "concept:supplier"})
    r["entities"].append({"ref": "concept:supplier", "grain_keys": ["supplier_id"]})
    r["relations"].append({"id": 9, "from_entity": "concept:order", "to_entity": "concept:supplier",
                           "cardinality": "n-1", "status": "candidate", "origin": "inferred",
                           "from_key": "orders.supplier_id", "to_key": "suppliers.id"})
    return r


def _saas():
    return {
        "entities": [
            {"ref": "concept:e", "grain_keys": ["sub_id"], "physical": "subscriptions"},
            {"ref": "concept:plan", "grain_keys": ["plan_id"], "physical": "plans"},
            {"ref": "concept:line", "grain_keys": ["line_id"], "physical": "invoice_lines"}],
        "measures": [
            {"ref": "metric:mrr", "home_entity": "concept:e", "additivity": "full"},
            {"ref": "metric:balance", "home_entity": "concept:e", "additivity": "semi",
             "non_additive_dims": ["dimension:month"]},
            {"ref": "metric:conversion_rate", "home_entity": "concept:e", "additivity": "non"}],
        "dimensions": [
            {"ref": "dimension:plan", "home_entity": "concept:plan"},
            {"ref": "dimension:line", "home_entity": "concept:line"},
            {"ref": "dimension:month", "home_entity": "concept:e"}],
        "relations": [
            {"id": 1, "from_entity": "concept:e", "to_entity": "concept:plan", "cardinality": "n-1",
             "status": "validated", "from_key": "subscriptions.plan_id", "to_key": "plans.id"},
            {"id": 2, "from_entity": "concept:e", "to_entity": "concept:line", "cardinality": "1-n",
             "status": "validated", "from_key": "subscriptions.id", "to_key": "invoice_lines.sub_id"}],
    }


def _solo():
    return {"entities": [{"ref": "concept:e", "grain_keys": ["id"], "physical": "t"}],
            "measures": [{"ref": "metric:amount", "home_entity": "concept:e", "additivity": "full"}],
            "dimensions": [], "relations": []}


def _with(spec, **over):
    s = json.loads(json.dumps(spec))          # copie profonde
    s.update(over)
    return s


CASES: list[ResolverCase] = [
    # ---------- Retail ----------
    ResolverCase("r_rev_by_region", "retail", _retail(),
                 _goal("aggregate", entity="concept:order", metrics=["metric:net_revenue"], dims=["dimension:region"]),
                 "no_fanout", "SUPPORTED", STRAT_NONE, False, S_AVAILABLE, "n-1 : pas de fanout"),
    ResolverCase("r_rev_by_product", "retail", _retail(),
                 _goal("aggregate", entity="concept:order", metrics=["metric:net_revenue"], dims=["dimension:product"]),
                 "fanout", "SUPPORTED", STRAT_PRE_AGG, True, S_AVAILABLE, "1-n : pré-agg sûre"),
    ResolverCase("r_rev_by_tag", "retail", _retail(),
                 _goal("aggregate", entity="concept:order", metrics=["metric:net_revenue"], dims=["dimension:tag"]),
                 "fanout", "SUPPORTED", STRAT_PRE_AGG, True, S_AVAILABLE, "n-n : pré-agg"),
    ResolverCase("r_count_under_fanout", "retail", _retail(),
                 _goal("count", entity="concept:order", dims=["dimension:product"]),
                 "count_fanout", "SUPPORTED", STRAT_COUNT_DISTINCT, True, S_AVAILABLE, "count sous fanout"),
    ResolverCase("r_missing_measure", "retail", _retail(),
                 _goal("aggregate", entity="concept:order", metrics=["metric:absent"]),
                 "unresolved", "UNSUPPORTED", STRAT_NONE, False, S_UNRESOLVED, "mesure absente"),
    ResolverCase("r_inferred_relation", "retail", _retail_inferred(),
                 _goal("aggregate", entity="concept:order", metrics=["metric:net_revenue"], dims=["dimension:supplier"]),
                 "invented", "UNSUPPORTED", STRAT_NONE, False, S_UNRESOLVED, "relation inférée non validée"),
    ResolverCase("r_hidden_measure", "retail", _with(_retail(), access={"hidden": ["metric:net_revenue"]}),
                 _goal("aggregate", entity="concept:order", metrics=["metric:net_revenue"], dims=["dimension:region"]),
                 "access", "UNSUPPORTED", STRAT_NONE, False, S_BLOCKED, "mesure masquée (accès)"),
    # ---------- SaaS ----------
    ResolverCase("s_mrr_by_plan", "saas", _saas(),
                 _goal("aggregate", entity="concept:e", metrics=["metric:mrr"], dims=["dimension:plan"]),
                 "no_fanout", "SUPPORTED", STRAT_NONE, False, S_AVAILABLE, "n-1"),
    ResolverCase("s_mrr_by_line", "saas", _saas(),
                 _goal("aggregate", entity="concept:e", metrics=["metric:mrr"], dims=["dimension:line"]),
                 "fanout", "SUPPORTED", STRAT_PRE_AGG, True, S_AVAILABLE, "1-n"),
    ResolverCase("s_balance_over_month", "saas", _saas(),
                 _goal("aggregate", entity="concept:e", metrics=["metric:balance"], dims=["dimension:month"]),
                 "semi_additive", "PARTIAL", STRAT_SEMI_ADDITIVE, False, S_RESERVE, "semi-additif sur axe non-additif"),
    ResolverCase("s_rate_sum", "saas", _saas(),
                 _goal("aggregate", entity="concept:e", metrics=["metric:conversion_rate"], dims=["dimension:plan"]),
                 "non_additive", "UNSUPPORTED", STRAT_NONE, False, S_UNRESOLVED, "ratio non sommable"),
    ResolverCase("s_stale_mrr", "saas", _with(_saas(), freshness={"metric:mrr": {"stale": True}}),
                 _goal("aggregate", entity="concept:e", metrics=["metric:mrr"]),
                 "quality_reserve", "PARTIAL", STRAT_NONE, False, S_RESERVE, "stale dans tolérance"),
    ResolverCase("s_quality_hardstop", "saas",
                 _with(_saas(), quality={"metric:mrr": 0.1}, policy={"quality_hard_stop": 0.5}),
                 _goal("aggregate", entity="concept:e", metrics=["metric:mrr"]),
                 "quality_blocked", "UNSUPPORTED", STRAT_NONE, False, S_BLOCKED, "hard-stop qualité"),
    ResolverCase("s_source_down", "saas", _with(_saas(), access={"source_reachable": False}),
                 _goal("aggregate", entity="concept:e", metrics=["metric:mrr"]),
                 "access", "UNSUPPORTED", STRAT_NONE, False, S_BLOCKED, "source injoignable"),
    ResolverCase("s_unknown_grain_fanout", "saas",
                 _with(_saas(), measures=_saas()["measures"] + [{"ref": "metric:mystery", "home_entity": ""}]),
                 _goal("aggregate", entity="concept:e", metrics=["metric:mystery"], dims=["dimension:line"]),
                 "grain_unknown", "UNSUPPORTED", STRAT_NONE, True, S_UNRESOLVED, "grain inconnu sous fanout"),
    # ---------- Solo ----------
    ResolverCase("solo_count", "solo", _solo(),
                 _goal("count", entity="concept:e"),
                 "no_fanout", "SUPPORTED", STRAT_NONE, False, S_AVAILABLE, "base solo, count"),
    ResolverCase("solo_sum", "solo", _solo(),
                 _goal("aggregate", entity="concept:e", metrics=["metric:amount"]),
                 "no_fanout", "SUPPORTED", STRAT_NONE, False, S_AVAILABLE, "base solo, somme"),
]


# --- signature normalisée ---------------------------------------------------
def signature(resolution, resolved_plan) -> dict:
    item = resolved_plan["resolution"][0]
    grain = item.get("grain") or {}
    return {
        "status": item["status"],
        "strategy": grain.get("aggregation_strategy", STRAT_NONE),
        "creates_row_multiplication": bool(grain.get("creates_row_multiplication", False)),
        "requires_pre_aggregation": bool(grain.get("requires_pre_aggregation", False)),
        "traversal": grain.get("traversal"),
        "metric_additivity": grain.get("metric_additivity"),
        "join_path": [{"cardinality": s["cardinality"], "fanout_risk": s["fanout_risk"],
                       "rel": s["validated_relation_id"]} for s in item.get("join_path", [])],
        "requirement_states": sorted(f"{r.kind}:{r.ref}={r.state}"
                                     for r in resolution.goals[0].requirements),
        "covers_question": resolved_plan["coherence"]["covers_question"],
    }


def _key_state(resolution) -> str:
    """État de l'exigence décisive : le pire (blocked/unresolved > reserve > available)."""
    rank = {S_AVAILABLE: 0, S_RESERVE: 1, S_UNRESOLVED: 2, S_BLOCKED: 3}
    reqs = resolution.goals[0].requirements
    return max((r.state for r in reqs), key=lambda s: rank.get(s, 0), default=S_AVAILABLE)


# --- détection de VIOLATIONS de sécurité (éliminatoires) --------------------
def _validated_ids(catalog: dict) -> set[int]:
    ids = set()
    for r in catalog.get("relations", []):
        if r.get("status") == "validated" or r.get("origin") == "constraint":
            ids.add(int(r["id"]))
    return ids


def detect_violations(case: ResolverCase, resolution, plan) -> list[str]:
    item = plan["resolution"][0]
    grain = item.get("grain") or {}
    steps = item.get("join_path", [])
    v: list[str] = []

    # Invariants UNIVERSELS (indépendants des attentes).
    if any(s["cardinality"] in _FANOUT_CARDS for s in steps) and not grain.get("creates_row_multiplication"):
        v.append(V_FANOUT_IGNORED)
    if grain.get("creates_row_multiplication") and not grain.get("requires_pre_aggregation"):
        v.append(V_FANOUT_IGNORED)
    valid_ids = _validated_ids(case.catalog)
    if any(int(s["validated_relation_id"]) not in valid_ids for s in steps):
        v.append(V_INVENTED_RELATION)
    ents = {e["ref"] for e in case.catalog.get("entities", [])}
    concepts = [c for c in item.get("concepts", []) if c.startswith("concept:")]
    if any(c not in ents for c in concepts):
        v.append(V_INVENTED_GRAIN)

    # Sécurité liée à la NATURE du cas.
    status = item["status"]
    strat = grain.get("aggregation_strategy")
    if case.safety == "non_additive" and status not in ("UNSUPPORTED", "NEEDS_CLARIFICATION"):
        v.append(V_NON_ADDITIVE_SUM)
    if case.safety == "grain_unknown" and status != "UNSUPPORTED":
        v.append(V_NON_ADDITIVE_SUM if strat == STRAT_PRE_AGG else V_FANOUT_IGNORED)
    if case.safety == "count_fanout" and grain.get("creates_row_multiplication") and strat != STRAT_COUNT_DISTINCT:
        v.append(V_COUNT_UNDER_FANOUT)
    if case.safety == "access" and status not in ("UNSUPPORTED",):
        v.append(V_ACCESS_BYPASSED)
    if case.safety in ("unresolved", "invented") and status not in ("UNSUPPORTED", "NEEDS_CLARIFICATION"):
        v.append(V_UNRESOLVED_TO_AVAILABLE)
    if case.safety == "invented" and steps:            # relation inférée → aucun chemin ne doit être émis
        v.append(V_INVENTED_RELATION)
    return sorted(set(v))


# --- exécution du benchmark -------------------------------------------------
@dataclass
class CaseResult:
    id: str
    domain: str
    safety: str
    produced: dict = field(default_factory=dict)         # 4 dimensions (status/strategy/fanout/key_state)
    expected: dict = field(default_factory=dict)
    signature: dict = field(default_factory=dict)        # signature normalisée complète
    matches: dict = field(default_factory=dict)
    violations: list = field(default_factory=list)
    snapshot_state: str = "n/a"          # match | changed | new


def run_eval(*, snapshots: dict | None = None) -> dict:
    snaps = snapshots if snapshots is not None else _load_snapshots()
    results: list[CaseResult] = []
    for case in CASES:
        ctx = DictCatalogAdapter().to_context(case.catalog)
        interp = validate_interpretation(
            {"plan_schema_version": "1.0", "unresolved_terms": [], "goals": [case.goal]})
        resolution, plan = resolve(interp, ctx)
        sig = signature(resolution, plan)
        item = plan["resolution"][0]
        grain = item.get("grain") or {}
        # fanout = DÉTECTION par le resolver (rich resolution), pas le plan : un goal
        # unsupported n'émet pas de grain mais a bien détecté la multiplication.
        grain_req = next((r for r in resolution.goals[0].requirements if r.kind == "grain"), None)
        fanout_detected = bool(grain_req.creates_row_multiplication) if grain_req else False
        strategy = grain.get("aggregation_strategy") or (grain_req.strategy if grain_req else STRAT_NONE)
        produced = {"status": item["status"], "strategy": strategy,
                    "fanout": fanout_detected, "key_state": _key_state(resolution)}
        expected = {"status": case.expect_status, "strategy": case.expect_strategy,
                    "fanout": case.expect_fanout, "key_state": case.expect_key_state}
        matches = {d: produced[d] == expected[d] for d in DIMENSIONS}
        snap_state = ("new" if case.id not in snaps
                      else "match" if snaps[case.id] == sig else "changed")
        results.append(CaseResult(case.id, case.domain, case.safety, produced, expected, sig,
                                  matches, detect_violations(case, resolution, plan), snap_state))

    dim_rates = {d: round(sum(r.matches[d] for r in results) / len(results), 4) for d in DIMENSIONS}
    violations = [(r.id, v) for r in results for v in r.violations]
    return {
        "n_cases": len(results),
        "domains": sorted({r.domain for r in results}),
        "dimension_rates": dim_rates,
        "violations": violations,
        "eliminated": bool(violations),
        "snapshot": {"changed": [r.id for r in results if r.snapshot_state == "changed"],
                     "new": [r.id for r in results if r.snapshot_state == "new"]},
        "results": results,
        "signatures": {r.id: r.signature for r in results},
    }


def _load_snapshots() -> dict:
    if _SNAPSHOT_PATH.is_file():
        return json.loads(_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    return {}


def write_snapshots() -> dict:
    """(Re)génère les snapshots de référence à partir du comportement courant."""
    sigs = {}
    for case in CASES:
        ctx = DictCatalogAdapter().to_context(case.catalog)
        interp = validate_interpretation(
            {"plan_schema_version": "1.0", "unresolved_terms": [], "goals": [case.goal]})
        resolution, plan = resolve(interp, ctx)
        sigs[case.id] = signature(resolution, plan)
    _SNAPSHOT_PATH.write_text(json.dumps(sigs, ensure_ascii=False, indent=2, sort_keys=True),
                              encoding="utf-8")
    return sigs
