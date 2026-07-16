"""Accès en LECTURE SEULE aux bases de données sources (V0.1 : PostgreSQL).

Toute connexion à une source est ouverte avec :
- `default_transaction_read_only = on` (défense en profondeur, principe
  « Lecture seule stricte » du cahier des charges) ;
- un `statement_timeout` (garde-fou d'exécution) ;
- éventuellement SSL/TLS (`sslmode`).

Ce module n'écrit JAMAIS dans les bases sources.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator

import psycopg
from psycopg.rows import tuple_row

from app.core.logging import get_logger

log = get_logger("noreon.source_db")


@dataclass
class SourceConfig:
    host: str
    port: int
    database: str
    username: str
    password: str
    sslmode: str = "prefer"
    connect_timeout: int = 10
    options: dict[str, Any] | None = None


def _conninfo(cfg: SourceConfig, statement_timeout_ms: int | None) -> dict[str, Any]:
    opts = ["-c default_transaction_read_only=on"]
    if statement_timeout_ms is not None:
        opts.append(f"-c statement_timeout={statement_timeout_ms}")
    return {
        "host": cfg.host,
        "port": cfg.port,
        "dbname": cfg.database,
        "user": cfg.username,
        "password": cfg.password,
        "sslmode": cfg.sslmode,
        "connect_timeout": cfg.connect_timeout,
        "options": " ".join(opts),
        "application_name": "noreon",
    }


@contextmanager
def open_source(cfg: SourceConfig, statement_timeout_ms: int | None = None) -> Iterator[psycopg.Connection]:
    """Ouvre une connexion source read-only. Toujours en autocommit=False + rollback."""
    conn = psycopg.connect(
        **_conninfo(cfg, statement_timeout_ms),
        row_factory=tuple_row,
        autocommit=False,
    )
    try:
        yield conn
        # On ne committe jamais : aucune écriture n'est attendue.
        conn.rollback()
    finally:
        conn.close()


def test_connection(cfg: SourceConfig) -> dict[str, Any]:
    """Teste la connexion. Renvoie {ok, server_version, error}."""
    try:
        with open_source(cfg, statement_timeout_ms=10_000) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT version()")
                version = cur.fetchone()[0]
        return {"ok": True, "server_version": version, "error": None}
    except Exception as exc:  # noqa: BLE001 - on remonte un message propre
        return {"ok": False, "server_version": None, "error": str(exc)}


def check_read_only(cfg: SourceConfig) -> dict[str, Any]:
    """Vérifie que le compte fourni est bien en lecture seule (Module 1).

    Méthode SANS aucune écriture : on interroge les privilèges effectifs via
    `has_table_privilege` / `has_schema_privilege` (qui tiennent compte de
    l'appartenance aux rôles et des droits PUBLIC) + le statut superuser.
    """
    try:
        with open_source(cfg, statement_timeout_ms=15_000) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
                row = cur.fetchone()
                is_superuser = bool(row[0]) if row else False

                cur.execute(
                    """
                    SELECT count(*)
                    FROM information_schema.tables t
                    WHERE t.table_schema NOT IN ('pg_catalog', 'information_schema')
                      AND t.table_type = 'BASE TABLE'
                      AND (
                        has_table_privilege(
                          quote_ident(t.table_schema) || '.' || quote_ident(t.table_name), 'INSERT')
                        OR has_table_privilege(
                          quote_ident(t.table_schema) || '.' || quote_ident(t.table_name), 'UPDATE')
                        OR has_table_privilege(
                          quote_ident(t.table_schema) || '.' || quote_ident(t.table_name), 'DELETE')
                      )
                    """
                )
                writable_tables = int(cur.fetchone()[0])

                cur.execute(
                    """
                    SELECT count(*)
                    FROM information_schema.schemata s
                    WHERE s.schema_name NOT IN ('pg_catalog', 'information_schema')
                      AND has_schema_privilege(s.schema_name, 'CREATE')
                    """
                )
                creatable_schemas = int(cur.fetchone()[0])

        read_only = (not is_superuser) and writable_tables == 0 and creatable_schemas == 0
        reasons: list[str] = []
        if is_superuser:
            reasons.append("le compte est superuser")
        if writable_tables:
            reasons.append(f"{writable_tables} table(s) accessibles en écriture (INSERT/UPDATE/DELETE)")
        if creatable_schemas:
            reasons.append(f"{creatable_schemas} schéma(s) où le compte peut créer des objets")

        detail = (
            "Compte en lecture seule confirmé."
            if read_only
            else "Compte NON read-only : " + " ; ".join(reasons)
        )
        return {"read_only": read_only, "detail": detail, "error": None}
    except Exception as exc:  # noqa: BLE001
        return {"read_only": None, "detail": None, "error": str(exc)}
