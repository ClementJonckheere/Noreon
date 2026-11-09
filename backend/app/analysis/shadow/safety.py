"""Phase 2 — shadow : observation de SÉCURITÉ ANALYTIQUE (règles #5/#6).

Compare la protection anti-double-comptage du plan résolu C6 à ce que le legacy a
RÉELLEMENT exécuté. Définition EXTRÊMEMENT RESTRICTIVE : `llm_safer` uniquement
quand une différence de sécurité OBSERVABLE et DÉTERMINISTE existe (ex. C6 impose
pre_aggregation là où le legacy fait un SUM après 1→n sans protection ; ou C6
impose count_distinct là où le legacy fait count(*)). JAMAIS parce que C6 porte
plus de métadonnées.

`llm_safer`/`fallback_safer` sont des signaux d'INVESTIGATION (revue humaine
prioritaire), pas une base d'activation automatique (#6) : le legacy peut avoir
une protection que notre projection n'a pas su reconnaître.
"""
from __future__ import annotations

ANALYTICAL_SAFETY_VERSION = "1.0"

SAME_SAFETY = "same_safety"
LLM_SAFER = "llm_safer"
FALLBACK_SAFER = "fallback_safer"
NOT_COMPARABLE = "not_comparable"

_PROTECTED_STRATS = {"pre_aggregation", "count_distinct", "semi_additive"}


def _c6_view(resolved_plan: dict | None) -> dict | None:
    """Vue sécurité du plan C6 pour le goal principal (statut supporté requis)."""
    if not resolved_plan:
        return None
    res = resolved_plan.get("resolution") or []
    if not res:
        return None
    item = res[0]
    if item.get("status") not in ("SUPPORTED", "PARTIAL"):
        return None                                  # C6 n'a pas produit de plan exécutable → pas de comparaison
    grain = item.get("grain") or {}
    return {
        "fanout": bool(grain.get("creates_row_multiplication")),
        "strategy": grain.get("aggregation_strategy"),
        "protected": grain.get("aggregation_strategy") in _PROTECTED_STRATS,
        "is_count_distinct": grain.get("aggregation_strategy") == "count_distinct",
    }


def analytical_safety_delta(resolved_plan: dict | None, legacy_exec: dict | None) -> tuple[str, dict]:
    """Renvoie (verdict, détail structuré SANS nom de colonne)."""
    c6 = _c6_view(resolved_plan)
    if c6 is None or not legacy_exec or not legacy_exec.get("sql_present"):
        return NOT_COMPARABLE, {"reason": "informations insuffisantes des deux côtés"}

    legacy_join = legacy_exec.get("joins", 0) > 0
    legacy_sum = any(a in ("sum", "avg") for a in legacy_exec.get("aggregations", []))
    legacy_count_star = legacy_exec.get("count_star", False)
    legacy_count_distinct = legacy_exec.get("count_distinct", False)
    legacy_preagg = legacy_exec.get("pre_aggregated", False)

    detail = {"c6": c6, "legacy": {"join": legacy_join, "sum": legacy_sum,
                                   "count_star": legacy_count_star,
                                   "count_distinct": legacy_count_distinct, "pre_agg": legacy_preagg}}

    # llm_safer — cas 1 : C6 voit un fanout et protège, le legacy fait un SUM/AVG
    # sur jointure SANS pré-agrégation → double comptage observé côté legacy.
    if c6["fanout"] and c6["protected"] and legacy_sum and legacy_join and not legacy_preagg:
        return LLM_SAFER, {**detail, "why": "C6 pre_aggregation vs SUM legacy non protégé sur jointure"}
    # llm_safer — cas 2 : C6 impose count_distinct, le legacy fait count(*) sur jointure.
    if c6["is_count_distinct"] and legacy_count_star and legacy_join and not legacy_count_distinct:
        return LLM_SAFER, {**detail, "why": "C6 count_distinct vs count(*) legacy sur jointure"}

    # fallback_safer : le legacy protège explicitement là où le plan C6 n'a PAS
    # détecté/imposé de protection alors qu'une jointure existe.
    if legacy_join and (legacy_preagg or legacy_count_distinct) and not c6["fanout"]:
        return FALLBACK_SAFER, {**detail, "why": "protection legacy là où C6 n'a pas vu de fanout"}

    # same_safety : soit les deux protègent, soit aucun fanout des deux côtés.
    both_protected = (not c6["fanout"] or c6["protected"]) and (not legacy_join or legacy_preagg
                                                                or legacy_count_distinct or not legacy_sum)
    if both_protected:
        return SAME_SAFETY, detail
    return NOT_COMPARABLE, {**detail, "reason": "protections non alignées mais non concluantes"}
