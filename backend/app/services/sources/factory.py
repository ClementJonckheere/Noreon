"""Sélection de l'adaptateur de source selon le moteur de la connexion."""
from __future__ import annotations

from app.core.security import get_secret_box
from app.models.connection import Connection
from app.services.sources.base import SourceAdapter, SourceConfig


def build_config(conn: Connection) -> SourceConfig:
    box = get_secret_box()
    secret = {}
    if conn.secret_encrypted:
        try:
            secret = box.decrypt_json(conn.secret_encrypted)
        except Exception:  # noqa: BLE001 - connexions fichier sans secret
            secret = {}
    opts = conn.options or {}
    return SourceConfig(
        engine=conn.engine,
        host=conn.host or "localhost",
        port=conn.port or 0,
        database=conn.database or "",
        username=conn.username or "",
        password=secret.get("password", ""),
        sslmode=opts.get("sslmode", "prefer"),
        options=opts,
        file_path=opts.get("file_path"),
    )


def adapter_for_config(cfg: SourceConfig) -> SourceAdapter:
    engine = (cfg.engine or "postgresql").lower()
    if engine == "postgresql":
        from app.services.sources.postgres import PostgresAdapter
        return PostgresAdapter(cfg)
    if engine in ("mysql", "mariadb"):
        from app.services.sources.mysql import MySQLAdapter
        return MySQLAdapter(cfg)
    if engine in ("csv", "excel", "sqlite"):
        from app.services.sources.files import FileAdapter
        return FileAdapter(cfg)
    raise ValueError(f"Moteur de source non supporté : {engine}")


def get_adapter(conn: Connection) -> SourceAdapter:
    return adapter_for_config(build_config(conn))
