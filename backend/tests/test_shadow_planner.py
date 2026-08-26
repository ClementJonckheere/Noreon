"""Phase 2 — C5 : Shadow Planner. AUCUN appel LLM réel (stubs/fakes).

Vérifie : non-blocage, isolation erreurs/timeout, classification des divergences,
routeur, réparation, sampling, isolation des modes, versions, confidentialité,
`unknown≠empty`, refus `active/canary`, worker à session propre, et qu'aucune
donnée shadow n'atteint `analysis_plans`.
"""
from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import pytest

from app.analysis.contracts import validate_interpretation
from app.analysis.shadow import comparator as C
from app.analysis.shadow import service as S
from app.analysis.shadow.executor import InProcessShadowExecutor
from app.analysis.shadow.projection import project_fallback, project_llm
from app.models.planner_shadow import PlannerShadowEvaluation

MAIN, SIMPLE = "gpt-oss-120b", "gpt-oss-20b"


# --- fakes ------------------------------------------------------------------
class FakeSession:
    def __init__(self):
        self.added, self.commits, self.closed = [], 0, False
    def add(self, row): self.added.append(row)
    def commit(self): self.commits += 1
    def close(self): self.closed = True


class RecExecutor:
    def __init__(self): self.envelopes = []
    def submit(self, env): self.envelopes.append(env); return "submitted"


def _settings(**over):
    base = dict(planner_mode="shadow", planner_shadow_sample_rate=1.0, secret_key="s3cr3t",
                planner_shadow_store_sanitized_question=False, planner_shadow_store_plan=True,
                planner_shadow_plan_retention_days=14, ovh_model_main=MAIN, ovh_model_simple=SIMPLE,
                planner_shadow_executor="inprocess", planner_shadow_max_concurrency=4, ovh_base_url="")
    base.update(over)
    return SimpleNamespace(**base)


def _resp(status="answered", goal_type="count"):
    return SimpleNamespace(status=status, analysis={"goal_type": goal_type},
                           intent="reporting", duration_ms=42)


def _interp(*types_ids, deps=None):
    goals = []
    for i, t in enumerate(types_ids, start=1):
        g = {"id": f"g{i}", "priority": i, "type": t, "intent_text": "x", "entity_ref": "concept:customer"}
        if deps and f"g{i}" in deps:
            g["depends_on"] = deps[f"g{i}"]
        goals.append(g)
    return validate_interpretation({"plan_schema_version": "1.2", "unresolved_terms": [], "goals": goals})


def _plan(interp=None, status="ok", repair=None):
    return S.ShadowPlanResult(interp=interp, status=status, latency_ms=10, repair=repair)


def _env(question, fallback_view, *, fallback_status="answered", **over):
    e = dict(tenant_id=1, space_id=None, conversation_id=None, connection_id=7,
             request_id="req-123", question_hash="h", safe_question=question,
             question_sanitized=None, fallback_view=fallback_view, fallback_status=fallback_status,
             planner_mode="shadow", sample_rate=1.0)
    e.update(over)
    return e


def _run(question, plan_fn, fallback_view, *, fallback_status="answered", store_plan=True):
    sess = FakeSession()
    row = S.run_shadow_evaluation(_env(question, fallback_view, fallback_status=fallback_status),
                                  session=sess, plan_fn=plan_fn, catalog=object(),
                                  main_model=MAIN, simple_model=SIMPLE, store_plan=store_plan)
    return row, sess


# === Non-blocage / isolation ===============================================
def test_shadow_dispatch_does_not_touch_response():
    resp = _resp()
    before = dict(resp.__dict__)
    exe = RecExecutor()
    out = S.dispatch_shadow(response=resp, question="combien de clients", tenant_id=1,
                            connection_id=7, executor=exe, settings=_settings())
    assert out == "submitted" and resp.__dict__ == before      # réponse jamais mutée
    assert len(exe.envelopes) == 1


def test_inprocess_executor_nonblocking_and_isolated():
    ran = threading.Event()
    def runner(env):
        ran.set()
        raise RuntimeError("boom shadow")           # doit être avalé
    exe = InProcessShadowExecutor(max_concurrency=2, runner=runner)
    t0 = time.perf_counter()
    assert exe.submit({"x": 1}) == "submitted"
    assert (time.perf_counter() - t0) < 0.5          # submit ne bloque pas
    assert ran.wait(2.0)                             # le runner a bien tourné
    time.sleep(0.05)                                 # laisse l'exception s'avaler


def test_timeout_status_produces_only_telemetry():
    row, _ = _run("combien de clients", lambda m, q, c: _plan(status="timeout"),
                  {"status": "answered", "analysis": {"goal_type": "count"}})
    assert row.llm_status == "timeout" and row.comparison_outcome == C.LLM_ERROR


def test_contract_error_produces_only_telemetry():
    row, _ = _run("combien de clients", lambda m, q, c: _plan(status="contract_error"),
                  {"status": "answered", "analysis": {"goal_type": "count"}})
    assert row.llm_status == "contract_error" and row.comparison_outcome == C.LLM_ERROR


# === Classification des divergences ========================================
def test_material_divergence():
    row, _ = _run("combien de clients", lambda m, q, c: _plan(_interp("trend")),
                  {"status": "answered", "analysis": {"goal_type": "count"}})
    assert row.comparison_outcome == C.MATERIAL_DIVERGENCE
    assert row.review_status == "sampled_for_review"


def test_equivalent_outcome():
    row, _ = _run("combien de clients", lambda m, q, c: _plan(_interp("count")),
                  {"status": "answered", "analysis": {"goal_type": "count"}})
    assert row.comparison_outcome == C.EQUIVALENT


def test_fallback_error_outcome():
    row, _ = _run("combien de clients", lambda m, q, c: _plan(_interp("count")),
                  {"status": "error"}, fallback_status="error")
    assert row.comparison_outcome == C.FALLBACK_ERROR


def test_comparator_structure_not_json_equality():
    # deux plans équivalents avec JSON différent (ordre/ids/libellés) → pas material
    a = project_llm(_interp("count"))
    b = project_llm(_interp("aggregate"))            # équivalent via règle versionnée
    assert C.compare(a, b, llm_status="ok", fallback_status="ok").outcome in (C.IDENTICAL, C.EQUIVALENT)


# === unknown ≠ empty ========================================================
def test_projection_unknown_distinct_from_empty():
    llm = project_llm(_interp("count"))              # unresolved explicitement VIDE
    fb = project_fallback({"status": "answered"})     # unresolved INCONNU
    assert llm.unresolved_roles == frozenset()        # empty
    assert fb.unresolved_roles is None                # unknown
    facet = C.compare(llm, fb, llm_status="ok", fallback_status="ok").facets["unresolved_roles"]
    assert facet["state"] == "not_comparable"
    assert facet["llm"] == [] and facet["fallback"] is None   # distinction PORTÉE DANS LES DONNÉES


# === Routeur ================================================================
def test_router_candidate_recorded_simple():
    row, _ = _run("combien de clients", lambda m, q, c: _plan(_interp("count")),
                  {"status": "answered", "analysis": {"goal_type": "count"}})
    assert row.candidate_model == SIMPLE and row.routing_tier == "simple"
    assert row.routing_matched_rule and not row.escalated


def test_router_escalation_recorded():
    def plan_fn(model, q, c):
        if model == SIMPLE:
            return _plan(_interp("segmentation", "affinity", deps={"g2": ["g1"]}))  # trop complexe
        return _plan(_interp("segmentation", "affinity", deps={"g2": ["g1"]}))
    row, _ = _run("combien de clients", plan_fn,
                  {"status": "answered", "analysis": {"goal_type": "segmentation"}})
    assert row.escalated and row.previous_model == SIMPLE and row.candidate_model == MAIN
    assert row.escalation_reason and row.routing_matched_rule.startswith("escalation:")


# === Réparation =============================================================
def test_repair_recorded_in_telemetry():
    repair = {"type": "goal_id_renumber", "duplicates": ["g1"], "n_goals": 2}
    row, _ = _run("combien de clients", lambda m, q, c: _plan(_interp("count"), repair=repair),
                  {"status": "answered", "analysis": {"goal_type": "count"}})
    assert row.repair_applied and row.repair_type == "goal_id_renumber"
    assert row.repair_details_json["duplicates"] == ["g1"]


# === Versions ===============================================================
def test_all_versions_persisted():
    row, _ = _run("combien de clients", lambda m, q, c: _plan(_interp("count")),
                  {"status": "answered", "analysis": {"goal_type": "count"}})
    assert row.interpretation_schema_version == "1.2" and row.goal_types_version == "1.0"
    assert row.router_version == "1.0"
    assert row.comparator_version == "1.1" and row.projection_version == "1.1"   # promotion capabilities (#7)


def test_capabilities_informative_when_provisional():
    """Sans résolution C6, des capabilities différentes NE provoquent PAS material."""
    from app.analysis.shadow.projection import ComparableProjection
    llm = ComparableProjection(source="llm", primary_goal_type="count", goal_types=frozenset({"count"}),
                               goal_count=1, dependency_edges=frozenset(), unresolved_roles=frozenset(),
                               required_capabilities=frozenset({"a"}), capabilities_provisional=True)
    fb = ComparableProjection(source="fallback", primary_goal_type="count",
                              required_capabilities=frozenset({"b"}), capabilities_provisional=True)
    out = C.compare(llm, fb, llm_status="ok", fallback_status="ok")
    assert out.outcome != C.MATERIAL_DIVERGENCE
    assert out.facets["required_capabilities"]["material"] is False


def test_capabilities_material_when_resolved_both_sides():
    """Résolution C6 des deux côtés : des capabilities divergentes → material_divergence (#7)."""
    from app.analysis.shadow.projection import ComparableProjection
    llm = ComparableProjection(source="llm", primary_goal_type="count", goal_types=frozenset({"count"}),
                               goal_count=1, dependency_edges=frozenset(), unresolved_roles=frozenset(),
                               required_capabilities=frozenset({"measure:m=available"}), capabilities_provisional=False)
    fb = ComparableProjection(source="fallback", primary_goal_type="count", goal_types=frozenset({"count"}),
                              goal_count=1, dependency_edges=frozenset(), unresolved_roles=frozenset(),
                              required_capabilities=frozenset({"measure:m=unresolved"}), capabilities_provisional=False)
    out = C.compare(llm, fb, llm_status="ok", fallback_status="ok")
    assert out.outcome == C.MATERIAL_DIVERGENCE
    assert out.facets["required_capabilities"]["material"] is True


# === Sampling ===============================================================
def test_sampling_respected():
    assert all(S.is_sampled(f"r{i}", 1.0) for i in range(20))
    assert not any(S.is_sampled(f"r{i}", 0.0) for i in range(20))
    # déterministe : même id → même décision
    assert S.is_sampled("stable-id", 0.5) == S.is_sampled("stable-id", 0.5)
    assert S.dispatch_shadow(response=_resp(), question="q", tenant_id=1, connection_id=7,
                             executor=RecExecutor(), settings=_settings(planner_shadow_sample_rate=0.0)) == "disabled"


# === Isolation des modes ====================================================
def test_legacy_is_noop():
    exe = RecExecutor()
    assert S.dispatch_shadow(response=_resp(), question="q", tenant_id=1, connection_id=7,
                             executor=exe, settings=_settings(planner_mode="legacy")) == "legacy"
    assert exe.envelopes == []


@pytest.mark.parametrize("mode", ["active", "canary"])
def test_active_canary_not_executable(mode):
    exe = RecExecutor()
    out = S.dispatch_shadow(response=_resp(), question="q", tenant_id=1, connection_id=7,
                            executor=exe, settings=_settings(planner_mode=mode))
    assert out == "unsupported_mode" and exe.envelopes == []     # jamais un shadow déguisé


# === Confidentialité ========================================================
def test_question_hash_is_hmac_tenant_scoped():
    import hashlib
    q = "combien de clients"
    h = S.question_hash(q, tenant_id=1, secret="s3cr3t")
    assert h != hashlib.sha256(q.encode()).hexdigest()          # pas un simple SHA
    assert h == S.question_hash(q, 1, "s3cr3t")                  # stable
    assert h != S.question_hash(q, 2, "s3cr3t")                  # tenant-scoped
    assert h != S.question_hash(q, 1, "autre")                   # dépend du secret


def test_dispatch_does_not_store_raw_question():
    exe = RecExecutor()
    S.dispatch_shadow(response=_resp(), question="secret métier confidentiel", tenant_id=1,
                      connection_id=7, executor=exe, settings=_settings())
    env = exe.envelopes[0]
    assert env["question_hash"] and env["question_sanitized"] is None
    assert "secret métier confidentiel" not in str({k: v for k, v in env.items() if k != "safe_question"})


# === Séparation des domaines de persistance =================================
def test_shadow_only_writes_shadow_table():
    row, sess = _run("combien de clients", lambda m, q, c: _plan(_interp("count")),
                     {"status": "answered", "analysis": {"goal_type": "count"}})
    assert len(sess.added) == 1 and isinstance(sess.added[0], PlannerShadowEvaluation)
    assert sess.commits == 1


def test_analysis_plans_table_does_not_exist():
    from app.core.db import Base
    assert "planner_shadow_evaluations" in Base.metadata.tables
    assert "analysis_plans" not in Base.metadata.tables      # pas encore créée → pollution impossible
    assert "analysis_runs" not in Base.metadata.tables


# === Worker : sa PROPRE session ============================================
def test_worker_opens_its_own_session():
    made = {}
    def factory():
        s = FakeSession(); made["session"] = s; return s
    env = _env("combien de clients", {"status": "answered", "analysis": {"goal_type": "count"}})
    S.run_shadow_from_envelope(
        env, session_factory=factory, plan_fn=lambda m, q, c: _plan(_interp("count")),
        catalog_builder=lambda sess, envp: (object(), None), settings=_settings())
    assert made["session"].commits == 1 and made["session"].closed is True   # session propre, fermée
