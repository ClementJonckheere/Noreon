"""Construction du contexte de schéma fourni au moteur SQL.

Format textuel lisible à la fois par un vrai LLM et par le parseur du
fournisseur heuristique (voir app/llm/heuristic.parse_schema_context) :

    Table public.customers (rows~39000)
      - id integer PK
      - email varchar
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.schema_catalog import DbColumn, DbRelation, DbTable, SchemaSnapshot


def current_snapshot(db: Session, connection_id: int) -> SchemaSnapshot | None:
    return db.execute(
        select(SchemaSnapshot).where(
            SchemaSnapshot.connection_id == connection_id,
            SchemaSnapshot.is_current.is_(True),
        )
    ).scalar_one_or_none()


def build_context(db: Session, snapshot: SchemaSnapshot, max_tables: int = 60) -> str:
    tables = db.execute(
        select(DbTable).where(DbTable.snapshot_id == snapshot.id).order_by(DbTable.table_name)
    ).scalars().all()

    lines: list[str] = []
    for t in tables[:max_tables]:
        cols = db.execute(
            select(DbColumn).where(DbColumn.table_id == t.id).order_by(DbColumn.ordinal)
        ).scalars().all()
        rows_hint = f" (rows~{t.estimated_rows})" if t.estimated_rows else ""
        lines.append(f"Table {t.schema_name}.{t.table_name}{rows_hint}")
        for c in cols:
            pk = " PK" if c.is_primary_key else ""
            lines.append(f"  - {c.name} {c.data_type}{pk}")

    relations = db.execute(
        select(DbRelation).where(DbRelation.snapshot_id == snapshot.id)
    ).scalars().all()
    if relations:
        lines.append("")
        lines.append("Relations connues (jointures possibles) :")
        for r in relations:
            tag = {"declared": "FK", "inferred": "FK inférée", "validated": "FK validée"}.get(r.kind, r.kind)
            lines.append(
                f"  {r.from_schema}.{r.from_table}.{r.from_column} -> "
                f"{r.to_schema}.{r.to_table}.{r.to_column} [{tag}]"
            )
    return "\n".join(lines)
