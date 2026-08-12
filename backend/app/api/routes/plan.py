"""Plan d'action — les décisions RETENUES depuis les analyses, suivies dans le
temps : retenue → mise en œuvre → (mesure) ; ou abandonnée.

C'est le pendant « on décide de faire » de la Conversation « on comprend ». Une
décision entre ici quand un décideur la retient depuis une réponse d'analyse.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Principal, current_principal
from app.core.db import get_db
from app.models.connection import Connection
from app.models.decision import DecisionRecord
from app.models.measurement import MeasurementPlan, MeasurementRun
from app.schemas import PlanItemUpdate

router = APIRouter(prefix="/plan", tags=["plan"])

# Cycle de vie d'une action. « successful » ne se pose PAS d'un clic : c'est la
# mesure qui classe le résultat (objectif atteint / non atteint / inconclusif).
_ACTIVE = ("retained", "implemented", "measured")
_ALLOWED = {"retained", "implemented", "abandoned", "closed"}


def _plan_of(db: Session, decision_id: int) -> MeasurementPlan | None:
    return db.execute(
        select(MeasurementPlan).where(MeasurementPlan.decision_id == decision_id)
    ).scalars().first()


def _run_dict(r: MeasurementRun) -> dict:
    return {
        "id": r.id, "horizon_days": r.horizon_days,
        "raw_delta": r.raw_delta, "control_delta": r.control_delta,
        "adjusted_delta": r.adjusted_delta, "result": r.result,
        "limitations": r.limitations or [],
        "measured_at": r.measured_at.isoformat() if r.measured_at else None,
    }


def _dict(db: Session, d: DecisionRecord) -> dict:
    # Libellé d'analyse MÉTIER (« Ventes ») — jamais le nom physique de la source.
    from app.services.concepts import subject_domain
    plan = _plan_of(db, d.id)
    latest = plan.runs[-1] if (plan and plan.runs) else None
    return {
        "id": d.id, "role": d.role,
        "recommendation": d.recommendation, "status": d.status, "note": d.note,
        "connection_id": d.connection_id,
        "analysis_label": subject_domain(d.subject or ""),
        "created_at": d.created_at.isoformat() if d.created_at else None,
        "measurement": None if plan is None else {
            "measure_type": plan.measure_type,
            "metric_label": plan.metric_label,
            "threshold": plan.threshold,
            "implemented_at": plan.implemented_at.isoformat() if plan.implemented_at else None,
            "baseline_frozen": plan.baseline_target is not None,
            "has_control": bool(plan.control_scope and plan.control_scope.get("values")),
            "latest_run": _run_dict(latest) if latest else None,
            "runs_count": len(plan.runs) if plan else 0,
        },
    }


@router.get("")
def list_plan(
    include_closed: bool = False,
    db: Session = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> list[dict]:
    """Les actions du plan (tenant). Par défaut, seulement les actions ACTIVES
    (retenues / en cours) ; `include_closed` ajoute réussies et abandonnées."""
    rows = db.execute(
        select(DecisionRecord).where(DecisionRecord.tenant_id == principal.tenant_id)
        .order_by(DecisionRecord.created_at.desc())
    ).scalars().all()
    items = [_dict(db, d) for d in rows]
    if not include_closed:
        items = [it for it in items if it["status"] in _ACTIVE]
    return items


@router.patch("/{item_id}")
def update_plan_item(
    item_id: int, payload: PlanItemUpdate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> dict:
    """Fait avancer une action (retenue → mise en œuvre → abandonnée). Le passage
    en « réussie » relève de la MESURE, pas d'une déclaration manuelle."""
    d = db.execute(
        select(DecisionRecord).where(
            DecisionRecord.id == item_id, DecisionRecord.tenant_id == principal.tenant_id
        )
    ).scalar_one_or_none()
    if d is None:
        raise HTTPException(status_code=404, detail="Action introuvable.")
    if payload.status is not None:
        if payload.status == "successful":
            raise HTTPException(
                status_code=422,
                detail="« Réussie » est posé par la mesure du résultat, pas manuellement.",
            )
        if payload.status not in _ALLOWED:
            raise HTTPException(status_code=422, detail="Statut invalide.")
        # Point de rupture RÉEL : à la mise en œuvre, on fige le baseline pré-action.
        if payload.status == "implemented" and d.status != "implemented":
            plan = _plan_of(db, d.id)
            if plan is not None and plan.implemented_at is None:
                from app.services.connections import get_source_adapter
                from app.services import measurement as meas
                conn = db.get(Connection, d.connection_id)
                if conn is not None:
                    meas.freeze_baseline(db, plan, get_source_adapter(conn))
        d.status = payload.status
    if payload.note is not None:
        d.note = payload.note
    db.commit()
    return _dict(db, d)


@router.get("/{item_id}/measurement")
def measurement_detail(
    item_id: int,
    db: Session = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> dict:
    """Drill-down de PREUVE : protocole figé, fenêtres, valeurs, écart contrôlé,
    sélection des témoins (avant observation), limites, hash de requête."""
    import hashlib
    from datetime import timedelta

    d = db.execute(
        select(DecisionRecord).where(
            DecisionRecord.id == item_id, DecisionRecord.tenant_id == principal.tenant_id
        )
    ).scalar_one_or_none()
    if d is None:
        raise HTTPException(status_code=404, detail="Action introuvable.")
    plan = _plan_of(db, d.id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Aucun protocole de mesure.")

    def _qhash(sql: str | None) -> str | None:
        return hashlib.sha256(sql.encode()).hexdigest()[:12] if sql else None

    impl = plan.implemented_at
    baseline_window = observation_window = None
    if impl is not None:
        bstart = impl - timedelta(days=plan.baseline_window_days)
        baseline_window = {"from": bstart.date().isoformat(), "to": impl.date().isoformat()}

    runs = []
    for r in plan.runs:
        obs = None
        if impl is not None:
            oend = impl + timedelta(days=r.horizon_days)
            obs = {"from": impl.date().isoformat(), "to": oend.date().isoformat()}
        runs.append({
            "id": r.id, "horizon_days": r.horizon_days,
            "observation_window": obs,
            "baseline_target": r.baseline_target, "baseline_control": r.baseline_control,
            "observed_target": r.observed_target, "observed_control": r.observed_control,
            "raw_delta": r.raw_delta, "control_delta": r.control_delta,
            "adjusted_delta": r.adjusted_delta, "result": r.result,
            "limitations": r.limitations or [], "query_hash": _qhash(r.observation_sql),
            "measured_at": r.measured_at.isoformat() if r.measured_at else None,
        })

    return {
        "action": {"role": d.role, "recommendation": d.recommendation, "status": d.status},
        "protocol": {
            "measure_type": plan.measure_type,
            "metric_label": plan.metric_label, "metric_concept_id": plan.metric_concept_id,
            "target": (plan.scope or {}).get("values", []),
            "target_table": (plan.scope or {}).get("table"),
            "comparison": plan.comparison,
            "control_selection": plan.control_selection,
            "threshold": plan.threshold, "protocol_version": plan.protocol_version,
            "implemented_at": impl.isoformat() if impl else None,
            "baseline_window": baseline_window,
            "baseline_target": plan.baseline_target, "baseline_control": plan.baseline_control,
            "baseline_query_hash": _qhash(plan.baseline_sql),
        },
        "runs": runs,
    }


@router.post("/{item_id}/measure")
def measure_plan_item(
    item_id: int, horizon_days: int | None = None,
    db: Session = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> dict:
    """Crée un RUN de mesure (jamais d'écrasement) et classe le résultat CONTRÔLÉ."""
    d = db.execute(
        select(DecisionRecord).where(
            DecisionRecord.id == item_id, DecisionRecord.tenant_id == principal.tenant_id
        )
    ).scalar_one_or_none()
    if d is None:
        raise HTTPException(status_code=404, detail="Action introuvable.")
    plan = _plan_of(db, d.id)
    if plan is None:
        raise HTTPException(status_code=422, detail="Aucun protocole de mesure pour cette action.")
    if plan.implemented_at is None:
        raise HTTPException(status_code=422, detail="Action pas encore mise en œuvre : baseline non figé.")
    from app.services.connections import get_source_adapter
    from app.services import measurement as meas
    conn = db.get(Connection, d.connection_id)
    meas.run_measurement(db, plan, get_source_adapter(conn), horizon_days=horizon_days)
    d.status = "measured" if d.status != "abandoned" else d.status
    db.commit()
    return _dict(db, d)
