"""Exécution contrôlée des requêtes sur les bases sources (Module 8).

Chaîne complète des garde-fous d'exécution :
- EXPLAIN (FORMAT JSON) systématique → coût estimé ; blocage au-delà du seuil
  (détection des produits cartésiens accidentels) ;
- statement_timeout appliqué au niveau de la session source ;
- LIMIT automatique (appliqué en amont par sql_guard) ;
- file d'exécution : nombre max de requêtes simultanées par connexion source
  (sémaphore par connexion — in-process ; à porter sur Redis en multi-worker).
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from app.core.logging import get_logger
from app.services.source_db import SourceConfig, open_source
from app.services.sql_guard import GuardedSQL, SQLGuardError, guard

log = get_logger("noreon.executor")


class CostThresholdExceeded(SQLGuardError):
    def __init__(self, cost: float, threshold: float) -> None:
        super().__init__(
            f"Requête bloquée : coût estimé {cost:,.0f} supérieur au seuil autorisé "
            f"{threshold:,.0f} (risque de produit cartésien ou de scan massif). "
            "Ajoutez des filtres ou réduisez la portée."
        )
        self.cost = cost
        self.threshold = threshold


# --- file d'exécution : un sémaphore borné par connexion source ---
_locks_guard = threading.Lock()
_conn_semaphores: dict[int, threading.Semaphore] = {}


def _semaphore_for(connection_id: int, max_concurrent: int) -> threading.Semaphore:
    with _locks_guard:
        sem = _conn_semaphores.get(connection_id)
        if sem is None:
            sem = threading.Semaphore(max_concurrent)
            _conn_semaphores[connection_id] = sem
        return sem


@dataclass
class ExecutionResult:
    columns: list[str]
    rows: list[list]
    row_count: int
    duration_ms: int
    truncated: bool
    estimated_cost: float | None
    guarded_sql: str
    limit_applied: int | None
    warnings: list[str] = field(default_factory=list)


def estimate_cost(cfg: SourceConfig, sql: str, timeout_ms: int) -> float:
    """Renvoie le coût total estimé via EXPLAIN (FORMAT JSON)."""
    with open_source(cfg, statement_timeout_ms=timeout_ms) as conn:
        with conn.cursor() as cur:
            cur.execute(f"EXPLAIN (FORMAT JSON) {sql}")
            plan = cur.fetchone()[0]
    try:
        return float(plan[0]["Plan"]["Total Cost"])
    except (KeyError, IndexError, TypeError):
        return 0.0


def run_query(
    cfg: SourceConfig,
    raw_sql: str,
    *,
    connection_id: int,
    row_limit: int = 10_000,
    timeout_seconds: int = 60,
    max_cost: float = 1_000_000.0,
    max_concurrent: int = 1,
    enforce_cost: bool = True,
) -> ExecutionResult:
    """Applique tous les garde-fous puis exécute la requête en lecture seule."""
    guarded: GuardedSQL = guard(raw_sql, row_limit=row_limit)
    timeout_ms = timeout_seconds * 1000
    warnings: list[str] = []

    # 1) Coût estimé (EXPLAIN) avant toute exécution réelle.
    cost = estimate_cost(cfg, guarded.sql, timeout_ms)
    if enforce_cost and cost > max_cost:
        raise CostThresholdExceeded(cost, max_cost)
    if cost > max_cost * 0.5:
        warnings.append(f"Coût estimé élevé ({cost:,.0f}).")

    # 2) File d'exécution : au plus `max_concurrent` requêtes par connexion.
    sem = _semaphore_for(connection_id, max_concurrent)
    acquired = sem.acquire(timeout=timeout_seconds)
    if not acquired:
        raise SQLGuardError(
            "File d'exécution saturée pour cette connexion source (trop de requêtes simultanées)."
        )
    try:
        start = time.perf_counter()
        with open_source(cfg, statement_timeout_ms=timeout_ms) as conn:
            with conn.cursor() as cur:
                cur.execute(guarded.sql)
                columns = [d.name for d in cur.description] if cur.description else []
                fetched = cur.fetchall()
        duration_ms = int((time.perf_counter() - start) * 1000)
    finally:
        sem.release()

    truncated = guarded.limit_applied is not None and len(fetched) >= guarded.limit_applied
    rows = [list(r) for r in fetched]
    if truncated:
        warnings.append(f"Résultats tronqués à {guarded.limit_applied} lignes (LIMIT automatique).")

    return ExecutionResult(
        columns=columns,
        rows=rows,
        row_count=len(rows),
        duration_ms=duration_ms,
        truncated=truncated,
        estimated_cost=cost,
        guarded_sql=guarded.sql,
        limit_applied=guarded.limit_applied,
        warnings=warnings,
    )
