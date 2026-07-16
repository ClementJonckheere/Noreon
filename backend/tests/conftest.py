from __future__ import annotations

import os

import psycopg
import pytest

DEMO_DSN = os.getenv(
    "NOREON_DEMO_DSN",
    "host=localhost port=5432 dbname=noreon_demo user=noreon_ro password=readonly",
)
DEMO = {
    "host": "localhost",
    "port": 5432,
    "database": "noreon_demo",
    "username": "noreon_ro",
    "password": "readonly",
}


def _demo_available() -> bool:
    try:
        with psycopg.connect(DEMO_DSN, connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return True
    except Exception:
        return False


demo_required = pytest.mark.skipif(
    not _demo_available(),
    reason="Base de démo noreon_demo indisponible (lancer scripts/setup_demo.sh).",
)
