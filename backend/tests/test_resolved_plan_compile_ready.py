"""P0-B — le resolved_plan v2 est autosuffisant et compilable."""
from __future__ import annotations

import json

from app.analysis.capability.adapter import DictCatalogAdapter
from app.analysis.capability.resolver import resolve
from app.analysis.contracts import (
    INTERPRETATION_SCHEMA_VERSION,
    RESOLVED_PLAN_SCHEMA_VERSION,
    validate_interpretation,
    validate_resolved,
)


def _context(*, omit_amount_physical: bool = False):
    return DictCatalogAdapter().to_context({
        "snapshot_id": "snapshot-42",
        "snapshot_captured_at": "2026-08-26T12:00:00+00:00",
        "entities": [
            {"ref": "concept:order", "grain_keys": ["id"], "physical": "orders",
             "grain_key_types": {"id": "integer"}},
            {"ref": "concept:item", "grain_keys": ["id"], "physical": "items",
             "grain_key_types": {"id": "integer"}},
        ],
        "measures": [
            {"ref": "metric:amount", "home_entity": "concept:order",
             "physical": None if omit_amount_physical else "orders.amount", "data_type": "numeric"},
            {"ref": "metric:item_cost", "home_entity": "concept:item",
             "physical": "items.cost", "data_type": "numeric"},
        ],
        "dimensions": [
            {"ref": "dimension:product", "home_entity": "concept:item",
             "physical": "items.product", "data_type": "text"},
            {"ref": "dimension:ordered_at", "home_entity": "concept:order",
             "physical": "orders.ordered_at", "data_type": "timestamp", "is_temporal": True},
        ],
        "relations": [{
            "id": 7, "from_entity": "concept:order", "to_entity": "concept:item",
            "cardinality": "1-n", "status": "validated",
            "from_key": "orders.id", "to_key": "items.order_id",
        }],
    })


def _multi_goal_interpretation():
    return validate_interpretation({
        "plan_schema_version": INTERPRETATION_SCHEMA_VERSION,
        "unresolved_terms": [],
        "goals": [
            {
                "id": "g1", "priority": 1, "type": "aggregate",
                "intent_text": "mesures par produit et mois", "entity_ref": "concept:order",
                "entity_label": None,
                "metrics": [
                    {"ref": "metric:amount", "of_ref": None, "aggregation": "sum"},
                    {"ref": "metric:item_cost", "of_ref": None, "aggregation": "avg"},
                ],
                "dimensions": [{"ref": "dimension:product"}, {"ref": "dimension:ordered_at"}],
                "filters": [{
                    "ref": "dimension:product", "operator": "contains",
                    "value_type": "string", "value": "pro", "conjunction": "and",
                }],
                "sort": [{"ref": "metric:amount", "direction": "desc", "nulls": "last"}],
                "limit": 10,
                "temporal": {"dimension_ref": "dimension:ordered_at", "grain": "month",
                             "timezone": "Europe/Paris"},
                "method": None, "depends_on": [], "ambiguities": [],
                "binning_requested": False,
            },
            {
                "id": "g2", "priority": 2, "type": "ranking",
                "intent_text": "classement dérivé", "entity_ref": "concept:order",
                "entity_label": None,
                "metrics": [{"ref": "metric:amount", "of_ref": None, "aggregation": "sum"}],
                "dimensions": [], "filters": [], "method": None,
                "sort": [{"ref": "metric:amount", "direction": "desc", "nulls": "last"}],
                "limit": 5, "depends_on": ["g1"], "ambiguities": [],
                "binning_requested": False, "temporal": None,
            },
        ],
    })


def test_resolved_plan_versions_snapshot_and_dag_are_self_contained():
    context = _context()
    _, plan = resolve(_multi_goal_interpretation(), context)

    assert plan["resolved_plan_schema_version"] == RESOLVED_PLAN_SCHEMA_VERSION
    assert plan["source_interpretation_schema_version"] == INTERPRETATION_SCHEMA_VERSION
    assert RESOLVED_PLAN_SCHEMA_VERSION != INTERPRETATION_SCHEMA_VERSION
    assert plan["catalog_snapshot"]["snapshot_id"] == "snapshot-42"
    assert len(plan["catalog_snapshot"]["fingerprint"]) == 64
    assert plan["dag"] == {
        "nodes": [
            {"goal_id": "g1", "priority": 1, "depends_on": []},
            {"goal_id": "g2", "priority": 2, "depends_on": ["g1"]},
        ],
        "edges": [{"from_goal_id": "g1", "to_goal_id": "g2"}],
        "topological_order": ["g1", "g2"],
    }
    assert all(item["status"] == "SUPPORTED" and item["compile_ready"]
               for item in plan["resolution"])

    # La validation ne reçoit plus le contexte : le JSON sérialisé suffit.
    frozen = json.loads(json.dumps(plan))
    context.entities.clear()
    context.measures.clear()
    context.dimensions.clear()
    assert validate_resolved(frozen) is frozen


def test_each_measure_is_resolved_and_join_graph_is_canonical():
    _, plan = resolve(_multi_goal_interpretation(), _context())
    item = plan["resolution"][0]

    assert "join_path" not in item
    assert item["join_graph"]["root_alias"] == "t0"
    assert [edge["validated_relation_id"] for edge in item["join_graph"]["edges"]] == [7]
    assert {node["alias"] for node in item["join_graph"]["nodes"]} == {"t0", "t1"}
    assert [(metric["ref"], metric["physical"], metric["aggregation"])
            for metric in item["operation"]["metrics"]] == [
                ("metric:amount", "orders.amount", "sum"),
                ("metric:item_cost", "items.cost", "avg"),
            ]
    grains = {entry["ref"]: entry for entry in item["grain"]["measure_grains"]}
    assert grains["metric:amount"]["aggregation_strategy"] == "pre_aggregation"
    assert grains["metric:item_cost"]["aggregation_strategy"] == "none"


def test_filters_sort_limit_temporal_and_preaggregation_are_complete():
    _, plan = resolve(_multi_goal_interpretation(), _context())
    item = plan["resolution"][0]

    assert item["filters"][0] == {
        "ref": "dimension:product", "home_entity_ref": "concept:item", "source_alias": "t1",
        "physical": "items.product", "table": "items", "column": "product", "data_type": "text",
        "operator": "contains", "value_type": "string", "value": "pro", "conjunction": "and",
    }
    assert item["sort"][0]["physical"] == "orders.amount"
    assert item["limit"] == 10
    assert item["temporal"] == {
        "enabled": True, "dimension_ref": "dimension:ordered_at", "source_alias": "t0",
        "physical": "orders.ordered_at", "data_type": "timestamp", "grain": "month",
        "timezone": "Europe/Paris",
    }
    assert len(item["pre_aggregations"]) == 1
    instruction = item["pre_aggregations"][0]
    assert instruction["source_entity_ref"] == "concept:order"
    assert instruction["group_by"] == [{"physical": "orders.id", "output_alias": "k0"}]
    assert instruction["aggregations"] == [{
        "measure_ref": "metric:amount", "input_physical": "orders.amount",
        "function": "sum", "output_alias": "m0",
    }]
    assert instruction["join_back"] == [{
        "source_key": "orders.id", "target_alias": "t1", "target_key": "items.order_id",
        "validated_relation_id": 7, "output_key_alias": "k0",
    }]


def test_count_distinct_embeds_the_exact_physical_key():
    interpretation = validate_interpretation({
        "plan_schema_version": INTERPRETATION_SCHEMA_VERSION,
        "unresolved_terms": [], "goals": [{
            "id": "g1", "priority": 1, "type": "count", "intent_text": "compter",
            "entity_ref": "concept:order", "entity_label": None,
            "metrics": [], "dimensions": [{"ref": "dimension:product"}],
            "filters": [], "method": None, "depends_on": [], "ambiguities": [],
            "binning_requested": False, "sort": [], "limit": None, "temporal": None,
        }],
    })
    _, plan = resolve(interpretation, _context())
    item = plan["resolution"][0]
    assert item["operation"]["operator"] == "count_distinct"
    assert item["operation"]["count_distinct_keys"] == [
        {"physical": "orders.id", "data_type": "integer"},
    ]
    assert item["grain"]["aggregation_strategy"] == "count_distinct"


def test_missing_physical_mapping_cannot_be_supported():
    _, plan = resolve(_multi_goal_interpretation(), _context(omit_amount_physical=True))
    items = {item["goal_id"]: item for item in plan["resolution"]}
    assert items["g1"]["status"] == "UNSUPPORTED"
    assert items["g1"]["compile_ready"] is False
    assert "physical_column:physical_mapping_missing" in items["g1"]["compile_blockers"]
