"""Adaptateur MySQL / MariaDB (V1.0) — lecture seule, garde-fous, introspection."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import pymysql

from app.core.logging import get_logger
from app.services.sources.base import (
    ColumnInfo,
    RelationInfo,
    ScanResult,
    SourceAdapter,
    TableInfo,
    infer_relations,
)

log = get_logger("noreon.source.mysql")

_WRITE_PRIVS = ("ALL PRIVILEGES", "INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER", "TRUNCATE")


class MySQLAdapter(SourceAdapter):
    engine = "mysql"
    dialect = "mysql"

    @contextmanager
    def _open(self, timeout_seconds: int | None = None) -> Iterator[pymysql.connections.Connection]:
        cfg = self.config
        conn = pymysql.connect(
            host=cfg.host, port=cfg.port or 3306, user=cfg.username,
            password=cfg.password, database=cfg.database or None,
            connect_timeout=cfg.connect_timeout,
            read_timeout=(timeout_seconds or 120),
            ssl={"ssl": {}} if cfg.options.get("ssl") else None,
            autocommit=False,
        )
        try:
            with conn.cursor() as cur:
                # Défense en profondeur : session en lecture seule + timeout.
                for stmt in (
                    "SET SESSION TRANSACTION READ ONLY",
                    f"SET SESSION max_statement_time = {timeout_seconds or 120}",
                    f"SET SESSION max_execution_time = {(timeout_seconds or 120) * 1000}",
                ):
                    try:
                        cur.execute(stmt)
                    except Exception:  # noqa: BLE001 - selon MySQL/MariaDB
                        pass
            yield conn
            conn.rollback()
        finally:
            conn.close()

    # --- primitives ---
    def fetch(self, sql: str, params: tuple | None = None) -> tuple[list[str], list[list]]:
        with self._open() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                cols = [d[0] for d in cur.description] if cur.description else []
                rows = [list(r) for r in cur.fetchall()]
        return cols, rows

    def quote_ident(self, name: str) -> str:
        return "`" + name.replace("`", "``") + "`"

    def length_of(self, ident_sql: str) -> str:
        return f"char_length(cast({ident_sql} as char))"

    def sample_source(self, schema: str, table: str, estimated_rows: int | None) -> tuple[str, bool]:
        from app.core.config import settings

        fq = self.qualified(schema, table)
        if estimated_rows is not None and estimated_rows >= settings.profiling_sample_threshold:
            n = settings.profiling_sample_size
            return f"(SELECT * FROM {fq} ORDER BY RAND() LIMIT {n}) AS _noreon_s", True
        return fq, False

    # --- connexion / conformité ---
    def test_connection(self) -> dict:
        try:
            _, rows = self.fetch("SELECT version()")
            return {"ok": True, "server_version": f"MySQL/MariaDB {rows[0][0]}", "error": None}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "server_version": None, "error": str(exc)}

    def check_read_only(self) -> dict:
        try:
            _, rows = self.fetch("SHOW GRANTS")
        except Exception as exc:  # noqa: BLE001
            return {"read_only": None, "detail": None, "error": str(exc)}
        reasons: list[str] = []
        for (grant,) in rows:
            up = grant.upper()
            if not up.startswith("GRANT "):
                continue
            head = up.split(" ON ", 1)[0]  # partie « GRANT <privs> »
            for priv in _WRITE_PRIVS:
                if priv in head:
                    reasons.append(f"privilège {priv} accordé")
        read_only = not reasons
        detail = (
            "Compte en lecture seule confirmé."
            if read_only else "Compte NON read-only : " + " ; ".join(sorted(set(reasons)))
        )
        return {"read_only": read_only, "detail": detail, "error": None}

    # --- introspection (information_schema, restreinte à la base) ---
    def introspect(self) -> ScanResult:
        db = self.config.database
        with self._open() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT table_schema, table_name, table_type, table_rows "
                    "FROM information_schema.tables WHERE table_schema = %s", (db,))
                table_rows = cur.fetchall()
                cur.execute(
                    "SELECT table_schema, table_name, column_name, ordinal_position, data_type, "
                    "is_nullable, column_default, column_key "
                    "FROM information_schema.columns WHERE table_schema = %s "
                    "ORDER BY table_schema, table_name, ordinal_position", (db,))
                col_rows = cur.fetchall()
                cur.execute(
                    "SELECT table_schema, table_name, column_name, referenced_table_schema, "
                    "referenced_table_name, referenced_column_name "
                    "FROM information_schema.key_column_usage "
                    "WHERE table_schema = %s AND referenced_table_name IS NOT NULL", (db,))
                fk_rows = cur.fetchall()

        tables: dict[tuple[str, str], TableInfo] = {}
        for schema, name, ttype, rows_est in table_rows:
            tables[(schema, name)] = TableInfo(
                schema=schema, name=name,
                table_type="view" if ttype == "VIEW" else "table",
                estimated_rows=int(rows_est) if rows_est is not None else None, comment=None,
            )
        for schema, table, col, ordinal, dtype, nullable, default, key in col_rows:
            ti = tables.get((schema, table))
            if ti is None:
                continue
            ti.columns.append(ColumnInfo(
                name=col, ordinal=int(ordinal), data_type=dtype,
                is_nullable=(nullable == "YES"), default=default, is_pk=(key == "PRI"),
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
            with self._open(timeout_seconds=max(1, timeout_ms // 1000)) as conn:
                with conn.cursor() as cur:
                    cur.execute(f"EXPLAIN FORMAT=JSON {sql}")
                    import json as _json
                    plan = _json.loads(cur.fetchone()[0])
            qb = plan.get("query_block", {})
            cost = qb.get("cost_info", {}).get("query_cost")
            return float(cost) if cost is not None else 0.0
        except Exception:  # noqa: BLE001 - MariaDB ne fournit pas toujours de coût
            return 0.0

    def _execute(self, sql: str, timeout_seconds: int) -> tuple[list[str], list[list]]:
        with self._open(timeout_seconds=timeout_seconds) as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                cols = [d[0] for d in cur.description] if cur.description else []
                rows = [list(r) for r in cur.fetchall()]
        return cols, rows
