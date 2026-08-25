"""Phase 2 — C5 : orchestration du Shadow Planner.

Point d'entrée `dispatch_shadow(...)` appelé par le chat APRÈS que la réponse est
construite → il ne peut ni la muter ni la retarder. Le travail réel tourne dans
l'exécuteur (thread/RQ), sur une session DB PROPRE (jamais celle du chat).

Modes exécutables : `legacy`, `shadow`. `active`/`canary` sont RÉSERVÉS et
refusés explicitement (`unsupported_mode`) — jamais un shadow déguisé.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.analysis.contracts import (
    GOAL_TYPES_VERSION,
    INTERPRETATION_SCHEMA_VERSION,
    ContractError,
    repair_goal_ids_report,
    validate_interpretation,
)
from app.analysis.interpreter import (
    PLANNER_PROMPT_VERSION,
    PLANNER_SYSTEM,
    PlannerCatalog,
    build_user_prompt,
)
from app.analysis.planner_privacy import sanitize_question
from app.analysis.routing import ROUTER_VERSION, RoutingDecision, plan_is_simple_eligible, preroute
from app.analysis.schema_models import interpretation_json_schema
from app.analysis.shadow.comparator import COMPARATOR_VERSION, MATERIAL_DIVERGENCE, compare
from app.analysis.shadow.projection import PROJECTION_VERSION, project_fallback, project_llm
from app.core.logging import get_logger

log = get_logger("noreon.planner.shadow")

EXECUTABLE_MODES = {"legacy", "shadow"}
_RESERVED_MODES = {"active", "canary"}
_OVH_TOKEN_ENV = "OVH_AI_ENDPOINTS_ACCESS_TOKEN"


# --- confidentialité + sampling ---------------------------------------------
def question_hash(safe_question: str, tenant_id: int, secret: str) -> str:
    """HMAC-SHA256 tenant-scoped (correctif #7) — pas un simple SHA attaquable
    par dictionnaire sur des questions courtes et prévisibles."""
    msg = f"{tenant_id}:{safe_question}".encode()
    return hmac.new((secret or "").encode(), msg, hashlib.sha256).hexdigest()


def is_sampled(request_id: str, rate: float) -> bool:
    """Échantillonnage DÉTERMINISTE par request_id (aucun `random`) → reproductible."""
    if rate >= 1.0:
        return True
    if rate <= 0.0:
        return False
    h = hashlib.sha256((request_id or "").encode()).hexdigest()
    return (int(h[:8], 16) / 0xFFFFFFFF) < rate


# --- résultat d'un appel de planification instrumenté -----------------------
@dataclass
class ShadowPlanResult:
    interp: object | None = None
    status: str = "skipped"            # ok|contract_error|network_error|provider_error|timeout|skipped
    latency_ms: int | None = None
    tokens_prompt: int | None = None
    tokens_completion: int | None = None
    tokens_total: int | None = None
    repair: dict | None = None
    error_kind: str | None = None
    error_detail: str | None = None


# --- vue fallback (projetable) ----------------------------------------------
def build_fallback_view(response) -> dict:
    """Extrait du `ChatResponse` une vue JSON-sérialisable pour la projection.
    Aucune donnée brute : statut, type d'analyse éventuel, latence."""
    status = getattr(response, "status", None)
    analysis = getattr(response, "analysis", None)
    return {
        "status": status,
        "analysis": analysis if isinstance(analysis, dict) else None,
        "goal_type_hint": getattr(response, "intent", None),
        "latency_ms": getattr(response, "duration_ms", None),
    }


# --- point d'entrée (thread requête, APRÈS la réponse) ----------------------
def dispatch_shadow(*, response, question: str, tenant_id: int, connection_id: int | None,
                    executor, settings, request_id: str | None = None,
                    space_id: int | None = None, conversation_id: int | None = None) -> str:
    """Non bloquant, best-effort. Ne lève JAMAIS : renvoie un statut de dispatch."""
    try:
        mode = (settings.planner_mode or "legacy").lower()
        if mode == "legacy":
            return "legacy"
        if mode not in EXECUTABLE_MODES:
            # active/canary : refus EXPLICITE — jamais un shadow déguisé.
            log.error("planner_mode_unsupported mode=%s (exécutables: legacy|shadow) — "
                      "aucune évaluation, le planner n'est PAS actif", mode)
            return "unsupported_mode"
        rate = float(settings.planner_shadow_sample_rate)
        if rate <= 0.0:
            return "disabled"
        request_id = request_id or uuid.uuid4().hex
        if not is_sampled(request_id, rate):
            return "not_sampled"

        safe_q, _ = sanitize_question(question)
        envelope = {
            "tenant_id": tenant_id, "space_id": space_id, "conversation_id": conversation_id,
            "connection_id": connection_id, "request_id": request_id,
            "safe_question": safe_q,
            "question_hash": question_hash(safe_q, tenant_id, settings.secret_key),
            "question_sanitized": safe_q if settings.planner_shadow_store_sanitized_question else None,
            "fallback_view": build_fallback_view(response),
            "fallback_status": getattr(response, "status", None),
            "planner_mode": mode, "sample_rate": rate,
        }
        return executor.submit(envelope)
    except Exception as exc:  # noqa: BLE001 - le dispatch ne peut jamais impacter le chat
        log.warning("dispatch_shadow isolé après erreur : %s", exc)
        return "error_isolated"


# --- catalogue provisoire (jusqu'à C6/CapabilityResolver) -------------------
def _ref_token(*parts: str) -> str:
    raw = "_".join(p for p in parts if p)
    return re.sub(r"[^a-z0-9_]", "_", raw.lower()).strip("_") or "x"


_NUMERIC = ("int", "float", "numeric", "double", "decimal", "real", "money", "serial")


def build_provisional_catalog(session, connection_id: int) -> PlannerCatalog | None:
    """Catalogue best-effort dérivé du snapshot (PROVISOIRE — remplacé par le vrai
    CapabilityResolver en C6). Renvoie None si aucun schéma scanné."""
    from app.services.schema_context import current_snapshot

    snap = current_snapshot(session, connection_id)
    if snap is None or not snap.tables:
        return None
    concepts, metrics, dimensions = [], [], []
    for t in snap.tables:
        concepts.append({"entity_ref": f"concept:{_ref_token(t.table_name)}", "entity_label": t.table_name})
        for c in getattr(t, "columns", []) or []:
            dt = (c.data_type or "").lower()
            ref_tok = _ref_token(t.table_name, c.name)
            if any(n in dt for n in _NUMERIC):
                metrics.append({"metric_ref": f"metric:{ref_tok}", "metric_label": c.name})
            else:
                dimensions.append({"dimension_ref": f"dimension:{ref_tok}", "dimension_label": c.name})
    return PlannerCatalog(concepts=concepts, metrics=metrics, dimensions=dimensions,
                          relations=[], stats={}, domain=getattr(snap, "domain", "") or "")


# --- plan_fn instrumenté (prod) ---------------------------------------------
def _build_plan_fn(settings):
    """Construit `plan_fn(model, question, catalog) -> ShadowPlanResult` à partir
    de la config OVHcloud. Toute erreur devient un STATUT, jamais une exception."""
    from app.llm.providers import OVHcloudProvider

    base = settings.ovh_base_url
    token = os.getenv(_OVH_TOKEN_ENV, "")
    schema = interpretation_json_schema()
    if not base or not token:
        def _skip(model, question, catalog):
            return ShadowPlanResult(status="skipped", error_kind="config",
                                    error_detail="config OVHcloud incomplète")
        return _skip

    providers = {settings.ovh_model_main: OVHcloudProvider(model=settings.ovh_model_main, api_key=token, base_url=base),
                 settings.ovh_model_simple: OVHcloudProvider(model=settings.ovh_model_simple, api_key=token, base_url=base)}

    def plan_fn(model, question, catalog) -> ShadowPlanResult:
        prov = providers.get(model) or OVHcloudProvider(model=model, api_key=token, base_url=base)
        safe_q, _ = sanitize_question(question)
        user = build_user_prompt(catalog, safe_q)
        t0 = time.perf_counter()
        try:
            raw = prov.plan(system=PLANNER_SYSTEM, user=user, json_schema=schema)
        except Exception as exc:  # noqa: BLE001 - réseau/HTTP/timeout
            kind = "timeout" if "timeout" in type(exc).__name__.lower() else "network_error"
            return ShadowPlanResult(status=kind, error_kind=kind, error_detail=type(exc).__name__,
                                    latency_ms=int((time.perf_counter() - t0) * 1000))
        latency = int((time.perf_counter() - t0) * 1000)
        import json as _json
        try:
            data = _json.loads(raw)
        except Exception as exc:  # noqa: BLE001
            return ShadowPlanResult(status="contract_error", error_kind="contract",
                                    error_detail=f"json_decode: {exc}", latency_ms=latency)
        repaired, repair = repair_goal_ids_report(data)
        try:
            interp = validate_interpretation(repaired)
        except ContractError as exc:
            return ShadowPlanResult(status="contract_error", error_kind="contract",
                                    error_detail=f"{exc.code}@{exc.path}", latency_ms=latency, repair=repair)
        usage = getattr(prov, "last_usage", None) or {}
        return ShadowPlanResult(interp=interp, status="ok", latency_ms=latency, repair=repair,
                                tokens_prompt=usage.get("prompt_tokens"),
                                tokens_completion=usage.get("completion_tokens"),
                                tokens_total=usage.get("total_tokens"))
    return plan_fn


# --- cœur : évaluation shadow (session injectée) ----------------------------
def run_shadow_evaluation(envelope: dict, *, session, plan_fn, catalog,
                          main_model: str, simple_model: str,
                          store_plan: bool = True, plan_retention_days: int = 14, now=None):
    """Route + planifie (instrumenté) + projette + compare + persiste UNE ligne
    dans `planner_shadow_evaluations`. Ne cible jamais une autre table."""
    from app.models.planner_shadow import PlannerShadowEvaluation

    now = now or datetime.now(timezone.utc)
    question = envelope["safe_question"]
    fallback_view = envelope.get("fallback_view") or {}
    fallback_status = _norm_fallback_status(envelope.get("fallback_status"))

    # Routage instrumenté (reproduit route_and_plan avec télémétrie complète).
    dec = preroute(question, main_model=main_model, simple_model=simple_model)
    res = plan_fn(dec.selected_model, question, catalog) if catalog is not None else ShadowPlanResult(
        status="skipped", error_kind="no_catalog", error_detail="aucun schéma scanné")
    escalated = False
    if catalog is not None and dec.selected_model == simple_model and res.interp is not None:
        ok, reason = plan_is_simple_eligible(res.interp)
        if not ok:
            previous = dec.selected_model
            res = plan_fn(main_model, question, catalog)
            dec = RoutingDecision(main_model, "escalade après plan 20b non éligible",
                                  previous_model=previous, escalation_reason=reason,
                                  matched_rule=f"escalation:{reason}", tier="complex")
            escalated = True

    llm_status = res.status
    llm_proj = project_llm(res.interp) if res.interp is not None else None
    fb_proj = project_fallback(fallback_view)
    comparison = compare(llm_proj, fb_proj, llm_status=llm_status, fallback_status=fallback_status)

    plan_json = None
    purge_after = None
    if store_plan and res.interp is not None:
        plan_json = {"goals": [g.raw for g in res.interp.goals],
                     "unresolved_terms": list(res.interp.unresolved_terms)}
        purge_after = now + timedelta(days=plan_retention_days)

    row = PlannerShadowEvaluation(
        tenant_id=envelope["tenant_id"], space_id=envelope.get("space_id"),
        conversation_id=envelope.get("conversation_id"), connection_id=envelope.get("connection_id"),
        request_id=envelope["request_id"], question_hash=envelope["question_hash"],
        question_sanitized=envelope.get("question_sanitized"),
        planner_mode=envelope.get("planner_mode", "shadow"), sample_rate=envelope.get("sample_rate", 1.0),
        candidate_model=dec.selected_model, routing_reason=dec.routing_reason,
        routing_matched_rule=dec.matched_rule, routing_tier=dec.tier,
        escalated=escalated, previous_model=dec.previous_model, escalation_reason=dec.escalation_reason,
        interpretation_schema_version=INTERPRETATION_SCHEMA_VERSION, goal_types_version=GOAL_TYPES_VERSION,
        router_version=ROUTER_VERSION, planner_prompt_version=PLANNER_PROMPT_VERSION,
        comparator_version=COMPARATOR_VERSION, projection_version=PROJECTION_VERSION,
        llm_status=llm_status, fallback_status=fallback_status,
        llm_plan_json=plan_json, plan_purge_after=purge_after,
        llm_projection_json=llm_proj.to_json() if llm_proj else None,
        fallback_projection_json=fb_proj.to_json(),
        comparison_outcome=comparison.outcome, comparison_json=comparison.to_json(),
        repair_applied=res.repair is not None,
        repair_type=(res.repair or {}).get("type"),
        repair_details_json=res.repair,
        llm_latency_ms=res.latency_ms, fallback_latency_ms=fallback_view.get("latency_ms"),
        tokens_prompt=res.tokens_prompt, tokens_completion=res.tokens_completion,
        tokens_total=res.tokens_total,
        error_kind=res.error_kind, error_detail=(res.error_detail or "")[:2000] or None,
        review_status=("sampled_for_review" if comparison.outcome == MATERIAL_DIVERGENCE else "none"),
    )
    session.add(row)
    session.commit()
    return row


def _norm_fallback_status(status: str | None) -> str:
    if status in {None, "answered", "clarification"}:
        return "ok"
    return "error"


# --- worker : sa PROPRE session ---------------------------------------------
def run_shadow_from_envelope(envelope: dict, *, session_factory=None, plan_fn=None,
                             catalog_builder=None, settings=None, now=None):
    """Entrée du worker (InProcess ou RQ). Ouvre SA PROPRE session DB — ne reçoit
    JAMAIS celle de la requête chat."""
    if settings is None:
        from app.core.config import settings as settings
    if session_factory is None:
        from app.core.db import SessionLocal
        session_factory = SessionLocal
    session = session_factory()                       # session PROPRE
    try:
        catalog = (catalog_builder or build_provisional_catalog)(session, envelope.get("connection_id"))
        pf = plan_fn or _build_plan_fn(settings)
        return run_shadow_evaluation(
            envelope, session=session, plan_fn=pf, catalog=catalog,
            main_model=settings.ovh_model_main, simple_model=settings.ovh_model_simple,
            store_plan=settings.planner_shadow_store_plan,
            plan_retention_days=settings.planner_shadow_plan_retention_days, now=now)
    finally:
        session.close()
