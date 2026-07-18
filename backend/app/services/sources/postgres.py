"""Adaptateur PostgreSQL — lecture seule stricte, garde-fous, introspection."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import psycopg
from psycopg.rows import tuple_row

from app.core.logging import get_logger
from app.services.sources.base import (
    ColumnInfo,
    ScanResult,
    SourceAdapter,
    SourceConfig,
    TableInfo,
    RelationInfo,
    infer_relations,
)

log = get_logger("noreon.source.postgres")

_INTEGER_TYPES = {"integer", "bigint", "smallint", "int", "int2", "int4", "int8", "serial", "bigserial"}


class PostgresAdapter(SourceAdapter):
    engine = "postgresql"
    dialect = "postgres"

    def _conninfo(self, statement_timeout_ms: int | None) -> dict:
        cfg = self.config
        opts = ["-c default_transaction_read_only=on"]
        if statement_timeout_ms is not None:
            opts.append(f"-c statement_timeout={statement_timeout_ms}")
        return {
            "host": cfg.host, "port": cfg.port, "dbname": cfg.database,
            "user": cfg.username, "password": cfg.password,
            "sslmode": cfg.options.get("sslmode", cfg.sslmode),
            "connect_timeout": cfg.connect_timeout,
            "options": " ".join(opts), "application_name": "noreon",
        }

    @contextmanager
    def _open(self, statement_timeout_ms: int | None = None) -> Iterator[psycopg.Connection]:
        conn = psycopg.connect(**self._conninfo(statement_timeout_ms), row_factory=tuple_row, autocommit=False)
        try:
            yield conn
            conn.rollback()
        finally:
            conn.close()

    # --- primitives ---
    def fetch(self, sql: str, params: tuple | None = None) -> tuple[list[str], list[list]]:
        with self._open(statement_timeout_ms=120_000) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                cols = [d.name for d in cur.description] if cur.description else []
                rows = [list(r) for r in cur.fetchall()]
        return cols, rows

    def qualified(self, schema: str, table: str) -> str:
        return f'"{schema}"."{table}"'

    def length_of(self, ident_sql: str) -> str:
        return f"length({ident_sql}::text)"

    def sample_source(self, schema: str, table: str, estimated_rows: int | None) -> tuple[str, bool]:
        from app.core.config import settings

        fq = self.qualified(schema, table)
        threshold = settings.profiling_sample_threshold
        if estimated_rows is not None and estimated_rows >= threshold:
            pct = max(0.01, min(100.0, settings.profiling_sample_size * 100.0 / estimated_rows))
            return f"{fq} TABLESAMPLE SYSTEM ({pct:.4f})", True
        return fq, False

    # --- connexion / conformité ---
    def test_connection(self) -> dict:
        try:
            cols, rows = self.fetch("SELECT version()")
            return {"ok": True, "server_version": rows[0][0], "error": None}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "server_version": None, "error": str(exc)}

    def check_read_only(self) -> dict:
        try:
            with self._open(statement_timeout_ms=15_000) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
                    row = cur.fetchone()
                    is_superuser = bool(row[0]) if row else False
                    cur.execute(
                        """
                        SELECT count(*) FROM information_schema.tables t
                        WHERE t.table_schema NOT IN ('pg_catalog','information_schema')
                          AND t.table_type = 'BASE TABLE'
                          AND (has_table_privilege(quote_ident(t.table_schema)||'.'||quote_ident(t.table_name),'INSERT')
                            OR has_table_privilege(quote_ident(t.table_schema)||'.'||quote_ident(t.table_name),'UPDATE')
                            OR has_table_privilege(quote_ident(t.table_schema)||'.'||quote_ident(t.table_name),'DELETE'))
                        """
                    )
                    writable = int(cur.fetchone()[0])
                    cur.execute(
                        """
                        SELECT count(*) FROM information_schema.schemata s
                        WHERE s.schema_name NOT IN ('pg_catalog','information_schema')
                          AND has_schema_privilege(s.schema_name,'CREATE')
                        """
                    )
                    creatable = int(cur.fetchone()[0])
            read_only = (not is_superuser) and writable == 0 and creatable == 0
            reasons = []
            if is_superuser:
                reasons.append("le compte est superuser")
            if writable:
                reasons.append(f"{writable} table(s) accessibles en écriture (INSERT/UPDATE/DELETE)")
            if creatable:
                reasons.append(f"{creatable} schéma(s) où le compte peut créer des objets")
            detail = "Compte en lecture seule confirmé." if read_only else "Compte NON read-only : " + " ; ".join(reasons)
            return {"read_only": read_only, "detail": detail, "error": None}
        except Exception as exc:  # noqa: BLE001
            return {"read_only": None, "detail": None, "error": str(exc)}

    # --- introspection (via pg_catalog : robuste pour les comptes read-only) ---
    def introspect(self) -> ScanResult:
        with self._open(statement_timeout_ms=120_000) as conn:
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
                estimated_rows=int(est_rows) if est_rows is not None else None, comment=comment,
            )
        for schema, table, col, ordinal, dtype, nullable, default in col_rows:
            ti = tables.get((schema, table))
            if ti is None:
                continue
            ti.columns.append(ColumnInfo(
                name=col, ordinal=int(ordinal), data_type=dtype,
                is_nullable=bool(nullable), default=default,
                is_pk=(schema, table, col) in pk_set,
            ))
        relations: list[RelationInfo] = []
        declared_pairs: set[tuple] = set()
        for fs, ft, fc, ts, tt, tc in fk_rows:
            relations.append(RelationInfo(fs, ft, fc, ts, tt, tc, kind="declared", confidence=1.0))
            declared_pairs.add((fs, ft, fc))
        relations.extend(infer_relations(list(tables.values()), declared_pairs))
        return ScanResult(tables=list(tables.values()), relations=relations)

    # --- exécution ---
    def _estimate_cost(self, sql: str, timeout_ms: int) -> float:
        try:
            with self._open(statement_timeout_ms=timeout_ms) as conn:
                with conn.cursor() as cur:
                    cur.execute(f"EXPLAIN (FORMAT JSON) {sql}")
                    plan = cur.fetchone()[0]
            return float(plan[0]["Plan"]["Total Cost"])
        except Exception:  # noqa: BLE001
            return 0.0

    def _execute(self, sql: str, timeout_seconds: int) -> tuple[list[str], list[list]]:
        with self._open(statement_timeout_ms=timeout_seconds * 1000) as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                cols = [d.name for d in cur.description] if cur.description else []
                rows = [list(r) for r in cur.fetchall()]
        return cols, rows


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

_Q_PK = """
SELECT ns.nspname AS schema, cl.relname AS table_name, att.attname AS column_name
FROM pg_constraint c
JOIN pg_class cl ON cl.oid = c.conrelid
JOIN pg_namespace ns ON ns.oid = cl.relnamespace
JOIN unnest(c.conkey) AS k(attnum) ON TRUE
JOIN pg_attribute att ON att.attrelid = c.conrelid AND att.attnum = k.attnum
WHERE c.contype = 'p' AND ns.nspname NOT IN ('pg_catalog','information_schema')
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
WHERE c.contype = 'f' AND ns.nspname NOT IN ('pg_catalog','information_schema')
"""
