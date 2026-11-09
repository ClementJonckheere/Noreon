"""Phase 2 — C3b : runner à deux tables, incidents réseau séparés, préflight."""
from __future__ import annotations

from app.analysis import benchmark as B
from app.analysis.contracts import INTERPRETATION_SCHEMA_VERSION, validate_interpretation
from app.analysis.eval_cases import EvalCase
from app.analysis.interpreter import PlannerCatalog
from app.analysis.planner_stub import StubPlanner
from app.llm.base import LLMProvider, PlanningNotSupported

MAIN, SIMPLE = "gpt-oss-120b", "gpt-oss-20b"


def _cat():
    return PlannerCatalog(
        concepts=[{"entity_ref": "concept:customer"}, {"entity_ref": "concept:order"}],
        metrics=[{"metric_ref": "metric:net_revenue"}],
        dimensions=[{"dimension_ref": "dimension:city"},
                    {"dimension_ref": "dimension:time"}], relations=[], stats={})


def _interp(type_, extra=()):
    def goal(goal_id, priority, goal_type, entity_ref, depends_on=()):
        payload = {
            "id": goal_id, "priority": priority, "type": goal_type,
            "intent_text": "x", "entity_ref": entity_ref, "entity_label": None,
            "metrics": [], "dimensions": [], "filters": [], "method": None,
            "depends_on": list(depends_on), "ambiguities": [],
            "binning_requested": False, "sort": [], "limit": None,
            "temporal": None,
        }
        if goal_type == "trend":
            payload["metrics"] = [{
                "ref": "metric:net_revenue", "of_ref": None, "aggregation": "sum",
            }]
            payload["temporal"] = {
                "dimension_ref": "dimension:time", "grain": "month", "timezone": "UTC",
            }
        if goal_type in {"attribution", "segmentation", "affinity", "cohort", "correlation"}:
            payload["method"] = {"name": goal_type, "version": "1.0", "params": {}}
        return payload

    goals = [goal("g1", 1, type_, "concept:customer")]
    for i, t in enumerate(extra, start=2):
        goals.append(goal(f"g{i}", i, t, "concept:order", ("g1",)))
    return validate_interpretation({"plan_schema_version": INTERPRETATION_SCHEMA_VERSION,
                                    "goals": goals,
                                    "unresolved_terms": []})


_C1 = EvalCase("c1", "combien de clients", 1, frozenset({"count"}), simple_eligible=True)
_C2 = EvalCase("c2", "segmente mes clients", 1, frozenset({"segmentation"}))


def test_main_tier_evaluates_whole_corpus_semantically():
    plans = {"c1": _interp("count"), "c2": _interp("segmentation")}

    def plan_fn(model, q, cat):
        return B.PlanResult(interp=plans["c2" if "segmente" in q else "c1"], latency_ms=12.0, tokens=100)

    rep = B.run_model(MAIN, [_C1, _C2], _cat(), plan_fn=plan_fn, tier="main")
    assert all(r.semantic for r in rep.results)
    assert rep.recall_mean == 1.0 and not rep.eliminated
    assert rep.latency_ms_mean == 12.0 and rep.as_dict()["tokens_total"] == 200


def test_simple_tier_semantic_only_on_simple_and_checks_routing_exclusion():
    def plan_fn(model, q, cat):
        return B.PlanResult(interp=_interp("segmentation" if "segmente" in q else "count"))

    rep = B.run_model(SIMPLE, [_C1, _C2], _cat(), plan_fn=plan_fn, tier="simple",
                      main_model=MAIN, simple_model=SIMPLE)
    by = {r.case_id: r for r in rep.results}
    assert by["c1"].semantic is True                      # cas simple → sémantique
    assert by["c2"].semantic is False                     # cas complexe → conformité seule
    assert by["c2"].routing_excluded is True              # pré-routeur l'aurait exclu du 20b
    assert rep.routing_leaks == 0 and not rep.eliminated


def _cat_domain(domain):
    c = _cat()
    return PlannerCatalog(concepts=c.concepts, metrics=c.metrics, dimensions=c.dimensions,
                          relations=c.relations, stats=c.stats, domain=domain)


def test_cross_domain_case_is_not_scored_semantically():
    """Un cas d'un AUTRE domaine que le catalogue : conformité seule, pas de type."""
    crm_case = EvalCase("x", "combien d'abonnements", 1, frozenset({"count"}),
                        simple_eligible=True, domain="crm")
    # le modèle répond une tendance (hors sujet) mais le catalogue est RETAIL
    def plan_fn(model, q, cat):
        return B.PlanResult(interp=_interp("trend"))
    rep = B.run_model(MAIN, [crm_case], _cat_domain("retail"), plan_fn=plan_fn, tier="main")
    assert rep.results[0].semantic is False       # domaine incompatible
    assert not rep.eliminated                     # pas de pénalité de type


def test_invented_ref_eliminates_even_cross_domain():
    """Inventer une référence reste éliminatoire même sur un catalogue d'un autre domaine."""
    crm_case = EvalCase("x", "combien d'abonnements", 1, frozenset({"count"}), domain="crm")
    def plan_fn(model, q, cat):
        from app.analysis.contracts import validate_interpretation
        payload = _interp("count").goals[0].raw
        payload["entity_ref"] = "concept:invented_entity"
        return B.PlanResult(interp=validate_interpretation({
            "plan_schema_version": INTERPRETATION_SCHEMA_VERSION,
            "unresolved_terms": [], "goals": [payload]}))
    rep = B.run_model(MAIN, [crm_case], _cat_domain("retail"), plan_fn=plan_fn, tier="main")
    assert rep.results[0].semantic is False
    assert rep.eliminated and "référence hors catalogue" in rep.elimination_reasons()


def test_20b_substitution_on_simple_case_eliminates():
    # le 20b répond une tendance sur une demande de dénombrement → substitution.
    def plan_fn(model, q, cat):
        return B.PlanResult(interp=_interp("trend"))

    rep = B.run_model(SIMPLE, [_C1], _cat(), plan_fn=plan_fn, tier="simple",
                      main_model=MAIN, simple_model=SIMPLE)
    assert rep.eliminated
    assert "substitution silencieuse" in rep.elimination_reasons()


def test_network_incident_is_separated_from_json_conformity():
    calls = {"n": 0}

    def plan_fn(model, q, cat):
        calls["n"] += 1
        if calls["n"] == 1:
            return B.PlanResult(interp=_interp("count"), latency_ms=5.0)
        return B.PlanResult(interp=None, error_kind="network", attempts=2)

    rep = B.run_model(MAIN, [_C1, _C2], _cat(), plan_fn=plan_fn, tier="main")
    assert rep.network_incidents == 1
    assert rep.json_conformity == 1.0          # l'incident réseau n'est pas un JSON non conforme
    assert rep.as_dict()["retries_total"] >= 3


def test_preflight_ok_with_capable_provider():
    pf = B.preflight(StubPlanner())
    assert pf["ok"] is True and pf["json_schema"] is True


def test_preflight_fails_when_planning_unsupported():
    class _Dumb(LLMProvider):
        name = "dumb"
        def generate_sql(self, *a, **k): raise NotImplementedError
        def analyze_results(self, *a, **k): raise NotImplementedError
    pf = B.preflight(_Dumb())
    assert pf["ok"] is False and pf["error"]
