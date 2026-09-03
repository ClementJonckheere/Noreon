"""P0-C0 — tests éliminatoires écrits avant les corrections P0-C.

Le corpus reste volontairement générique : ces tests verrouillent des propriétés
de contrat, de provenance et de résolution, jamais un vocabulaire métier.
"""
from __future__ import annotations

import copy
from types import SimpleNamespace

import pytest

from app.analysis import contracts as C
from app.analysis.capability.adapter import DictCatalogAdapter
from app.analysis.capability.db_context import build_catalog_and_context
from app.analysis.capability.resolved_plan import catalog_snapshot, join_graph, select_join_tree
from app.analysis.capability.resolver import resolve
from app.analysis.interpreter import PLANNER_PROMPT_VERSION, PLANNER_SYSTEM, build_user_prompt
from app.analysis.shadow.service import ShadowPlanResult
from app.models.planner_shadow import PlannerShadowEvaluation


def _metric(ref: str = "metric:value", aggregation: str = "sum") -> dict:
    return {"ref": ref, "of_ref": None, "aggregation": aggregation}


def _goal(goal_type: str = "aggregate", **overrides) -> dict:
    goal = {
        "id": "g1",
        "priority": 1,
        "type": goal_type,
        "intent_text": "Calcul analytique",
        "entity_ref": "concept:subject",
        "entity_label": None,
        "metrics": [_metric()] if goal_type == "aggregate" else [],
        "dimensions": [],
        "filters": [],
        "method": None,
        "depends_on": [],
        "ambiguities": [],
        "binning_requested": False,
        "sort": [],
        "limit": None,
        "temporal": None,
    }
    goal.update(overrides)
    return goal


def _unresolved(goal_id: str = "g1", *, role: str = "entity",
                necessity: str = "required") -> dict:
    return {
        "goal_id": goal_id,
        "term": "opérande absent",
        "role": role,
        "necessity": necessity,
        "source_span": None,
        "reason": "aucune référence valide dans le catalogue",
    }


def _payload(goal: dict, unresolved_terms: list[dict] | None = None) -> dict:
    return {
        "plan_schema_version": C.INTERPRETATION_SCHEMA_VERSION,
        "goals": [goal],
        "unresolved_terms": unresolved_terms or [],
    }


def _context():
    return DictCatalogAdapter().to_context({
        "entities": [{
            "ref": "concept:subject", "grain_keys": ["id"],
            "grain_key_types": {"id": "integer"}, "physical": "subjects",
        }],
        "measures": [{
            "ref": "metric:value", "home_entity": "concept:subject",
            "physical": "subjects.value", "data_type": "numeric",
        }],
        "dimensions": [],
        "relations": [],
    })


# C4 — présence explicite et complétude conditionnelle -----------------------
def test_missing_required_decision_field_is_contract_error():
    goal = _goal()
    del goal["sort"]
    with pytest.raises(C.ContractError):
        C.validate_interpretation(_payload(goal))


def test_goal_without_operand_or_linked_reason_is_rejected():
    goal = _goal(
        "count", entity_ref=None, metrics=[], dimensions=[], filters=[], method=None,
    )
    with pytest.raises(C.ContractError) as exc:
        C.validate_interpretation(_payload(goal))
    assert exc.value.code in {"goal_without_operand", "count_operand_missing"}


def test_average_cannot_become_implicit_sum():
    metric = {"ref": "metric:value", "of_ref": None}
    goal = _goal(intent_text="Average value", metrics=[metric])
    with pytest.raises(C.ContractError):
        C.validate_interpretation(_payload(goal))


def test_average_intent_with_explicit_sum_is_rejected():
    goal = _goal(intent_text="Moyenne de la valeur", metrics=[_metric(aggregation="sum")])
    with pytest.raises(C.ContractError) as exc:
        C.validate_interpretation(_payload(goal))
    assert exc.value.code == "average_aggregation_mismatch"


def test_count_distinct_with_sum_aggregation_is_rejected_by_c4():
    goal = _goal("count", metrics=[_metric(aggregation="sum")])
    with pytest.raises(C.ContractError) as exc:
        C.validate_interpretation(_payload(goal))
    assert exc.value.code in {"count_aggregation_mismatch", "operation_aggregation_mismatch"}


@pytest.mark.parametrize(
    ("overrides", "expected_code"),
    [
        ({"entity_ref": None, "dimensions": []}, "ranking_axis_missing"),
        ({"sort": []}, "ranking_sort_missing"),
        ({"limit": None}, "ranking_limit_missing"),
    ],
)
def test_ranking_requires_axis_sort_and_limit(overrides, expected_code):
    goal = _goal(
        "ranking",
        entity_ref="concept:subject",
        metrics=[_metric()],
        dimensions=[{"ref": "dimension:group"}],
        sort=[{"ref": "metric:value", "direction": "desc", "nulls": "last"}],
        limit=10,
    )
    goal.update(overrides)
    with pytest.raises(C.ContractError) as exc:
        C.validate_interpretation(_payload(goal))
    assert exc.value.code == expected_code


def test_c4_ambiguity_becomes_needs_clarification_in_c6():
    goal = _goal(
        metrics=[],
        ambiguities=[{"code": "criterion_missing", "detail": "metric not determined"}],
    )
    interpretation = C.validate_interpretation(_payload(goal))
    resolution, plan = resolve(interpretation, _context())
    assert resolution.goals[0].status == "NEEDS_CLARIFICATION"
    assert plan["resolution"][0]["status"] == "NEEDS_CLARIFICATION"
    assert plan["resolution"][0]["compile_ready"] is False


def test_resolved_count_distinct_cannot_embed_sum_metric():
    interpretation = C.validate_interpretation(_payload(_goal("count")))
    _, plan = resolve(interpretation, _context())
    bad = copy.deepcopy(plan)
    mapping = {
        "ref": "metric:value",
        "source_entity_ref": "concept:subject",
        "source_alias": "t0",
        "physical": "subjects.value",
        "table": "subjects",
        "column": "value",
        "data_type": "numeric",
        "aggregation": "sum",
        "output_alias": "m0",
    }
    bad["resolution"][0]["operation"]["metrics"] = [mapping]
    bad["resolution"][0]["physical"]["measures"] = [mapping]
    with pytest.raises(C.ContractError) as exc:
        C.validate_resolved(bad)
    assert exc.value.code in {"count_aggregation_mismatch", "operation_aggregation_mismatch"}


def test_provider_raw_and_normalized_interpretation_are_distinct_telemetry():
    fields = ShadowPlanResult.__dataclass_fields__
    assert "provider_raw_json" in fields
    assert "normalized_interpretation_json" in fields
    assert hasattr(PlannerShadowEvaluation, "provider_raw_json")
    assert hasattr(PlannerShadowEvaluation, "normalized_interpretation_json")


def test_catalog_snapshot_keeps_aliases_and_visible_non_executable_relations():
    context = DictCatalogAdapter().to_context({
        "entities": [
            {"ref": "concept:left", "physical": "lefts", "grain_keys": ["id"],
             "aliases": ["gauche"]},
            {"ref": "concept:right", "physical": "rights", "grain_keys": ["id"],
             "aliases": ["droite"]},
        ],
        "measures": [{
            "ref": "metric:value", "home_entity": "concept:left",
            "physical": "lefts.value", "aliases": ["valeur"],
        }],
        "dimensions": [],
        "relations": [
            {"id": 1, "from_entity": "concept:left", "to_entity": "concept:right",
             "from_key": "lefts.right_id", "to_key": "rights.id", "origin": "constraint",
             "status": "validated", "validation_status": "system_validated", "executable": True},
            {"id": 2, "from_entity": "concept:left", "to_entity": "concept:right",
             "from_key": "lefts.guess", "to_key": "rights.guess", "origin": "inferred",
             "status": "candidate", "validation_status": "unvalidated", "executable": False},
        ],
    })
    snapshot = catalog_snapshot(context)
    assert snapshot["entities"][0]["aliases"] == ["gauche"]
    assert snapshot["measures"][0]["aliases"] == ["valeur"]
    assert {relation["id"] for relation in snapshot["relations"]} == {1, 2}
    assert next(r for r in snapshot["relations"] if r["id"] == 2)["executable"] is False


def test_interpreter_prompt_13_defines_operands_and_four_examples():
    prompt = PLANNER_SYSTEM.casefold()
    assert PLANNER_PROMPT_VERSION == "1.3"
    assert "tout opérande métier indispensable" in prompt
    assert "tout terme de la question" not in prompt
    assert prompt.count("exemple ") >= 4
    assert "required unresolved" in prompt
    assert "optional unresolved" in prompt
    assert "ambiguity" in prompt
    assert "known reference" in prompt
    assert "meilleurs clients" in prompt
    assert "metric unresolved = \"meilleurs\"" in prompt


def test_used_catalog_reference_cannot_also_be_unresolved():
    term = _unresolved(role="metric")
    term["term"] = "metric:value"
    with pytest.raises(C.ContractError) as exc:
        C.validate_interpretation(_payload(_goal(), [term]))
    assert exc.value.code == "resolved_ref_also_unresolved"


# Catalogue canonique --------------------------------------------------------
class _Rows:
    def __init__(self, rows):
        self.rows = list(rows)

    def scalars(self):
        return self

    def all(self):
        return list(self.rows)


class _FakeSession:
    def __init__(self, *, candidates=(), semantic_rows=()):
        self.candidates = list(candidates)
        self.semantic_rows = list(semantic_rows)

    def execute(self, statement):
        rendered = str(statement)
        if "concept_mappings" in rendered:
            return _Rows(self.semantic_rows)
        if "relation_candidates" in rendered:
            return _Rows(self.candidates)
        return _Rows([])


def _column(name: str, data_type: str, *, primary: bool = False):
    return SimpleNamespace(
        name=name, data_type=data_type, is_primary_key=primary, comment=None,
    )


def _table(name: str, columns: list):
    return SimpleNamespace(
        table_name=name, schema_name="public", columns=columns, comment=None,
    )


def _snapshot(tables: list, relations=()):
    return SimpleNamespace(
        id=41, tables=tables, relations=list(relations), created_at=None,
    )


def _install_snapshot(monkeypatch, snapshot):
    monkeypatch.setattr(
        "app.services.schema_context.current_snapshot",
        lambda session, connection_id: snapshot,
    )


def test_numeric_primary_and_foreign_keys_are_never_automatic_measures(monkeypatch):
    db_relation = SimpleNamespace(
        id=3,
        from_table="events", from_column="subject_id", from_schema="public",
        to_table="subjects", to_column="id", to_schema="public",
        kind="declared", status="validated", cardinality="n-1",
        integrity_ratio=1.0, confidence=1.0, details={"constraint_name": "fk_subject"},
    )
    snap = _snapshot([
        _table("subjects", [_column("id", "integer", primary=True)]),
        _table("events", [
            _column("id", "integer", primary=True),
            _column("subject_id", "integer"),
        ]),
    ], [db_relation])
    _install_snapshot(monkeypatch, snap)

    _, context = build_catalog_and_context(_FakeSession(), 7, tenant_id=2)

    assert "metric:subjects_id" not in context.measures
    assert "metric:events_id" not in context.measures
    assert "metric:events_subject_id" not in context.measures
    assert set(context.column_roles["subjects.id"]) == {"entity_key"}
    assert set(context.column_roles["events.subject_id"]) == {"entity_key"}


def test_unvalidated_numeric_column_is_attribute_not_measure(monkeypatch):
    snap = _snapshot([_table("subjects", [
        _column("id", "integer", primary=True),
        _column("score", "numeric"),
    ])])
    _install_snapshot(monkeypatch, snap)

    _, context = build_catalog_and_context(_FakeSession(), 7, tenant_id=2)

    assert "metric:subjects_score" not in context.measures
    assert set(context.column_roles["subjects.score"]) <= {"attribute", "unclassified"}


def test_validated_measure_role_exposes_numeric_measure(monkeypatch):
    concept = SimpleNamespace(name="Validated Value", synonyms=["approved value"])
    mapping = SimpleNamespace(
        table_name="subjects", column_name="score", schema_name="public",
        status="validated", analytical_roles=["measure"], concept=concept,
    )
    snap = _snapshot([_table("subjects", [
        _column("id", "integer", primary=True), _column("score", "numeric"),
    ])])
    _install_snapshot(monkeypatch, snap)

    catalog, context = build_catalog_and_context(
        _FakeSession(semantic_rows=[(mapping, concept)]), 7, tenant_id=2,
    )

    assert "metric:subjects_score" in context.measures
    assert context.column_roles["subjects.score"] == ("measure",)
    assert catalog.metrics[0]["metric_label"] == "Validated Value"


def test_declared_db_relation_is_visible_and_executable(monkeypatch):
    db_relation = SimpleNamespace(
        id=9,
        from_table="events", from_column="subject_id", from_schema="public",
        to_table="subjects", to_column="id", to_schema="public",
        kind="declared", status="validated", cardinality="n-1",
        integrity_ratio=0.99, confidence=1.0, details={"constraint_name": "fk_subject"},
    )
    snap = _snapshot([
        _table("subjects", [_column("id", "integer", primary=True)]),
        _table("events", [
            _column("id", "integer", primary=True), _column("subject_id", "integer"),
        ]),
    ], [db_relation])
    _install_snapshot(monkeypatch, snap)

    catalog, context = build_catalog_and_context(_FakeSession(), 7, tenant_id=2)

    assert len(context.relations) == 1
    relation = context.relations[0]
    assert relation.origin == "constraint"
    assert relation.validation_status == "system_validated"
    assert relation.is_executable is True
    assert any(item["executable"] is True for item in catalog.relations)


def test_inferred_unvalidated_candidate_is_visible_but_not_executable(monkeypatch):
    candidate = SimpleNamespace(
        id=12, connection_id=7, tenant_id=2,
        left_table="events", left_column="subject_id", left_schema="public",
        right_table="subjects", right_column="id", right_schema="public",
        direction="left_to_right", cardinality="n-1", coverage=0.92,
        target_uniqueness=1.0, type_compatibility="conforme", exceptions_count=2,
        exceptions_note=None, alternatives=[], origin="inferred", status="candidate",
        evidence={"sample_size": 100}, validated_by=None, validated_at=None,
        validation_window=None, evaluated_at=None, snapshot_id="41", source_ids=[],
    )
    snap = _snapshot([
        _table("subjects", [_column("id", "integer", primary=True)]),
        _table("events", [
            _column("id", "integer", primary=True), _column("subject_id", "integer"),
        ]),
    ])
    _install_snapshot(monkeypatch, snap)

    catalog, context = build_catalog_and_context(
        _FakeSession(candidates=[candidate]), 7, tenant_id=2,
    )

    assert len(catalog.relations) == 1
    assert catalog.relations[0]["executable"] is False
    assert len(context.relations) == 1
    assert context.relations[0].is_executable is False
    assert context.relations[0].evidence == {"sample_size": 100}


@pytest.mark.parametrize("status", ["proposed", "rejected"])
def test_proposed_or_rejected_alias_is_not_exposed_to_interpreter(monkeypatch, status):
    concept = SimpleNamespace(name="Recognizable Alias", synonyms=["Known Synonym"])
    mapping = SimpleNamespace(
        table_name="subjects", column_name="id", schema_name="public",
        status=status, analytical_roles=["entity_key"], concept=concept,
    )
    snap = _snapshot([_table("subjects", [_column("id", "integer", primary=True)])])
    _install_snapshot(monkeypatch, snap)

    catalog, _ = build_catalog_and_context(
        _FakeSession(semantic_rows=[(mapping, concept)]), 7, tenant_id=2,
    )
    prompt = build_user_prompt(catalog, "question")

    assert "Recognizable Alias" not in prompt
    assert "Known Synonym" not in prompt


@pytest.mark.parametrize("status", ["validated", "corrected"])
def test_validated_or_corrected_alias_is_exposed_to_interpreter(monkeypatch, status):
    concept = SimpleNamespace(name="Recognizable Alias", synonyms=["Known Synonym"])
    mapping = SimpleNamespace(
        table_name="subjects", column_name="id", schema_name="public",
        status=status, analytical_roles=["entity_key"], concept=concept,
    )
    snap = _snapshot([_table("subjects", [_column("id", "integer", primary=True)])])
    _install_snapshot(monkeypatch, snap)

    catalog, _ = build_catalog_and_context(
        _FakeSession(semantic_rows=[(mapping, concept)]), 7, tenant_id=2,
    )
    prompt = build_user_prompt(catalog, "question")

    assert "Recognizable Alias" in prompt
    assert "Known Synonym" in prompt


# C6 — diagnostics, racine multi-mesures et provenance ----------------------
def test_missing_root_does_not_emit_cascading_unresolved_diagnostics():
    goal = _goal("count", entity_ref=None)
    interpretation = C.validate_interpretation(_payload(goal, [_unresolved()]))
    resolution, _ = resolve(interpretation, _context())
    requirements = resolution.goals[0].requirements

    unresolved_codes = {
        req.reason_code for req in requirements
        if req.state == "unresolved" and req.kind != "unresolved_term"
    }
    assert unresolved_codes == {"root_entity_missing"}
    dependent = {req.kind: req.state for req in requirements
                 if req.kind in {"join_path", "count_key", "fanout"}}
    assert dependent == {
        "join_path": "not_evaluated",
        "count_key": "not_evaluated",
        "fanout": "not_evaluated",
    }


def _multi_measure_interpretation(metric_refs: list[str]):
    return C.validate_interpretation(_payload(_goal(
        entity_ref=None,
        metrics=[_metric(ref, "sum") for ref in metric_refs],
    )))


def test_multi_measure_root_is_permutation_invariant_or_clarified():
    context = DictCatalogAdapter().to_context({
        "entities": [
            {"ref": "concept:left", "grain_keys": ["id"], "physical": "lefts"},
            {"ref": "concept:right", "grain_keys": ["id"], "physical": "rights"},
        ],
        "measures": [
            {"ref": "metric:left_value", "home_entity": "concept:left",
             "physical": "lefts.value"},
            {"ref": "metric:right_value", "home_entity": "concept:right",
             "physical": "rights.value"},
        ],
        "dimensions": [],
        "relations": [{
            "id": 5, "from_entity": "concept:left", "to_entity": "concept:right",
            "from_key": "lefts.right_id", "to_key": "rights.id",
            "cardinality": "one_to_one", "status": "validated",
        }],
    })

    _, first = resolve(
        _multi_measure_interpretation(["metric:left_value", "metric:right_value"]), context,
    )
    _, second = resolve(
        _multi_measure_interpretation(["metric:right_value", "metric:left_value"]), context,
    )
    a, b = first["resolution"][0], second["resolution"][0]

    assert a["status"] == b["status"]
    if a["status"] == "NEEDS_CLARIFICATION":
        assert b["status"] == "NEEDS_CLARIFICATION"
    else:
        assert a["physical"]["root_entity_ref"] == b["physical"]["root_entity_ref"]


def test_multi_path_join_graph_is_deduped_stable_and_has_provenance():
    spec = {
        "entities": [
            {"ref": "concept:root", "grain_keys": ["id"], "physical": "roots"},
            {"ref": "concept:bridge", "grain_keys": ["id"], "physical": "bridges"},
            {"ref": "concept:a", "grain_keys": ["id"], "physical": "as"},
            {"ref": "concept:b", "grain_keys": ["id"], "physical": "bs"},
        ],
        "measures": [],
        "dimensions": [],
        "relations": [
            {"id": 5, "from_entity": "concept:root", "to_entity": "concept:bridge",
             "from_key": "roots.bridge_id", "to_key": "bridges.id",
             "cardinality": "many_to_one", "status": "validated",
             "origin": "constraint", "validation_status": "system_validated",
             "evidence": {"constraint": "fk_bridge"}, "coverage": 1.0},
            {"id": 6, "from_entity": "concept:bridge", "to_entity": "concept:a",
             "from_key": "bridges.a_id", "to_key": "as.id",
             "cardinality": "many_to_one", "status": "validated",
             "origin": "declared", "validation_status": "human_validated",
             "evidence": {"review": "approved"}, "coverage": 0.99},
            {"id": 7, "from_entity": "concept:bridge", "to_entity": "concept:b",
             "from_key": "bridges.b_id", "to_key": "bs.id",
             "cardinality": "many_to_one", "status": "validated",
             "origin": "declared", "validation_status": "human_validated",
             "evidence": {"review": "approved"}, "coverage": 0.98},
        ],
    }
    context = DictCatalogAdapter().to_context(spec)
    first = join_graph(
        context,
        select_join_tree(context, "concept:root", {"concept:a", "concept:b"}),
    )
    second = join_graph(
        context,
        select_join_tree(context, "concept:root", {"concept:b", "concept:a"}),
    )

    assert first == second
    assert first["execution_order"] == [5, 6, 7]
    assert len(first["edges"]) == len({edge["validated_relation_id"] for edge in first["edges"]})
    assert [node["alias"] for node in first["nodes"]] == ["t0", "t1", "t2", "t3"]
    assert all(
        {"origin", "validation_status", "evidence", "coverage", "provenance"} <= set(edge)
        for edge in first["edges"]
    )
