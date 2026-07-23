from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_owned_connection
from app.core.db import get_db
from app.models.connection import Connection
from app.models.query_log import QueryLog
from app.schemas import ChatRequest
from app.services import chat as chat_svc

router = APIRouter(prefix="/connections/{connection_id}", tags=["chat"])


@router.post("/chat")
def ask(
    payload: ChatRequest,
    conn: Connection = Depends(get_owned_connection),
    db: Session = Depends(get_db),
) -> dict:
    response = chat_svc.answer_question(
        db, conn, payload.question,
        run_analysis=payload.run_analysis, deep_analysis=payload.deep_analysis,
    )
    db.commit()
    return response.as_dict()


@router.get("/discoveries")
def discoveries(
    conn: Connection = Depends(get_owned_connection),
    db: Session = Depends(get_db),
    refresh: bool = False,
) -> dict:
    """Suggestions automatiques à l'ouverture (anomalies, tendances, colonnes
    suspectes, relations incohérentes) — l'analyste proactif.

    Mis en cache (par version de schéma) pour un affichage instantané ;
    `?refresh=true` force le recalcul."""
    from app.services import discoveries as disc_svc
    from app.services.connections import get_source_adapter

    adapter = get_source_adapter(conn)
    return disc_svc.cached_discoveries(db, conn, adapter, force=refresh)


@router.get("/queries")
def query_log(
    conn: Connection = Depends(get_owned_connection),
    db: Session = Depends(get_db),
    limit: int = 50,
) -> list[dict]:
    """Journal d'audit des exécutions (transparence + traçabilité, Module 8)."""
    rows = db.execute(
        select(QueryLog).where(QueryLog.connection_id == conn.id)
        .order_by(QueryLog.created_at.desc()).limit(limit)
    ).scalars().all()
    return [
        {
            "id": r.id, "question": r.question, "sql": r.sql,
            "status": r.status, "block_reason": r.block_reason,
            "tables_used": r.tables_used, "row_count": r.row_count,
            "duration_ms": r.duration_ms, "estimated_cost": r.estimated_cost,
            "truncated": r.truncated, "confidence": r.confidence,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
