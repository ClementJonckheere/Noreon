from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_owned_connection, require_analyst
from app.core.db import get_db
from app.models.alert import Alert, AlertEvent
from app.models.connection import Connection
from app.schemas import AlertCreate, AlertEventOut, AlertOut
from app.services import alerts as alerts_svc

router = APIRouter(prefix="/connections/{connection_id}/alerts", tags=["alerts"])


@router.get("", response_model=list[AlertOut])
def list_alerts(
    conn: Connection = Depends(get_owned_connection),
    db: Session = Depends(get_db),
) -> list[AlertOut]:
    rows = db.execute(
        select(Alert).where(Alert.connection_id == conn.id).order_by(Alert.created_at.desc())
    ).scalars().all()
    return [AlertOut.model_validate(r) for r in rows]


@router.post("", response_model=AlertOut, status_code=201,
             dependencies=[Depends(require_analyst)])
def create_alert(
    payload: AlertCreate,
    conn: Connection = Depends(get_owned_connection),
    db: Session = Depends(get_db),
) -> AlertOut:
    if payload.definition_id is None and (not payload.table_name or not payload.expression):
        raise HTTPException(
            status_code=422,
            detail="Fournissez une définition (definition_id) ou une table + expression.",
        )
    alert = Alert(
        tenant_id=conn.tenant_id, connection_id=conn.id, name=payload.name,
        description=payload.description, definition_id=payload.definition_id,
        schema_name=payload.schema_name, table_name=payload.table_name,
        expression=payload.expression, filter_sql=payload.filter_sql,
        comparison=payload.comparison, threshold=payload.threshold,
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return AlertOut.model_validate(alert)


@router.post("/{alert_id}/check", response_model=AlertOut,
             dependencies=[Depends(require_analyst)])
def check_alert(
    alert_id: int,
    conn: Connection = Depends(get_owned_connection),
    db: Session = Depends(get_db),
) -> AlertOut:
    alert = db.get(Alert, alert_id)
    if alert is None or alert.connection_id != conn.id:
        raise HTTPException(status_code=404, detail="Alerte introuvable.")
    alerts_svc.evaluate(db, alert, conn)
    db.commit()
    db.refresh(alert)
    return AlertOut.model_validate(alert)


@router.post("/check-all", response_model=list[AlertOut],
             dependencies=[Depends(require_analyst)])
def check_all(
    conn: Connection = Depends(get_owned_connection),
    db: Session = Depends(get_db),
) -> list[AlertOut]:
    alerts_svc.evaluate_all(db, conn)
    db.commit()
    rows = db.execute(
        select(Alert).where(Alert.connection_id == conn.id).order_by(Alert.created_at.desc())
    ).scalars().all()
    return [AlertOut.model_validate(r) for r in rows]


@router.get("/{alert_id}/events", response_model=list[AlertEventOut])
def alert_events(
    alert_id: int,
    conn: Connection = Depends(get_owned_connection),
    db: Session = Depends(get_db),
) -> list[AlertEventOut]:
    alert = db.get(Alert, alert_id)
    if alert is None or alert.connection_id != conn.id:
        raise HTTPException(status_code=404, detail="Alerte introuvable.")
    rows = db.execute(
        select(AlertEvent).where(AlertEvent.alert_id == alert_id)
        .order_by(AlertEvent.created_at.desc()).limit(50)
    ).scalars().all()
    return [AlertEventOut.model_validate(r) for r in rows]


@router.delete("/{alert_id}", status_code=204,
               dependencies=[Depends(require_analyst)])
def delete_alert(
    alert_id: int,
    conn: Connection = Depends(get_owned_connection),
    db: Session = Depends(get_db),
) -> None:
    alert = db.get(Alert, alert_id)
    if alert is None or alert.connection_id != conn.id:
        raise HTTPException(status_code=404, detail="Alerte introuvable.")
    db.delete(alert)
    db.commit()
