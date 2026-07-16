"""Logique métier des connexions sources (Module 1)."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.security import SecretBox, get_secret_box
from app.models.connection import Connection
from app.services.source_db import SourceConfig, check_read_only, test_connection


def source_config(conn: Connection, box: SecretBox | None = None) -> SourceConfig:
    """Construit la config source (déchiffre le mot de passe en mémoire, jamais loggé)."""
    box = box or get_secret_box()
    secret = box.decrypt_json(conn.secret_encrypted)
    opts = conn.options or {}
    return SourceConfig(
        host=conn.host,
        port=conn.port,
        database=conn.database,
        username=conn.username,
        password=secret.get("password", ""),
        sslmode=opts.get("sslmode", "prefer"),
        options=opts,
    )


def probe(cfg: SourceConfig) -> dict:
    """Teste connexion + lecture seule. Résultat agrégé pour l'API."""
    conn_result = test_connection(cfg)
    if not conn_result["ok"]:
        return {
            "connection_ok": False,
            "server_version": None,
            "read_only": None,
            "read_only_detail": None,
            "error": conn_result["error"],
        }
    ro = check_read_only(cfg)
    return {
        "connection_ok": True,
        "server_version": conn_result["server_version"],
        "read_only": ro["read_only"],
        "read_only_detail": ro["detail"],
        "error": ro["error"],
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


def create_connection(
    db: Session,
    *,
    tenant_id: int,
    name: str,
    host: str,
    port: int,
    database: str,
    username: str,
    password: str,
    options: dict | None = None,
) -> tuple[Connection, dict]:
    """Crée une connexion : chiffre le secret, teste, vérifie le read-only.

    Le test de connexion est OBLIGATOIRE avant validation (Module 1). Si le
    compte n'est pas read-only, la connexion est enregistrée mais marquée
    bloquante (l'API renvoie une alerte).
    """
    box = get_secret_box()
    options = options or {}
    cfg = SourceConfig(
        host=host,
        port=port,
        database=database,
        username=username,
        password=password,
        sslmode=options.get("sslmode", "prefer"),
        options=options,
    )
    result = probe(cfg)

    conn = Connection(
        tenant_id=tenant_id,
        name=name,
        engine="postgresql",
        host=host,
        port=port,
        database=database,
        username=username,
        secret_encrypted=box.encrypt_json({"password": password}),
        options=options,
    )
    persist_probe_result(conn, result)
    db.add(conn)
    db.flush()
    return conn, result
