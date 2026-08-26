"""Phase 2 — C3 : routage à deux modèles + benchmark (seuils éliminatoires).

Sans clé : logique déterministe uniquement (routage + scoring). Le benchmark réel
2-modèles s'exécute côté opérateur avec la clé OVHcloud.
"""
from __future__ import annotations

import pytest

from app.analysis import benchmark as B
from app.analysis import routing as R
from app.analysis.contracts import validate_interpretation
from app.analysis.eval_cases import CASES, CASES_BY_ID
from app.analysis.interpreter import PlannerCatalog

MAIN = "gpt-oss-120b"
SIMPLE = "gpt-oss-20b"


# --- Pré-routage sur le jeu d'éval ------------------------------------------
@pytest.mark.parametrize("case", CASES, ids=[c.id for c in CASES])
def test_preroute_matches_expected_tier(case):
    dec = R.preroute(case.question, main_model=MAIN, simple_model=SIMPLE)
    if case.simple_eligible:
        assert dec.selected_model == SIMPLE, (case.id, dec.routing_reason)
    else:
        assert dec.selected_model == MAIN, (case.id, dec.routing_reason)


# --- Allowlist déterministe sur le PLAN -------------------------------------
def _interp(goals, unresolved=None):
    return validate_interpretation({
        "plan_schema_version": "1.2", "goals": goals,
        "unresolved_terms": unresolved or []})


def test_single_count_goal_is_eligible():
    interp = _interp([{"id": "g1", "priority": 1, "type": "count",
                       "intent_text": "combien", "entity_ref": "concept:customer"}])
    ok, reason = R.plan_is_simple_eligible(interp)
    assert ok and reason is None


@pytest.mark.parametrize("mutation,expect_reason", [
    ({"type": "segmentation"}, "hors allowlist"),
    ({"method": {"name": "rfm", "params": {}}}, "méthode"),
    ({"depends_on": ["g0"]}, None),   # dépendance → inéligible (raison variable)
    ({"ambiguities": [{"q": "?"}]}, "ambiguïté"),
    ({"entity_ref": None}, "entité non résolue"),
])
def test_plan_ineligible_on_complexity(mutation, expect_reason):
    goal = {"id": "g1", "priority": 1, "type": "count", "intent_text": "x",
            "entity_ref": "concept:customer"}
    goal.update(mutation)
    # une dépendance suppose un parent existant ; on ajoute g0 le cas échéant.
    goals = [goal]
    if mutation.get("depends_on"):
        goals = [{"id": "g0", "priority": 1, "type": "count", "intent_text": "p",
                  "entity_ref": "concept:order"},
                 {**goal, "priority": 2}]
    interp = _interp(goals)
    ok, reason = R.plan_is_simple_eligible(interp if not mutation.get("depends_on")
                                           else _interp(goals))
    assert ok is False
    if expect_reason:
        assert expect_reason in reason


# --- Escalade explicite et auditée ------------------------------------------
def test_escalation_is_audited_when_20b_plan_is_complex():
    """20b pré-routé mais plan complexe (2 objectifs) → rejet + relance 120b,
    avec audit complet."""
    simple_plan = {"plan_schema_version": "1.2", "unresolved_terms": [], "goals": [
        {"id": "g1", "priority": 1, "type": "segmentation", "intent_text": "seg",
         "entity_ref": "concept:customer"},
        {"id": "g2", "priority": 2, "type": "affinity", "intent_text": "aff",
         "entity_ref": "concept:product", "depends_on": ["g1"]}]}
    main_plan = {"plan_schema_version": "1.2", "unresolved_terms": [], "goals": [
        {"id": "g1", "priority": 1, "type": "segmentation", "intent_text": "seg",
         "entity_ref": "concept:customer"}]}

    calls = []

    def plan_fn(model, question, catalog):
        calls.append(model)
        return validate_interpretation(simple_plan if model == SIMPLE else main_plan)

    # question pré-routée simple mais plan complexe
    interp, dec = R.route_and_plan("combien", None, plan_fn=plan_fn, main_model=MAIN, simple_model=SIMPLE)
    assert calls == [SIMPLE, MAIN]                       # escalade réelle
    assert dec.selected_model == MAIN
    assert dec.previous_model == SIMPLE
    assert dec.escalation_reason and "objectifs" in dec.escalation_reason
    assert dec.as_dict()["routing_reason"]


def test_no_escalation_when_20b_plan_is_simple():
    plan = {"plan_schema_version": "1.2", "unresolved_terms": [], "goals": [
        {"id": "g1", "priority": 1, "type": "count", "intent_text": "combien",
         "entity_ref": "concept:customer"}]}
    calls = []

    def plan_fn(model, question, catalog):
        calls.append(model)
        return validate_interpretation(plan)

    interp, dec = R.route_and_plan("combien de clients", None, plan_fn=plan_fn,
                                   main_model=MAIN, simple_model=SIMPLE)
    assert calls == [SIMPLE]
    assert dec.selected_model == SIMPLE and dec.previous_model is None


# --- Benchmark : seuils éliminatoires ---------------------------------------
def _catalog():
    return PlannerCatalog(
        concepts=[{"entity_ref": "concept:customer"}, {"entity_ref": "concept:order"}],
        metrics=[{"metric_ref": "metric:net_revenue"}],
        dimensions=[{"dimension_ref": "dimension:city"}], relations=[], stats={})


def test_out_of_catalog_reference_eliminates():
    from app.analysis.eval_cases import EvalCase
    case = EvalCase(id="c", question="q", min_goals=1, expect_types=frozenset({"count"}))
    interp = _interp([{"id": "g1", "priority": 1, "type": "count", "intent_text": "x",
                       "entity_ref": "concept:unknown_entity"}])
    res = B.score_case(case, interp, B.catalog_refs(_catalog()))
    assert res.out_of_catalog is True


def test_silent_substitution_is_detected():
    from app.analysis.eval_cases import EvalCase
    case = EvalCase(id="c", question="combien de clients", min_goals=1,
                    expect_types=frozenset({"count"}))
    # le modèle répond une tendance non demandée → substitution
    interp = _interp([{"id": "g1", "priority": 1, "type": "trend", "intent_text": "x",
                       "entity_ref": "concept:order",
                       "metrics": [{"ref": "metric:net_revenue"}]}])
    res = B.score_case(case, interp, B.catalog_refs(_catalog()))
    assert res.silent_substitution is True and res.primary_forgotten is True


def test_model_eliminated_below_thresholds():
    from app.analysis.eval_cases import EvalCase
    good = EvalCase(id="ok", question="combien", min_goals=1, expect_types=frozenset({"count"}))
    rep = B.ModelReport(model=MAIN, results=[
        B.score_case(good, _interp([{"id": "g1", "priority": 1, "type": "count",
                                     "intent_text": "x", "entity_ref": "concept:customer"}]),
                     B.catalog_refs(_catalog())),
        B.CaseResult("bad", json_ok=False, error="x"),   # non conforme
    ])
    assert rep.eliminated
    assert any("JSON conforme" in r for r in rep.elimination_reasons())


def test_rank_puts_eliminated_last():
    clean = B.ModelReport(model="A", results=[B.CaseResult("c", json_ok=True, recall=1.0, latency_ms=100.0)])
    bad = B.ModelReport(model="B", results=[
        B.CaseResult("c", json_ok=True, recall=1.0, out_of_catalog=True, latency_ms=10.0)])
    order = B.rank([bad, clean])
    assert [r.model for r in order] == ["A", "B"]   # qualifié avant éliminé


def test_eval_cases_have_routing_expectations():
    assert any(c.simple_eligible for c in CASES) and any(not c.simple_eligible for c in CASES)
