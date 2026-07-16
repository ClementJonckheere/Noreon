"""Orchestration du profilage asynchrone (Module 3).

Une tâche de profilage parcourt les tables du snapshot courant et les profile
UNE À LA FOIS par connexion (sobriété / limitation de charge). La fonction
`run_profiling_job` est autonome (ouvre sa propre session interne) : elle est
appelée soit par le worker RQ, soit en tâche de fond FastAPI si Redis est
indisponible.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.logging import get_logger
from app.models.connection import Connection
from app.models.profile import ColumnProfile, ProfilingJob
from app.models.schema_catalog import DbColumn, DbTable
from app.services.connections import source_config
from app.services.profiler import persist_profiles, profile_table
from app.services.schema_context import current_snapshot

log = get_logger("noreon.profiling")


def run_profiling_job(job_id: int) -> None:
    db = SessionLocal()
    try:
        job = db.get(ProfilingJob, job_id)
        if job is None:
            log.warning("Job de profilage %s introuvable", job_id)
            return
        conn = db.get(Connection, job.connection_id)
        snapshot = current_snapshot(db, job.connection_id) if conn else None
        if conn is None or snapshot is None:
            job.status = "error"
            job.error = "Connexion ou schéma introuvable (scan requis avant profilage)."
            job.finished_at = datetime.now(timezone.utc)
            db.commit()
            return

        job.status = "running"
        job.started_at = datetime.now(timezone.utc)

        tables = db.execute(
            select(DbTable).where(
                DbTable.snapshot_id == snapshot.id, DbTable.table_type == "table"
            ).order_by(DbTable.table_name)
        ).scalars().all()
        if job.scope.startswith("table:"):
            target = job.scope.split(":", 1)[1]
            tables = [t for t in tables if t.table_name == target]

        job.tables_total = len(tables)
        db.commit()

        cfg = source_config(conn)
        for table in tables:
            # Re-profilage : on purge les anciens profils de la table.
            db.query(ColumnProfile).filter(
                ColumnProfile.connection_id == conn.id,
                ColumnProfile.schema_name == table.schema_name,
                ColumnProfile.table_name == table.table_name,
            ).delete()
            columns = db.execute(
                select(DbColumn).where(DbColumn.table_id == table.id).order_by(DbColumn.ordinal)
            ).scalars().all()
            try:
                profiles = profile_table(cfg, table, columns)
                persist_profiles(db, conn, table, profiles)
            except Exception as exc:  # noqa: BLE001 - échantillonnage dégradé/signalement
                log.warning("Profilage échoué pour %s : %s", table.fqtn, exc)
            job.tables_done += 1
            db.commit()

        job.status = "done"
        job.finished_at = datetime.now(timezone.utc)
        db.commit()
        log.info("Profilage terminé (job %s) : %s tables", job.id, job.tables_done)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        job = db.get(ProfilingJob, job_id)
        if job is not None:
            job.status = "error"
            job.error = str(exc)
            job.finished_at = datetime.now(timezone.utc)
            db.commit()
        raise
    finally:
        db.close()
