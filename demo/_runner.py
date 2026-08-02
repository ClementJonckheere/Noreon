"""Pipeline partagé de la bibliothèque de démonstration.

Branche Noreon sur la base source d'un scénario (lecture seule), rejoue le
pipeline complet et renvoie la réponse structurée. Utilisé par `verify.py`
(affichage) et `benchmark.py` (scoring Gold Standard).

Ne modifie jamais la base source ; la base interne est utilisée en transaction
puis annulée (rollback).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

SCENARIO_QUESTIONS = {
    "retail": "Pourquoi le chiffre d'affaires baisse-t-il depuis 4 mois ?",
    "crm": "Pourquoi le churn augmente-t-il ?",
    "finance": "Pourquoi la marge diminue-t-elle ?",
    "supply_chain": "Pourquoi les ruptures de stock augmentent-elles ?",
    "hr": "Pourquoi les départs augmentent-ils ?",
}


def db_available(scenario: str) -> bool:
    """La base source du scénario est-elle joignable (lecture seule) ?"""
    import psycopg

    dsn = (f"host=localhost port=5432 dbname=noreon_demo_{scenario} "
           "user=noreon_ro password=readonly")
    try:
        with psycopg.connect(dsn, connect_timeout=3) as c:
            with c.cursor() as cur:
                cur.execute("SELECT 1")
        return True
    except Exception:
        return False


def analyze(scenario: str, question: str | None = None):
    """Rejoue Discover → Understand → Reason → Reveal. Renvoie (ChatResponse, meta)."""
    from app.core.db import SessionLocal
    from app.models.schema_catalog import DbColumn
    from app.models.tenant import Tenant, TenantSettings
    from app.services import chat as chat_svc
    from app.services import connections as conn_svc
    from app.services import scanner
    from app.services.profiler import persist_profiles, profile_table
    from app.services.schema_context import current_snapshot
    from sqlalchemy import select

    question = question or SCENARIO_QUESTIONS[scenario]
    db = SessionLocal()
    try:
        tenant = Tenant(slug=f"demo-{scenario}", name=f"Demo {scenario}")
        tenant.settings = TenantSettings(tenant=tenant)
        db.add(tenant)
        db.flush()
        conn, probe = conn_svc.create_connection(
            db, tenant_id=tenant.id, name=f"demo-{scenario}", host="localhost", port=5432,
            database=f"noreon_demo_{scenario}", username="noreon_ro", password="readonly",
        )
        db.flush()
        adapter = conn_svc.get_source_adapter(conn)
        scanner.scan_and_persist(db, conn, adapter)
        snapshot = current_snapshot(db, conn.id)
        for t in snapshot.tables:
            if t.table_type != "table":
                continue
            cols = db.execute(
                select(DbColumn).where(DbColumn.table_id == t.id).order_by(DbColumn.ordinal)
            ).scalars().all()
            persist_profiles(db, conn, t, profile_table(adapter, t, cols))
        r = chat_svc.answer_question(db, conn, question, run_analysis=True, deep_analysis=True)
        meta = {
            "tables": len([t for t in snapshot.tables if t.table_type == "table"]),
            "relations": len(snapshot.relations),
            "read_only": conn.is_read_only,
        }
        return r, meta
    finally:
        db.rollback()
        db.close()
