"""Phase 2 — C6 : tests ANTI-FANOUT (prioritaires).

Ces cas produiraient des résultats PLAUSIBLES MAIS MATHÉMATIQUEMENT FAUX (double
comptage) — bien plus dangereux qu'un ContractError. Une jointure valide n'est
JAMAIS une garantie d'agrégation sûre.
"""
from __future__ import annotations

from app.analysis.capability.adapter import DictCatalogAdapter
from app.analysis.capability.model import (
    S_AVAILABLE,
    S_RESERVE,
    S_UNRESOLVED,
    STRAT_COUNT_DISTINCT,
    STRAT_NONE,
    STRAT_PRE_AGG,
    STRAT_SEMI_ADDITIVE,
)
from app.analysis.capability.resolver import resolve
from app.analysis.contracts import validate_interpretation

_BASE_ENTITIES = [
    {"ref": "concept:order", "grain_keys": ["order_id"], "physical": "orders"},
    {"ref": "concept:customer", "grain_keys": ["customer_id"], "physical": "customers"},
    {"ref": "concept:order_item", "grain_keys": ["order_item_id"], "physical": "order_items"},
    {"ref": "concept:tag", "grain_keys": ["tag_id"], "physical": "tags"},
]


def _ctx(measures, relations, dimensions, **extra):
    spec = {"entities": _BASE_ENTITIES, "measures": measures, "dimensions": dimensions,
            "relations": relations}
    spec.update(extra)
    return DictCatalogAdapter().to_context(spec)


def _goal(gtype, metrics=(), dims=(), entity="concept:order"):
    g = {"id": "g1", "priority": 1, "type": gtype, "intent_text": "x", "entity_ref": entity}
    if metrics:
        g["metrics"] = [{"ref": m} for m in metrics]
    if dims:
        g["dimensions"] = [{"ref": d} for d in dims]
    return validate_interpretation({"plan_schema_version": "1.0", "unresolved_terms": [], "goals": [g]})


_REV = [{"ref": "metric:net_revenue", "home_entity": "concept:order", "additivity": "full"}]
_REL_ITEM = {"id": 2, "from_entity": "concept:order", "to_entity": "concept:order_item",
             "cardinality": "1-n", "status": "validated", "from_key": "orders.id",
             "to_key": "order_items.order_id", "coverage": 1.0}
_REL_CUST = {"id": 1, "from_entity": "concept:order", "to_entity": "concept:customer",
             "cardinality": "n-1", "status": "validated", "from_key": "orders.customer_id",
             "to_key": "customers.id", "coverage": 1.0}
_DIM_PRODUCT = {"ref": "dimension:product", "home_entity": "concept:order_item"}
_DIM_REGION = {"ref": "dimension:region", "home_entity": "concept:customer"}


def _grain(plan):
    return plan["resolution"][0]["grain"]


def test_one_to_many_forces_pre_aggregation():
    ctx = _ctx(_REV, [_REL_ITEM], [_DIM_PRODUCT])
    _, plan = resolve(_goal("aggregate", ["metric:net_revenue"], ["dimension:product"]), ctx)
    g = _grain(plan)
    assert g["creates_row_multiplication"] and g["requires_pre_aggregation"]
    assert g["aggregation_strategy"] == STRAT_PRE_AGG
    assert plan["resolution"][0]["status"] == "SUPPORTED"       # sûr après pré-agg (#2)


def test_many_to_many_forces_pre_aggregation():
    rel_nn = {"id": 3, "from_entity": "concept:order", "to_entity": "concept:tag",
              "cardinality": "n-n", "status": "validated", "from_key": "orders.id", "to_key": "tags.id"}
    ctx = _ctx(_REV, [rel_nn], [{"ref": "dimension:tag", "home_entity": "concept:tag"}])
    _, plan = resolve(_goal("aggregate", ["metric:net_revenue"], ["dimension:tag"]), ctx)
    g = _grain(plan)
    assert g["creates_row_multiplication"] and g["aggregation_strategy"] == STRAT_PRE_AGG
    assert plan["resolution"][0]["join_path"][0]["cardinality"] == "many_to_many"


def test_many_to_one_has_no_fanout():
    ctx = _ctx(_REV, [_REL_CUST], [_DIM_REGION])
    _, plan = resolve(_goal("aggregate", ["metric:net_revenue"], ["dimension:region"]), ctx)
    g = _grain(plan)
    assert not g["creates_row_multiplication"] and g["aggregation_strategy"] == STRAT_NONE


def test_valid_join_is_not_a_safe_aggregation():
    """Le cœur : une relation VALIDÉE (1-n) n'autorise PAS un SUM direct."""
    ctx = _ctx(_REV, [_REL_ITEM], [_DIM_PRODUCT])
    _, plan = resolve(_goal("aggregate", ["metric:net_revenue"], ["dimension:product"]), ctx)
    # relation validée ET pourtant pré-agrégation imposée (contrat : pas de fanout sans pré-agg)
    assert plan["resolution"][0]["join_path"][0]["fanout_risk"] is True
    assert _grain(plan)["requires_pre_aggregation"] is True


def test_count_across_fanout_uses_count_distinct():
    ctx = _ctx([], [_REL_ITEM], [_DIM_PRODUCT])
    _, plan = resolve(_goal("count", [], ["dimension:product"]), ctx)
    assert _grain(plan)["aggregation_strategy"] == STRAT_COUNT_DISTINCT
    assert plan["resolution"][0]["status"] == "SUPPORTED"


def test_unknown_measure_grain_under_fanout_is_unresolved():
    # mesure sans home_entity connu → grain inconnu → jamais une somme fausse
    measures = [{"ref": "metric:mystery", "home_entity": "", "additivity": "full"}]
    ctx = _ctx(measures, [_REL_ITEM], [_DIM_PRODUCT])
    res, plan = resolve(_goal("aggregate", ["metric:mystery"], ["dimension:product"]), ctx)
    assert plan["resolution"][0]["status"] == "UNSUPPORTED"
    grain_req = [r for r in res.goals[0].requirements if r.kind == "grain"][0]
    assert grain_req.state == S_UNRESOLVED and grain_req.reason_code == "grain_unknown_under_fanout"


def test_non_additive_measure_is_unresolved():
    measures = [{"ref": "metric:conversion_rate", "home_entity": "concept:order", "additivity": "non"}]
    ctx = _ctx(measures, [_REL_CUST], [_DIM_REGION])
    res, plan = resolve(_goal("aggregate", ["metric:conversion_rate"], ["dimension:region"]), ctx)
    assert plan["resolution"][0]["status"] == "UNSUPPORTED"
    grain_req = [r for r in res.goals[0].requirements if r.kind == "grain"][0]
    assert grain_req.reason_code == "non_additive_measure"


def test_semi_additive_over_non_additive_axis_is_reserve():
    measures = [{"ref": "metric:balance", "home_entity": "concept:order", "additivity": "semi",
                 "non_additive_dims": ["dimension:month"]}]
    ctx = _ctx(measures, [], [{"ref": "dimension:month", "home_entity": "concept:order"}])
    res, plan = resolve(_goal("aggregate", ["metric:balance"], ["dimension:month"]), ctx)
    assert plan["resolution"][0]["status"] == "PARTIAL"
    grain_req = [r for r in res.goals[0].requirements if r.kind == "grain"][0]
    assert grain_req.state == S_RESERVE and grain_req.strategy == STRAT_SEMI_ADDITIVE
