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


def build_context(
    db: Session,
    snapshot: SchemaSnapshot,
    max_tables: int = 60,
    *,
    hidden_tables: set[str] | None = None,
    hidden_columns: set[tuple[str, str]] | None = None,
) -> str:
    """Contexte de schéma pour le moteur SQL.

    Gouvernance par espace : `hidden_tables` (noms de tables masquées) et
    `hidden_columns` ({(table, colonne)}) sont exclus — le moteur ne les voit
    jamais, donc ne peut ni les proposer ni les interroger.
    """
    hidden_tables = {t.lower() for t in (hidden_tables or set())}
    hidden_columns = {(t.lower(), c.lower()) for t, c in (hidden_columns or set())}

    tables = db.execute(
        select(DbTable).where(DbTable.snapshot_id == snapshot.id).order_by(DbTable.table_name)
    ).scalars().all()

    lines: list[str] = []
    for t in tables[:max_tables]:
        if t.table_name.lower() in hidden_tables:
            continue
        cols = db.execute(
            select(DbColumn).where(DbColumn.table_id == t.id).order_by(DbColumn.ordinal)
        ).scalars().all()
        rows_hint = f" (rows~{t.estimated_rows})" if t.estimated_rows else ""
        lines.append(f"Table {t.schema_name}.{t.table_name}{rows_hint}")
        for c in cols:
            if (t.table_name.lower(), c.name.lower()) in hidden_columns:
                continue
            pk = " PK" if c.is_primary_key else ""
            lines.append(f"  - {c.name} {c.data_type}{pk}")

    # Les relations REJETÉES par l'utilisateur (boucle de validation, Module 6)
    # ne guident plus le choix des jointures.
    relations = db.execute(
        select(DbRelation).where(
            DbRelation.snapshot_id == snapshot.id,
            DbRelation.status != "rejected",
        )
    ).scalars().all()
    # Une relation touchant une table masquée par la gouvernance est retirée.
    relations = [
        r for r in relations
        if r.from_table.lower() not in hidden_tables and r.to_table.lower() not in hidden_tables
    ]
    if relations:
        lines.append("")
        lines.append("Relations connues (jointures possibles) :")
        for r in relations:
            tag = {"declared": "FK", "inferred": "FK inférée", "validated": "FK validée"}.get(r.kind, r.kind)
            card = f", {r.cardinality}" if r.cardinality else ""
            lines.append(
                f"  {r.from_schema}.{r.from_table}.{r.from_column} -> "
                f"{r.to_schema}.{r.to_table}.{r.to_column} [{tag}{card}]"
            )
    return "\n".join(lines)
