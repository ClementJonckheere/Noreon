"""Espaces & gouvernance des données par espace.

Un espace regroupe une équipe : ses connexions (BDD), ses membres, et ce qui est
accessible (tables/colonnes cochées). La gouvernance ne stocke que les
EXCEPTIONS (`enabled=false`) ; par défaut tout est visible.
"""
from __future__ import annotations

import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.schema_catalog import DbColumn, DbTable, SchemaSnapshot
from app.models.space import (
    Space,
    SpaceColumnAccess,
    SpaceConnection,
    SpaceTableAccess,
)


def slugify(name: str) -> str:
    s = unicodedata.normalize("NFD", name)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "espace"


def space_connection_ids(db: Session, space_id: int) -> list[int]:
    return list(
        db.execute(
            select(SpaceConnection.connection_id).where(SpaceConnection.space_id == space_id)
        ).scalars().all()
    )


def is_connection_in_space(db: Session, space_id: int, connection_id: int) -> bool:
    return db.execute(
        select(SpaceConnection.id).where(
            SpaceConnection.space_id == space_id,
            SpaceConnection.connection_id == connection_id,
        )
    ).scalar_one_or_none() is not None


def hidden_tables(db: Session, space_id: int, connection_id: int) -> set[str]:
    """Noms de tables masquées (enabled=false) pour l'espace, en minuscules."""
    rows = db.execute(
        select(SpaceTableAccess.table_name).where(
            SpaceTableAccess.space_id == space_id,
            SpaceTableAccess.connection_id == connection_id,
            SpaceTableAccess.enabled.is_(False),
        )
    ).scalars().all()
    return {t.lower() for t in rows}


def hidden_columns(db: Session, space_id: int, connection_id: int) -> set[tuple[str, str]]:
    """Couples (table, colonne) masqués pour l'espace, en minuscules."""
    rows = db.execute(
        select(SpaceColumnAccess.table_name, SpaceColumnAccess.column_name).where(
            SpaceColumnAccess.space_id == space_id,
            SpaceColumnAccess.connection_id == connection_id,
            SpaceColumnAccess.enabled.is_(False),
        )
    ).all()
    return {(t.lower(), c.lower()) for t, c in rows}


def set_table_enabled(
    db: Session, space_id: int, connection_id: int, schema: str, table: str, enabled: bool
) -> None:
    """Coche/décoche une table. On ne matérialise que les exceptions (enabled=false)."""
    row = db.execute(
        select(SpaceTableAccess).where(
            SpaceTableAccess.space_id == space_id,
            SpaceTableAccess.connection_id == connection_id,
            SpaceTableAccess.schema_name == schema,
            SpaceTableAccess.table_name == table,
        )
    ).scalar_one_or_none()
    if enabled:
        if row is not None:
            db.delete(row)  # défaut = visible → on retire l'exception
    else:
        if row is None:
            db.add(SpaceTableAccess(
                space_id=space_id, connection_id=connection_id,
                schema_name=schema, table_name=table, enabled=False,
            ))
        else:
            row.enabled = False


def set_column_enabled(
    db: Session, space_id: int, connection_id: int, schema: str, table: str, column: str, enabled: bool
) -> None:
    row = db.execute(
        select(SpaceColumnAccess).where(
            SpaceColumnAccess.space_id == space_id,
            SpaceColumnAccess.connection_id == connection_id,
            SpaceColumnAccess.schema_name == schema,
            SpaceColumnAccess.table_name == table,
            SpaceColumnAccess.column_name == column,
        )
    ).scalar_one_or_none()
    if enabled:
        if row is not None:
            db.delete(row)
    else:
        if row is None:
            db.add(SpaceColumnAccess(
                space_id=space_id, connection_id=connection_id, schema_name=schema,
                table_name=table, column_name=column, enabled=False,
            ))
        else:
            row.enabled = False


def governance_view(db: Session, space_id: int, connection_id: int) -> dict:
    """Vue de gouvernance : chaque table/colonne du dernier schéma + son état."""
    snapshot = db.execute(
        select(SchemaSnapshot).where(
            SchemaSnapshot.connection_id == connection_id,
            SchemaSnapshot.is_current.is_(True),
        )
    ).scalar_one_or_none()
    if snapshot is None:
        return {"scanned": False, "tables": []}

    ht = hidden_tables(db, space_id, connection_id)
    hc = hidden_columns(db, space_id, connection_id)
    tables = db.execute(
        select(DbTable).where(DbTable.snapshot_id == snapshot.id).order_by(DbTable.table_name)
    ).scalars().all()

    out = []
    for t in tables:
        cols = db.execute(
            select(DbColumn).where(DbColumn.table_id == t.id).order_by(DbColumn.ordinal)
        ).scalars().all()
        out.append({
            "schema": t.schema_name,
            "table": t.table_name,
            "enabled": t.table_name.lower() not in ht,
            "columns": [
                {"name": c.name, "data_type": c.data_type,
                 "enabled": (t.table_name.lower(), c.name.lower()) not in hc}
                for c in cols
            ],
        })
    return {"scanned": True, "tables": out}


def space_dict(db: Session, space: Space) -> dict:
    conn_ids = space_connection_ids(db, space.id)
    return {
        "id": space.id, "name": space.name, "slug": space.slug,
        "description": space.description, "connection_ids": conn_ids,
        "created_at": space.created_at.isoformat() if space.created_at else None,
    }
