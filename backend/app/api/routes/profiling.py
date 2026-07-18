from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_owned_connection, require_analyst
from app.core.db import get_db
from app.models.connection import Connection
from app.models.profile import ColumnProfile, ProfilingJob
from app.schemas import ColumnProfileOut, ProfilingJobOut
from app.services.profiling_jobs import run_profiling_job
from app.services.schema_context import current_snapshot
from app.worker.queue import QUEUE_PROFILING, enqueue

router = APIRouter(prefix="/connections/{connection_id}", tags=["profiling"])


@router.post("/profile", response_model=ProfilingJobOut, status_code=202,
             dependencies=[Depends(require_analyst)])
def start_profiling(
    conn: Connection = Depends(get_owned_connection),
    db: Session = Depends(get_db),
    scope: str = Query("all", description="all | table:<nom>"),
) -> ProfilingJobOut:
    if current_snapshot(db, conn.id) is None:
        raise HTTPException(status_code=409, detail="Scannez le schéma avant de profiler.")
    job = ProfilingJob(
        tenant_id=conn.tenant_id, connection_id=conn.id, scope=scope,
        status="queued", priority=10,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    # Tâche asynchrone à faible priorité (RQ si Redis, sinon in-process).
    enqueue(run_profiling_job, job.id, queue=QUEUE_PROFILING)
    return ProfilingJobOut.model_validate(job)


@router.get("/profile/jobs", response_model=list[ProfilingJobOut])
def list_jobs(
    conn: Connection = Depends(get_owned_connection),
    db: Session = Depends(get_db),
) -> list[ProfilingJobOut]:
    rows = db.execute(
        select(ProfilingJob).where(ProfilingJob.connection_id == conn.id)
        .order_by(ProfilingJob.created_at.desc())
    ).scalars().all()
    return [ProfilingJobOut.model_validate(r) for r in rows]


@router.get("/profile/jobs/{job_id}", response_model=ProfilingJobOut)
def get_job(
    job_id: int,
    conn: Connection = Depends(get_owned_connection),
    db: Session = Depends(get_db),
) -> ProfilingJobOut:
    job = db.get(ProfilingJob, job_id)
    if job is None or job.connection_id != conn.id:
        raise HTTPException(status_code=404, detail="Job introuvable.")
    return ProfilingJobOut.model_validate(job)


@router.get("/profiles", response_model=list[ColumnProfileOut])
def get_profiles(
    conn: Connection = Depends(get_owned_connection),
    db: Session = Depends(get_db),
    table: str | None = Query(None),
) -> list[ColumnProfileOut]:
    stmt = select(ColumnProfile).where(ColumnProfile.connection_id == conn.id)
    if table:
        stmt = stmt.where(ColumnProfile.table_name == table)
    rows = db.execute(stmt.order_by(ColumnProfile.table_name, ColumnProfile.column_name)).scalars().all()
    return [ColumnProfileOut.model_validate(r) for r in rows]
