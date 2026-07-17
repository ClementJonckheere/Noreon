"""Scanner automatique de schéma (Module 2) — persistance versionnée.

L'introspection elle-même (tables, colonnes, clés, relations implicites) est
fournie par l'adaptateur de source (multi-SGBD, V1.0). Ce module se charge du
versionnement : un nouveau snapshot n'est créé que si la signature du schéma a
changé (scan incrémental).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.connection import Connection
from app.models.schema_catalog import DbColumn, DbRelation, DbTable, SchemaSnapshot
from app.services.sources.base import SourceAdapter

log = get_logger("noreon.scanner")


def scan_and_persist(db: Session, conn: Connection, adapter: SourceAdapter) -> tuple[SchemaSnapshot, bool]:
    """Scanne (via l'adaptateur) et versionne. Renvoie (snapshot_courant, changed)."""
    result = adapter.introspect()
    signature = result.signature()

    current = db.execute(
        select(SchemaSnapshot).where(
            SchemaSnapshot.connection_id == conn.id, SchemaSnapshot.is_current.is_(True)
        )
    ).scalar_one_or_none()

    if current is not None and current.signature == signature:
        conn.last_scanned_at = datetime.now(timezone.utc)
        return current, False  # scan incrémental : rien n'a changé

    version = 1
    if current is not None:
        current.is_current = False
        version = current.version + 1

    snapshot = SchemaSnapshot(
        connection_id=conn.id, version=version, signature=signature,
        is_current=True, table_count=len(result.tables),
    )
    db.add(snapshot)
    db.flush()

    for t in result.tables:
        table = DbTable(
            snapshot_id=snapshot.id, schema_name=t.schema, table_name=t.name,
            table_type=t.table_type, estimated_rows=t.estimated_rows, comment=t.comment,
        )
        db.add(table)
        db.flush()
        for c in t.columns:
            db.add(DbColumn(
                table_id=table.id, name=c.name, ordinal=c.ordinal, data_type=c.data_type,
                is_nullable=c.is_nullable, default_value=c.default, is_primary_key=c.is_pk,
            ))

    for r in result.relations:
        db.add(DbRelation(
            snapshot_id=snapshot.id,
            from_schema=r.from_schema, from_table=r.from_table, from_column=r.from_column,
            to_schema=r.to_schema, to_table=r.to_table, to_column=r.to_column,
            kind=r.kind, status="validated" if r.kind == "declared" else "proposed",
            confidence=r.confidence, details=r.details,
        ))

    conn.last_scanned_at = datetime.now(timezone.utc)
    db.flush()
    return snapshot, True
