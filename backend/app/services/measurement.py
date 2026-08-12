"""Protocole de mesure d'une action — approche C.

- À la RÉTENTION : `design_plan` classe l'action (impact | performance | completion
  | diagnostic) et pose un `MeasurementPlan` SANS valeur numérique.
- À la MISE EN ŒUVRE : `freeze_baseline` enregistre `implemented_at` et calcule +
  FIGE le baseline (cible + témoins) côté backend, sur la fenêtre AVANT l'action.
- À l'ÉCHÉANCE : `run_measurement` crée un `MeasurementRun` (jamais d'écrasement),
  compare cible vs témoins, classe le résultat — jamais « réussie » automatique.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.decision import DecisionRecord
from app.models.measurement import MeasurementPlan, MeasurementRun

# Le KPI de l'ACTION n'est pas celui du diagnostic. On classe l'action.
_COMPLETION = ("audit", "auditer", "vérifier", "verifier", "diagnostiquer", "analyser sur place", "contrôler")
_PERFORMANCE = ("prévision", "prevision", "prévisions", "forecast", "budget", "planifier")
_IMPACT = ("relance", "promotion", "réassort", "reassort", "campagne", "remise", "plan commercial", "animer", "booster")


def classify_action(recommendation: str) -> str:
    r = (recommendation or "").lower()
    if any(w in r for w in _PERFORMANCE):
        return "performance"
    if any(w in r for w in _IMPACT):
        return "impact"
    if any(w in r for w in _COMPLETION):
        return "completion"
    return "impact"


def design_plan(db: Session, decision: DecisionRecord, *, scope: dict | None = None,
                control_scope: dict | None = None, threshold: float = 0.02) -> MeasurementPlan:
    """Pose le PROTOCOLE (pas de baseline numérique encore)."""
    mtype = classify_action(decision.recommendation)
    plan = MeasurementPlan(
        decision_id=decision.id, tenant_id=decision.tenant_id, connection_id=decision.connection_id,
        measure_type=mtype, metric_concept_id="revenue", metric_label="Chiffre d'affaires",
        scope=scope or {}, control_scope=control_scope, threshold=threshold,
        comparison="matched_control" if control_scope else "none",
    )
    db.add(plan)
    db.flush()
    return plan


def _sum(adapter, connection_id: int, scope: dict, values: list[str], start, end) -> tuple[float | None, str]:
    """SUM(metric) sur un périmètre + une fenêtre — SQL réel, auditable."""
    table = scope.get("table"); dim = scope.get("dim_col")
    metric = scope.get("metric_col"); date_col = scope.get("date_col")
    if not (table and dim and metric and date_col and values):
        return None, ""
    in_list = ", ".join("'" + str(v).replace("'", "") + "'" for v in values)
    sql = (
        f"SELECT sum({metric}) FROM {table} "
        f"WHERE {dim} IN ({in_list}) AND {date_col} >= '{start.isoformat()}' "
        f"AND {date_col} < '{end.isoformat()}'"
    )
    res = adapter.run_query(sql, connection_id=connection_id)
    val = res.rows[0][0] if res.rows and res.rows[0] else None
    return (float(val) if val is not None else None), getattr(res, "guarded_sql", sql)


def _pretrend(adapter, connection_id: int, scope: dict, values: list[str], start, end) -> float | None:
    """Croissance moitié-1 → moitié-2 de la fenêtre baseline (proxy de tendance)."""
    mid = start + (end - start) / 2
    a, _ = _sum(adapter, connection_id, scope, values, start, mid)
    b, _ = _sum(adapter, connection_id, scope, values, mid, end)
    if not a:
        return None
    return (b - a) / a


def freeze_baseline(db: Session, plan: MeasurementPlan, adapter, *, implemented_at: datetime | None = None) -> MeasurementPlan:
    """À la MISE EN ŒUVRE : fige le baseline pré-action ET la sélection des
    témoins (avant toute observation post-action — garantie méthodologique)."""
    impl = implemented_at or datetime.now(timezone.utc)
    plan.implemented_at = impl
    if plan.measure_type == "impact" and plan.scope:
        start = impl - timedelta(days=plan.baseline_window_days)
        tvals = plan.scope.get("values", [])
        bt, sql = _sum(adapter, plan.connection_id, plan.scope, tvals, start, impl)
        bc = None
        cvals = (plan.control_scope or {}).get("values") or []
        if cvals:
            bc, _ = _sum(adapter, plan.connection_id, plan.scope, cvals, start, impl)
            # Comparabilité PRÉ-ACTION : niveau (baseline) + pré-tendance. Figée ici,
            # AVANT de connaître le moindre résultat post-action.
            n_t = max(1, len(tvals)); n_c = max(1, len(cvals))
            lvl_t = (bt or 0) / n_t; lvl_c = (bc or 0) / n_c
            matching = max(0.0, 1 - abs(lvl_t - lvl_c) / lvl_t) if lvl_t else None
            pt_t = _pretrend(adapter, plan.connection_id, plan.scope, tvals, start, impl)
            pt_c = _pretrend(adapter, plan.connection_id, plan.scope, cvals, start, impl)
            pretrend = (max(0.0, 1 - abs(pt_t - pt_c) * 5) if (pt_t is not None and pt_c is not None) else None)
            plan.control_selection = {
                "control_ids": cvals,
                "matching_features": ["niveau de CA (baseline)", "pré-tendance"],
                "matching_score": round(matching, 3) if matching is not None else None,
                "pretrend_score": round(pretrend, 3) if pretrend is not None else None,
                "selection_at": impl.isoformat(),
            }
        plan.baseline_target = bt
        plan.baseline_control = bc
        plan.baseline_sql = sql
    plan.baseline_frozen_at = datetime.now(timezone.utc)
    db.flush()
    return plan


def run_measurement(db: Session, plan: MeasurementPlan, adapter, *, horizon_days: int | None = None) -> MeasurementRun:
    """À l'ÉCHÉANCE : crée un RUN (jamais d'écrasement), classe le résultat CONTRÔLÉ."""
    horizon = horizon_days or plan.observation_window_days
    limitations: list[str] = []
    run = MeasurementRun(
        plan_id=plan.id, horizon_days=horizon,
        baseline_target=plan.baseline_target, baseline_control=plan.baseline_control,
    )

    # Chaque type a SA sémantique de résultat — jamais « inconclusif » par défaut.
    if plan.measure_type != "impact":
        run.result = "a_qualifier"
        _MSG = {
            "completion": "Type « completion » : issue = terminé / non terminé (livrable + facteurs "
                          "vérifiés). À qualifier — pas mesurable par l'évolution du CA.",
            "diagnostic": "Type « diagnostic » : issue = hypothèse soutenue / écartée / inconclusive. "
                          "À qualifier depuis les vérifications de l'audit.",
            "performance": "Type « performance » : issue = objectif atteint / non atteint sur l'erreur "
                           "de prévision (MAPE avant/après). Données de prévision requises.",
        }
        limitations.append(_MSG.get(plan.measure_type, "Type à qualifier manuellement."))
        run.limitations = limitations
        db.add(run); db.flush()
        return run

    if plan.implemented_at is None or plan.baseline_target in (None, 0):
        run.result = "inconclusif"
        limitations.append("Baseline non figé ou nul : l'action n'a pas encore de point de rupture mesurable.")
        run.limitations = limitations
        db.add(run); db.flush()
        return run

    start = plan.implemented_at
    end = start + timedelta(days=horizon)
    ot, sql = _sum(adapter, plan.connection_id, plan.scope, plan.scope.get("values", []), start, end)
    oc = None
    if plan.control_scope and plan.control_scope.get("values"):
        oc, _ = _sum(adapter, plan.connection_id, plan.scope, plan.control_scope["values"], start, end)
    run.observed_target = ot
    run.observed_control = oc
    run.observation_sql = sql

    if ot is None:
        run.result = "inconclusif"
        limitations.append("Aucune donnée sur la fenêtre d'observation.")
        run.limitations = limitations
        db.add(run); db.flush()
        return run

    run.raw_delta = (ot - plan.baseline_target) / plan.baseline_target
    if plan.baseline_control not in (None, 0) and oc is not None:
        run.control_delta = (oc - plan.baseline_control) / plan.baseline_control
        run.adjusted_delta = run.raw_delta - run.control_delta   # points (fraction)
        effective = run.adjusted_delta
    else:
        run.control_delta = None
        run.adjusted_delta = None
        effective = run.raw_delta
        limitations.append("Sans groupe témoin : effet non isolé d'un mouvement de marché.")

    # Résultat CONTRÔLÉ — jamais « réussie » : objectif atteint / non atteint / inconclusif.
    run.result = "objectif_atteint" if effective >= plan.threshold else "objectif_non_atteint"
    if horizon < 14:
        limitations.append("Fenêtre d'observation courte : tendance non stabilisée.")
    run.limitations = limitations
    db.add(run); db.flush()
    return run
