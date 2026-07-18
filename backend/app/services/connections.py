"""Logique métier des connexions sources (Module 1) — multi-moteurs (V1.0)."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.security import get_secret_box
from app.models.connection import Connection
from app.services.sources.base import SourceAdapter, SourceConfig
from app.services.sources.factory import adapter_for_config, get_adapter


def get_source_adapter(conn: Connection) -> SourceAdapter:
    return get_adapter(conn)


def probe(adapter: SourceAdapter) -> dict:
    """Teste connexion + lecture seule. Résultat agrégé pour l'API."""
    conn_result = adapter.test_connection()
    if not conn_result["ok"]:
        return {
            "connection_ok": False, "server_version": None,
            "read_only": None, "read_only_detail": None, "error": conn_result["error"],
        }
    ro = adapter.check_read_only()
    return {
        "connection_ok": True, "server_version": conn_result["server_version"],
        "read_only": ro["read_only"], "read_only_detail": ro["detail"], "error": ro["error"],
    }


def persist_probe_result(conn: Connection, probe_result: dict) -> None:
    conn.last_tested_at = datetime.now(timezone.utc)
    if probe_result["connection_ok"]:
        conn.status = "ok"
        conn.last_error = None
        conn.is_read_only = probe_result["read_only"]
        conn.read_only_detail = probe_result["read_only_detail"]
    else:
        conn.status = "error"
        conn.last_error = probe_result["error"]


_DEFAULT_PORTS = {"postgresql": 5432, "mysql": 3306, "mariadb": 3306}


def create_connection(
    db: Session,
    *,
    tenant_id: int,
    name: str,
    engine: str = "postgresql",
    host: str = "",
    port: int | None = None,
    database: str = "",
    username: str = "",
    password: str = "",
    options: dict | None = None,
) -> tuple[Connection, dict]:
    """Crée une connexion (n'importe quel moteur) : chiffre le secret, teste,
    vérifie le read-only. Le test est OBLIGATOIRE avant validation (Module 1)."""
    box = get_secret_box()
    options = options or {}
    port = port or _DEFAULT_PORTS.get(engine, 0)

    cfg = SourceConfig(
        engine=engine, host=host or "localhost", port=port, database=database,
        username=username, password=password,
        sslmode=options.get("sslmode", "prefer"), options=options,
        file_path=options.get("file_path"),
    )
    result = probe(adapter_for_config(cfg))

    secret_encrypted = box.encrypt_json({"password": password}) if password else box.encrypt_json({})
    conn = Connection(
        tenant_id=tenant_id, name=name, engine=engine, host=host or "localhost",
        port=port, database=database, username=username,
        secret_encrypted=secret_encrypted, options=options,
    )
    persist_probe_result(conn, result)
    db.add(conn)
    db.flush()
    return conn, result
