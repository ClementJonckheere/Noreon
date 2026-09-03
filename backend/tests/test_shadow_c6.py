"""Phase 2 — shadow C6 : câblage resolver réel + télémétrie 3 étages + sécurité.

Aucun LLM, aucun accès réseau. Vérifie : projection d'exécution legacy depuis le
SQL, sécurité analytique RESTRICTIVE, intégration C6 (3 étages persistés), et le
contexte réel construit depuis un snapshot.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.analysis.capability.adapter import DictCatalogAdapter
from app.analysis.contracts import INTERPRETATION_SCHEMA_VERSION, validate_interpretation
from app.analysis.shadow import safety as SF
from app.analysis.shadow import service as S
from app.analysis.shadow.legacy_projection import project_legacy_execution


def _interpretation(goal_type, entity_ref, *, metrics=(), dimensions=()):
    goal = {
        "id": "g1", "priority": 1, "type": goal_type, "intent_text": "x",
        "entity_ref": entity_ref, "entity_label": None,
        "metrics": [
            {"ref": ref, "of_ref": None, "aggregation": "sum"} for ref in metrics
        ],
        "dimensions": [{"ref": ref} for ref in dimensions],
        "filters": [], "method": None, "depends_on": [], "ambiguities": [],
        "binning_requested": False, "sort": [], "limit": None, "temporal": None,
    }
    return validate_interpretation({
        "plan_schema_version": INTERPRETATION_SCHEMA_VERSION,
        "unresolved_terms": [], "goals": [goal],
    })


# --- projection d'exécution legacy ------------------------------------------
def test_legacy_projection_from_real_sql():
    resp = SimpleNamespace(
        sql="SELECT c.region, SUM(o.amount) FROM orders o JOIN customers c "
            "ON o.customer_id=c.id GROUP BY c.region",
        tables_used=["orders", "customers"], columns_used=["amount", "region"], status="answered")
    p = project_legacy_execution(resp)
    assert p["sql_present"] and "sum" in p["aggregations"] and p["joins"] == 1
    assert p["group_by"] and not p["count_star"] and not p["pre_aggregated"]


def test_legacy_projection_detects_count_distinct_and_preagg():
    resp = SimpleNamespace(
        sql="SELECT COUNT(DISTINCT o.id) FROM (SELECT id FROM orders GROUP BY id) o", status="answered")
    p = project_legacy_execution(resp)
    assert p["count_distinct"] and p["pre_aggregated"]


# --- sécurité analytique (restrictive) --------------------------------------
def _fanout_resolved():
    ctx = DictCatalogAdapter().to_context({
        "entities": [{"ref": "concept:o", "grain_keys": ["oid"], "physical": "o"},
                     {"ref": "concept:i", "grain_keys": ["iid"], "physical": "i"}],
        "measures": [{"ref": "metric:rev", "home_entity": "concept:o", "additivity": "full",
                      "physical": "o.rev"}],
        "dimensions": [{"ref": "dimension:p", "home_entity": "concept:i", "physical": "i.p"}],
        "relations": [{"id": 1, "from_entity": "concept:o", "to_entity": "concept:i", "cardinality": "1-n",
                       "status": "validated", "from_key": "o.id", "to_key": "i.oid"}]})
    from app.analysis.capability.resolver import resolve
    interp = _interpretation(
        "aggregate", "concept:o", metrics=["metric:rev"], dimensions=["dimension:p"],
    )
    _, plan = resolve(interp, ctx)
    return plan


def test_safety_llm_safer_on_unprotected_legacy_sum():
    plan = _fanout_resolved()   # C6 : fanout + pre_aggregation
    legacy = {"sql_present": True, "aggregations": ["sum"], "joins": 1, "pre_aggregated": False,
              "count_star": False, "count_distinct": False}
    verdict, detail = SF.analytical_safety_delta(plan, legacy)
    assert verdict == SF.LLM_SAFER and "pre_aggregation" in detail["why"]


def test_safety_llm_safer_on_count_star_vs_count_distinct():
    ctx = DictCatalogAdapter().to_context({
        "entities": [{"ref": "concept:o", "grain_keys": ["oid"], "physical": "o"},
                     {"ref": "concept:i", "grain_keys": ["iid"], "physical": "i"}],
        "measures": [], "dimensions": [{"ref": "dimension:p", "home_entity": "concept:i",
                                          "physical": "i.p"}],
        "relations": [{"id": 1, "from_entity": "concept:o", "to_entity": "concept:i", "cardinality": "1-n",
                       "status": "validated", "from_key": "o.id", "to_key": "i.oid"}]})
    from app.analysis.capability.resolver import resolve
    interp = _interpretation("count", "concept:o", dimensions=["dimension:p"])
    _, plan = resolve(interp, ctx)                # C6 : count_distinct
    legacy = {"sql_present": True, "aggregations": ["count"], "joins": 1, "pre_aggregated": False,
              "count_star": True, "count_distinct": False}
    verdict, _ = SF.analytical_safety_delta(plan, legacy)
    assert verdict == SF.LLM_SAFER


def test_safety_not_comparable_without_sql():
    plan = _fanout_resolved()
    assert SF.analytical_safety_delta(plan, {"sql_present": False})[0] == SF.NOT_COMPARABLE


def test_safety_not_comparable_when_c6_unsupported():
    # C6 n'a pas produit de plan exécutable → pas de verdict de sécurité
    assert SF.analytical_safety_delta({"resolution": [{"status": "UNSUPPORTED"}]},
                                      {"sql_present": True, "aggregations": ["sum"], "joins": 1})[0] == SF.NOT_COMPARABLE


def test_safety_same_when_no_fanout():
    ctx = DictCatalogAdapter().to_context({
        "entities": [{"ref": "concept:o", "grain_keys": ["oid"], "physical": "o"}],
        "measures": [{"ref": "metric:rev", "home_entity": "concept:o", "additivity": "full",
                      "physical": "o.rev"}],
        "dimensions": [], "relations": []})
    from app.analysis.capability.resolver import resolve
    interp = _interpretation("aggregate", "concept:o", metrics=["metric:rev"])
    _, plan = resolve(interp, ctx)
    legacy = {"sql_present": True, "aggregations": ["sum"], "joins": 0, "pre_aggregated": False,
              "count_star": False, "count_distinct": False}
    assert SF.analytical_safety_delta(plan, legacy)[0] == SF.SAME_SAFETY


# --- intégration : run_shadow_evaluation avec contexte C6 -------------------
class _FakeSession:
    def __init__(self): self.added, self.commits = [], 0
    def add(self, r): self.added.append(r)
    def commit(self): self.commits += 1


def test_run_shadow_evaluation_persists_three_stages_and_safety():
    ctx = DictCatalogAdapter().to_context({
        "entities": [{"ref": "concept:o", "grain_keys": ["oid"], "physical": "o"},
                     {"ref": "concept:i", "grain_keys": ["iid"], "physical": "i"}],
        "measures": [{"ref": "metric:rev", "home_entity": "concept:o", "additivity": "full",
                      "physical": "o.rev"}],
        "dimensions": [{"ref": "dimension:p", "home_entity": "concept:i", "physical": "i.p"}],
        "relations": [{"id": 1, "from_entity": "concept:o", "to_entity": "concept:i", "cardinality": "1-n",
                       "status": "validated", "from_key": "o.id", "to_key": "i.oid"}]})
    interp = _interpretation(
        "aggregate", "concept:o", metrics=["metric:rev"], dimensions=["dimension:p"],
    )
    env = {"tenant_id": 1, "connection_id": 7, "request_id": "r1", "question_hash": "h",
           "safe_question": "revenu par produit", "planner_mode": "shadow", "sample_rate": 1.0,
           "fallback_view": {"status": "answered"}, "fallback_status": "answered",
           "legacy_execution": {"sql_present": True, "aggregations": ["sum"], "joins": 1,
                                "pre_aggregated": False, "count_star": False, "count_distinct": False}}
    sess = _FakeSession()
    row = S.run_shadow_evaluation(env, session=sess, plan_fn=lambda m, q, c: S.ShadowPlanResult(interp=interp, status="ok"),
                                  catalog=object(), context=ctx, main_model="M", simple_model="S")
    assert row.resolved_plan_json and row.capability_resolution_json          # étages 2
    assert row.legacy_execution_projection_json                              # étage 3
    assert row.capability_states_json and sum(row.capability_states_json.values()) >= 1
    assert row.analytical_safety == SF.LLM_SAFER
    assert row.analytical_safety_version == "1.0"
    assert row.review_status == "sampled_for_review"                         # llm_safer → revue prioritaire (#6)


# --- contexte réel depuis un snapshot ---------------------------------------
def test_db_context_builds_consistent_refs(monkeypatch):
    cols_orders = [SimpleNamespace(name="id", data_type="integer", is_primary_key=True),
                   SimpleNamespace(name="amount", data_type="numeric", is_primary_key=False),
                   SimpleNamespace(name="city", data_type="varchar", is_primary_key=False)]
    snap = SimpleNamespace(tables=[SimpleNamespace(table_name="orders", columns=cols_orders)])
    monkeypatch.setattr("app.services.schema_context.current_snapshot", lambda s, c: snap)
    from app.analysis.capability import db_context
    monkeypatch.setattr(db_context, "_load_relations", lambda *a: ([], []))
    catalog, context = db_context.build_catalog_and_context(object(), 7)
    assert "concept:orders" in context.entities
    assert "metric:orders_amount" not in context.measures
    assert context.column_roles["orders.amount"] == ("attribute",)
    assert "dimension:orders_city" not in context.dimensions
    assert context.column_roles["orders.city"] == ("attribute",)
    # cohérence catalogue ↔ contexte (mêmes refs)
    cat_refs = {c["entity_ref"] for c in catalog.concepts}
    assert cat_refs == set(context.entities)
    assert context.entities["concept:orders"].grain_keys == ("id",)   # PK → grain
