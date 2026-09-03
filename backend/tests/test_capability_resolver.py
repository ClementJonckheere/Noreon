"""Phase 2 — C6 : états/causes du CapabilityResolver + multi-domaines + domain-agnostic.

`available` (capability/qualité) est distinct de `access`. `blocked` (accès OU
hard-stop qualité) ne se confond jamais avec `unresolved` (manque de structure).
Le même resolver marche pour Retail, SaaS et une base solo — aucun nom métier.
"""
from __future__ import annotations

import pathlib

from app.analysis.capability.adapter import DictCatalogAdapter
from app.analysis.capability.model import (
    CAUSE_ACCESS,
    CAUSE_CAPABILITY,
    CAUSE_QUALITY,
    S_AVAILABLE,
    S_BLOCKED,
    S_RESERVE,
    S_UNRESOLVED,
)
from app.analysis.capability.resolver import resolve
from app.analysis.contracts import INTERPRETATION_SCHEMA_VERSION, validate_interpretation, validate_resolved


def _goal(gtype, metrics=(), dims=(), entity="concept:e"):
    g = {
        "id": "g1", "priority": 1, "type": gtype, "intent_text": "x",
        "entity_ref": entity, "entity_label": None,
        "metrics": [{"ref": m, "of_ref": None, "aggregation": "sum"} for m in metrics],
        "dimensions": [{"ref": d} for d in dims], "filters": [], "method": None,
        "depends_on": [], "ambiguities": [], "binning_requested": False,
        "sort": [], "limit": None, "temporal": None,
    }
    return validate_interpretation({
        "plan_schema_version": INTERPRETATION_SCHEMA_VERSION,
        "unresolved_terms": [], "goals": [g],
    })


def _req(res, kind):
    return [r for r in res.goals[0].requirements if r.kind == kind]


# === Multi-domaines (même resolver, zéro nom métier) ========================
def test_retail_saas_solo_all_resolve_and_emit_only_catalog_refs():
    domains = {
        "retail": {"entities": [{"ref": "concept:e", "grain_keys": ["id"], "physical": "e"}],
                   "measures": [{"ref": "metric:m", "home_entity": "concept:e",
                                 "physical": "e.m"}], "dimensions": [], "relations": []},
        "saas": {"entities": [{"ref": "concept:e", "grain_keys": ["id"], "physical": "e"}],
                 "measures": [{"ref": "metric:m", "home_entity": "concept:e",
                               "physical": "e.m"}], "dimensions": [], "relations": []},
        "solo": {"entities": [{"ref": "concept:e", "grain_keys": ["id"], "physical": "e"}],
                 "measures": [], "dimensions": [], "relations": []},
    }
    for name, spec in domains.items():
        ctx = DictCatalogAdapter().to_context(spec)
        goal = _goal("aggregate" if spec["measures"] else "count",
                     ["metric:m"] if spec["measures"] else [])
        res, plan = resolve(goal, ctx)
        assert plan["resolution"][0]["status"] == "SUPPORTED", name
        validate_resolved(plan)


def test_capability_package_has_no_business_literals():
    # Règle n°1 : le MOTEUR est domain-agnostic. `resolver_eval.py` est un corpus
    # de fixtures (catalogues de démo) — exclu, comme demo_retail.py pour l'arbitrage.
    forbidden = ("magasin", "boutique", "facture", "invoice", "abonnement",
                 "subscription", "chiffre_affaires")
    pkg = pathlib.Path(__file__).resolve().parents[1] / "app" / "analysis" / "capability"
    for py in pkg.glob("*.py"):
        if py.name == "resolver_eval.py":
            continue
        text = py.read_text(encoding="utf-8").lower()
        for word in forbidden:
            assert word not in text, f"{word} dans {py.name}"


# === Capability : rien n'est inventé ========================================
def test_missing_measure_is_unresolved_not_invented():
    ctx = DictCatalogAdapter().to_context(
        {"entities": [{"ref": "concept:e", "grain_keys": ["id"], "physical": "e"}],
         "measures": [], "dimensions": [], "relations": []})
    res, plan = resolve(_goal("aggregate", ["metric:absent"]), ctx)
    m = _req(res, "measure")[0]
    assert m.state == S_UNRESOLVED and m.cause_class == CAUSE_CAPABILITY
    assert plan["resolution"][0]["status"] == "UNSUPPORTED"


def test_inferred_fk_not_usable_but_constraint_fk_is_system_validated():
    ent = [{"ref": "concept:e", "grain_keys": ["id"], "physical": "e"},
           {"ref": "concept:d", "grain_keys": ["id"], "physical": "d"}]
    meas = [{"ref": "metric:m", "home_entity": "concept:e", "physical": "e.m"}]
    dims = [{"ref": "dimension:x", "home_entity": "concept:d", "physical": "d.x"}]
    rel = {"id": 1, "from_entity": "concept:e", "to_entity": "concept:d", "cardinality": "n-1",
           "from_key": "e.d_id", "to_key": "d.id"}

    # inférée (origin=inferred, non validée) → aucun chemin → unresolved
    ctx_inf = DictCatalogAdapter().to_context({"entities": ent, "measures": meas, "dimensions": dims,
                                               "relations": [{**rel, "origin": "inferred", "status": "candidate"}]})
    res, _ = resolve(_goal("aggregate", ["metric:m"], ["dimension:x"]), ctx_inf)
    rels = _req(res, "relation")
    assert rels and rels[0].reason_code == "no_validated_relation"

    # FK physique confirmée (origin=constraint) → system-validated → résout (#6)
    ctx_fk = DictCatalogAdapter().to_context({"entities": ent, "measures": meas, "dimensions": dims,
                                              "relations": [{**rel, "origin": "constraint", "status": "candidate"}]})
    _, plan = resolve(_goal("aggregate", ["metric:m"], ["dimension:x"]), ctx_fk)
    assert plan["resolution"][0]["status"] == "SUPPORTED"


# === Qualité : reserve vs hard-stop, jamais unresolved ======================
def _quality_ctx(**over):
    spec = {"entities": [{"ref": "concept:e", "grain_keys": ["id"], "physical": "e"}],
            "measures": [{"ref": "metric:m", "home_entity": "concept:e", "physical": "e.m"}],
            "dimensions": [], "relations": []}
    spec.update(over)
    return DictCatalogAdapter().to_context(spec)


def test_stale_within_tolerance_is_reserve_quality():
    ctx = _quality_ctx(freshness={"metric:m": {"stale": True}}, policy={"staleness_mode": "reserve"})
    res, plan = resolve(_goal("aggregate", ["metric:m"]), ctx)
    m = _req(res, "measure")[0]
    assert m.state == S_RESERVE and m.cause_class == CAUSE_QUALITY
    assert plan["resolution"][0]["status"] == "PARTIAL"


def test_quality_hard_stop_is_blocked_not_unresolved():
    ctx = _quality_ctx(quality={"metric:m": 0.1}, policy={"quality_hard_stop": 0.5})
    res, plan = resolve(_goal("aggregate", ["metric:m"]), ctx)
    m = _req(res, "measure")[0]
    assert m.state == S_BLOCKED and m.cause_class == CAUSE_QUALITY   # distinct d'un manque
    assert m.reason_code == "quality_hard_stop"


def test_strict_staleness_is_hard_stop():
    ctx = _quality_ctx(freshness={"metric:m": {"stale": True}}, policy={"staleness_mode": "strict"})
    res, _ = resolve(_goal("aggregate", ["metric:m"]), ctx)
    assert _req(res, "measure")[0].state == S_BLOCKED


# === Accès : orthogonal à la capability =====================================
def test_hidden_ref_is_blocked_access_while_capability_available():
    ctx = _quality_ctx(access={"hidden": {"metric:m"}})
    res, plan = resolve(_goal("aggregate", ["metric:m"]), ctx)
    m = _req(res, "measure")[0]
    assert m.capability_state == S_AVAILABLE          # la capability EST disponible…
    assert m.access_state == "blocked" and m.state == S_BLOCKED   # …mais l'accès bloque (#5)
    assert m.cause_class == CAUSE_ACCESS and m.reason_code == "not_permitted"


def test_source_unreachable_is_blocked_access():
    ctx = _quality_ctx(access={"source_reachable": False})
    res, _ = resolve(_goal("aggregate", ["metric:m"]), ctx)
    m = _req(res, "measure")[0]
    assert m.state == S_BLOCKED and m.reason_code == "source_unreachable"


# === Chemins ambigus → clarification ========================================
def test_ambiguous_join_path_needs_clarification():
    ent = [{"ref": "concept:e", "grain_keys": ["id"], "physical": "e"},
           {"ref": "concept:d", "grain_keys": ["id"], "physical": "d"},
           {"ref": "concept:mid", "grain_keys": ["id"], "physical": "mid"}]
    meas = [{"ref": "metric:m", "home_entity": "concept:e", "physical": "e.m"}]
    dims = [{"ref": "dimension:x", "home_entity": "concept:d", "physical": "d.x"}]
    # deux chemins e→d aussi sûrs (n-1) et aussi courts (1 étape) : direct et via un autre id
    rels = [
        {"id": 1, "from_entity": "concept:e", "to_entity": "concept:d", "cardinality": "n-1",
         "status": "validated", "from_key": "e.d_id", "to_key": "d.id"},
        {"id": 2, "from_entity": "concept:e", "to_entity": "concept:d", "cardinality": "n-1",
         "status": "validated", "from_key": "e.d_id2", "to_key": "d.id"}]
    ctx = DictCatalogAdapter().to_context({"entities": ent, "measures": meas, "dimensions": dims, "relations": rels})
    _, plan = resolve(_goal("aggregate", ["metric:m"], ["dimension:x"]), ctx)
    assert plan["resolution"][0]["status"] == "NEEDS_CLARIFICATION"
    assert "clarification" in plan["resolution"][0]
