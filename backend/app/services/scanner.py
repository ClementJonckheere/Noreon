"""Scanner automatique de schéma (Module 2).

Analyse la structure d'une base PostgreSQL (tables, vues, colonnes, clés
primaires, clés étrangères déclarées) puis infère les relations implicites
(convention `xxx_id`) — indispensable car les FK sont rarement déclarées dans
les bases réelles.

Versionnement (scan incrémental) : chaque scan calcule une signature du
schéma. Un nouveau snapshot n'est créé que si la signature a changé.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.connection import Connection
from app.models.schema_catalog import DbColumn, DbRelation, DbTable, SchemaSnapshot
from app.services.source_db import SourceConfig, open_source

log = get_logger("noreon.scanner")

_INTEGER_TYPES = {"integer", "bigint", "smallint", "int", "int2", "int4", "int8", "serial", "bigserial"}


@dataclass
class ColumnInfo:
    name: str
    ordinal: int
    data_type: str
    is_nullable: bool
    default: str | None
    is_pk: bool = False


@dataclass
class TableInfo:
    schema: str
    name: str
    table_type: str
    estimated_rows: int | None
    comment: str | None
    columns: list[ColumnInfo] = field(default_factory=list)


@dataclass
class RelationInfo:
    from_schema: str
    from_table: str
    from_column: str
    to_schema: str
    to_table: str
    to_column: str
    kind: str  # declared | inferred
    confidence: float
    details: dict = field(default_factory=dict)


@dataclass
class ScanResult:
    tables: list[TableInfo]
    relations: list[RelationInfo]

    def signature(self) -> str:
        payload = {
            "tables": [
                {
                    "s": t.schema,
                    "n": t.name,
                    "t": t.table_type,
                    "cols": [[c.name, c.data_type, c.is_nullable, c.is_pk] for c in t.columns],
                }
                for t in sorted(self.tables, key=lambda x: (x.schema, x.name))
            ],
            "rels": sorted(
                [
                    [r.from_schema, r.from_table, r.from_column, r.to_schema, r.to_table, r.to_column, r.kind]
                    for r in self.relations
                ]
            ),
        }
        blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()


_Q_TABLES = """
SELECT n.nspname AS schema, c.relname AS name,
       CASE WHEN c.relkind IN ('v','m') THEN 'view' ELSE 'table' END AS table_type,
       NULLIF(c.reltuples, -1)::bigint AS est_rows,
       obj_description(c.oid) AS comment
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r','p','v','m')
  AND n.nspname NOT IN ('pg_catalog','information_schema')
ORDER BY n.nspname, c.relname
"""

_Q_COLUMNS = """
SELECT table_schema, table_name, column_name, ordinal_position, data_type,
       (is_nullable = 'YES') AS nullable, column_default
FROM information_schema.columns
WHERE table_schema NOT IN ('pg_catalog','information_schema')
ORDER BY table_schema, table_name, ordinal_position
"""

# NB : on interroge pg_catalog (et non information_schema) pour les clés, car
# les vues information_schema.*constraint* sont filtrées par propriétaire et
# masquent les contraintes aux comptes en LECTURE SEULE — précisément le type
# de compte que Noreon utilise.
_Q_PK = """
SELECT ns.nspname AS schema, cl.relname AS table_name, att.attname AS column_name
FROM pg_constraint c
JOIN pg_class cl ON cl.oid = c.conrelid
JOIN pg_namespace ns ON ns.oid = cl.relnamespace
JOIN unnest(c.conkey) AS k(attnum) ON TRUE
JOIN pg_attribute att ON att.attrelid = c.conrelid AND att.attnum = k.attnum
WHERE c.contype = 'p'
  AND ns.nspname NOT IN ('pg_catalog', 'information_schema')
"""

_Q_FK = """
SELECT ns.nspname AS from_schema, cl.relname AS from_table, att.attname AS from_col,
       fns.nspname AS to_schema, fcl.relname AS to_table, fatt.attname AS to_col
FROM pg_constraint c
JOIN pg_class cl ON cl.oid = c.conrelid
JOIN pg_namespace ns ON ns.oid = cl.relnamespace
JOIN pg_class fcl ON fcl.oid = c.confrelid
JOIN pg_namespace fns ON fns.oid = fcl.relnamespace
JOIN unnest(c.conkey, c.confkey) WITH ORDINALITY AS k(conkey, confkey, ord) ON TRUE
JOIN pg_attribute att ON att.attrelid = c.conrelid AND att.attnum = k.conkey
JOIN pg_attribute fatt ON fatt.attrelid = c.confrelid AND fatt.attnum = k.confkey
WHERE c.contype = 'f'
  AND ns.nspname NOT IN ('pg_catalog', 'information_schema')
"""


def introspect(cfg: SourceConfig) -> ScanResult:
    with open_source(cfg, statement_timeout_ms=120_000) as conn:
        with conn.cursor() as cur:
            cur.execute(_Q_TABLES)
            table_rows = cur.fetchall()
            cur.execute(_Q_COLUMNS)
            col_rows = cur.fetchall()
            cur.execute(_Q_PK)
            pk_rows = cur.fetchall()
            cur.execute(_Q_FK)
            fk_rows = cur.fetchall()

    pk_set = {(s, t, c) for (s, t, c) in pk_rows}
    tables: dict[tuple[str, str], TableInfo] = {}
    for schema, name, ttype, est_rows, comment in table_rows:
        tables[(schema, name)] = TableInfo(
            schema=schema, name=name, table_type=ttype,
            estimated_rows=int(est_rows) if est_rows is not None else None,
            comment=comment,
        )

    for schema, table, col, ordinal, dtype, nullable, default in col_rows:
        ti = tables.get((schema, table))
        if ti is None:
            continue
        ti.columns.append(
            ColumnInfo(
                name=col, ordinal=int(ordinal), data_type=dtype,
                is_nullable=bool(nullable), default=default,
                is_pk=(schema, table, col) in pk_set,
            )
        )

    relations: list[RelationInfo] = []
    declared_pairs: set[tuple] = set()
    for fs, ft, fc, ts, tt, tc in fk_rows:
        relations.append(
            RelationInfo(fs, ft, fc, ts, tt, tc, kind="declared", confidence=1.0)
        )
        declared_pairs.add((fs, ft, fc))

    relations.extend(_infer_relations(list(tables.values()), pk_set, declared_pairs))
    return ScanResult(tables=list(tables.values()), relations=relations)


def _infer_relations(
    tables: list[TableInfo],
    pk_set: set[tuple[str, str, str]],
    declared_pairs: set[tuple],
) -> list[RelationInfo]:
    """Détecte les relations implicites via la convention `xxx_id`."""
    # Index des tables par nom normalisé → (table, pk_column)
    by_name: dict[str, tuple[TableInfo, str]] = {}
    for t in tables:
        pks = [c for c in t.columns if c.is_pk]
        if len(pks) == 1:
            by_name.setdefault(t.name.lower(), (t, pks[0].name))

    def candidates(base: str) -> list[str]:
        base = base.lower()
        return [base, base + "s", base + "es",
                (base[:-1] + "ies") if base.endswith("y") else base]

    inferred: list[RelationInfo] = []
    for t in tables:
        for col in t.columns:
            cname = col.name.lower()
            if not cname.endswith("_id") and not (cname.endswith("id") and len(cname) > 2):
                continue
            base = cname[:-3] if cname.endswith("_id") else cname[:-2]
            if not base or col.data_type.lower() not in _INTEGER_TYPES:
                continue
            if (t.schema, t.name, col.name) in declared_pairs:
                continue
            target = None
            for cand in candidates(base):
                if cand in by_name and by_name[cand][0].name.lower() != t.name.lower():
                    target = by_name[cand]
                    break
            if target is None:
                continue
            target_table, target_pk = target
            target_col = next((c for c in target_table.columns if c.name == target_pk), None)
            if target_col is None or target_col.data_type.lower() not in _INTEGER_TYPES:
                continue
            confidence = 0.8 if base == target_table.name.lower() else 0.65
            inferred.append(
                RelationInfo(
                    from_schema=t.schema, from_table=t.name, from_column=col.name,
                    to_schema=target_table.schema, to_table=target_table.name, to_column=target_pk,
                    kind="inferred", confidence=confidence,
                    details={"rule": "naming_convention_xxx_id"},
                )
            )
    return inferred


def scan_and_persist(db: Session, conn: Connection, cfg: SourceConfig) -> tuple[SchemaSnapshot, bool]:
    """Scanne et versionne. Renvoie (snapshot_courant, changed)."""
    result = introspect(cfg)
    signature = result.signature()

    current = db.execute(
        select(SchemaSnapshot)
        .where(SchemaSnapshot.connection_id == conn.id, SchemaSnapshot.is_current.is_(True))
    ).scalar_one_or_none()

    if current is not None and current.signature == signature:
        conn.last_scanned_at = datetime.now(timezone.utc)
        return current, False  # scan incrémental : rien n'a changé

    # Le schéma a changé (ou premier scan) → nouveau snapshot courant.
    version = 1
    if current is not None:
        current.is_current = False
        version = current.version + 1

    snapshot = SchemaSnapshot(
        connection_id=conn.id,
        version=version,
        signature=signature,
        is_current=True,
        table_count=len(result.tables),
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
