"""Télémétrie interne — Noreon mesure son propre fonctionnement.

Compteurs légers, en mémoire et thread-safe, pour les signaux qui ne sont PAS
déjà dans le journal d'audit (`QueryLog`) : temps passé dans la couche LLM,
volume de jetons consommés, taux d'utilisation du cache d'Insights.

Ces compteurs alimentent le tableau de bord d'observabilité (service `metrics`)
avec les agrégats du journal d'audit. Rien d'identifiant n'y transite — que des
mesures de coût et de performance.
"""
from __future__ import annotations

import threading

_LOCK = threading.Lock()
_C = {
    "llm_calls": 0,
    "llm_ms": 0.0,       # temps cumulé dans la génération SQL (couche LLM)
    "llm_tokens": 0,     # jetons consommés (0 pour le provider heuristique)
    "cache_hits": 0,     # Insights servis depuis le cache
    "cache_misses": 0,   # Insights recalculés
}


def record_llm(ms: float, tokens: int = 0) -> None:
    with _LOCK:
        _C["llm_calls"] += 1
        _C["llm_ms"] += ms
        _C["llm_tokens"] += tokens


def record_cache(hit: bool) -> None:
    with _LOCK:
        _C["cache_hits" if hit else "cache_misses"] += 1


def snapshot() -> dict:
    with _LOCK:
        c = dict(_C)
    calls = c["llm_calls"] or 1
    cache_total = c["cache_hits"] + c["cache_misses"]
    return {
        "llm_calls": c["llm_calls"],
        "llm_ms_total": round(c["llm_ms"], 1),
        "llm_ms_avg": round(c["llm_ms"] / calls, 2),
        "llm_tokens_total": c["llm_tokens"],
        "cache_hits": c["cache_hits"],
        "cache_misses": c["cache_misses"],
        "cache_hit_rate": round(c["cache_hits"] / cache_total, 4) if cache_total else None,
    }


def reset() -> None:
    with _LOCK:
        for k in _C:
            _C[k] = 0 if isinstance(_C[k], int) else 0.0
