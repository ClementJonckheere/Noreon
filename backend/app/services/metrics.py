"""Observabilité produit — Noreon mesure la qualité de son propre travail.

Deux tableaux de bord, calculés hors-ligne, sans rien d'identifiant :

- **Qualité** (rassure le client, pilote le produit) : temps moyen d'analyse,
  confiance moyenne, % de questions résolues, % de clarifications demandées,
  % de SQL validés par les garde-fous.
- **Coûts** (pilotage économique) : jetons LLM, temps LLM, coût estimé, taux
  d'utilisation du cache, temps SQL.

Source : le journal d'audit immuable (`QueryLog`) + les compteurs de télémétrie
en mémoire (`telemetry`). Aucune donnée métier brute n'y transite.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.query_log import QueryLog
from app.services import telemetry

# Statuts journalisés côté chat :
#   ok          → réponse produite (SQL exécuté)
#   clarification→ question renvoyée (ambiguë)
#   unanswerable → refus honnête (information absente)
#   blocked      → refusé par les garde-fous / la gouvernance
#   error        → échec d'exécution
_RESOLVED = {"ok"}
_GENERATED_SQL = {"ok", "blocked", "error"}  # cas où un SQL a été produit


def product_metrics(
    db: Session, *, tenant_id: int | None = None, connection_id: int | None = None,
    days: int = 30,
) -> dict:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    stmt = select(
        QueryLog.status, QueryLog.duration_ms, QueryLog.estimated_cost,
        QueryLog.confidence,
    ).where(QueryLog.created_at >= since)
    if tenant_id is not None:
        stmt = stmt.where(QueryLog.tenant_id == tenant_id)
    if connection_id is not None:
        stmt = stmt.where(QueryLog.connection_id == connection_id)
    rows = db.execute(stmt).all()

    total = len(rows)
    by_status: dict[str, int] = {}
    durations: list[int] = []
    costs: list[float] = []
    confidences: list[float] = []
    for status, duration, cost, confidence in rows:
        by_status[status] = by_status.get(status, 0) + 1
        if status == "ok" and duration is not None:
            durations.append(duration)
        if status == "ok" and cost is not None:
            costs.append(cost)
        if status == "ok" and confidence and isinstance(confidence, dict):
            score = confidence.get("score")
            if isinstance(score, (int, float)):
                confidences.append(float(score))

    resolved = sum(by_status.get(s, 0) for s in _RESOLVED)
    clarifications = by_status.get("clarification", 0)
    generated = sum(by_status.get(s, 0) for s in _GENERATED_SQL)
    validated_sql = by_status.get("ok", 0)

    def pct(n: int, d: int) -> float | None:
        return round(n / d, 4) if d else None

    def avg(xs: list) -> float | None:
        return round(sum(xs) / len(xs), 2) if xs else None

    tel = telemetry.snapshot()

    return {
        "window_days": days,
        "total_analyses": total,
        "by_status": by_status,
        # --- Qualité (rassure le client, pilote le produit) ---
        "quality": {
            "avg_duration_ms": avg(durations),
            "avg_confidence": avg(confidences),
            "resolution_rate": pct(resolved, total),
            "clarification_rate": pct(clarifications, total),
            "sql_validation_rate": pct(validated_sql, generated),
        },
        # --- Coûts (pilotage économique) ---
        "costs": {
            "llm_calls": tel["llm_calls"],
            "llm_tokens_total": tel["llm_tokens_total"],
            "llm_ms_avg": tel["llm_ms_avg"],
            "avg_sql_cost": avg(costs),
            "avg_sql_ms": avg(durations),
            "cache_hit_rate": tel["cache_hit_rate"],
            "cache_hits": tel["cache_hits"],
            "cache_misses": tel["cache_misses"],
        },
    }
