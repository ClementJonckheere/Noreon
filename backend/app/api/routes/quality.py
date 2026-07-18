from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_owned_connection, require_analyst
from app.core.db import get_db
from app.models.connection import Connection
from app.models.quality import QualityScore
from app.schemas import QualityRunOut, QualityScoreOut
from app.services import connections as conn_svc
from app.services import quality as quality_svc

router = APIRouter(prefix="/connections/{connection_id}", tags=["quality"])


@router.post("/quality", response_model=QualityRunOut,
             dependencies=[Depends(require_analyst)])
def run_quality(
    conn: Connection = Depends(get_owned_connection),
    db: Session = Depends(get_db),
) -> QualityRunOut:
    if conn.is_read_only is False:
        raise HTTPException(status_code=409, detail="Connexion non read-only : calcul refusé.")
    adapter = conn_svc.get_source_adapter(conn)
    try:
        summary = quality_svc.run_quality(db, conn, adapter)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return QualityRunOut(**summary)


@router.get("/quality", response_model=list[QualityScoreOut])
def get_quality(
    conn: Connection = Depends(get_owned_connection),
    db: Session = Depends(get_db),
    level: str | None = None,
) -> list[QualityScoreOut]:
    stmt = select(QualityScore).where(QualityScore.connection_id == conn.id)
    if level:
        stmt = stmt.where(QualityScore.level == level)
    rows = db.execute(
        stmt.order_by(QualityScore.level, QualityScore.table_name, QualityScore.column_name)
    ).scalars().all()
    return [QualityScoreOut.model_validate(r) for r in rows]
