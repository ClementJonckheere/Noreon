"""Phase 2 — shadow : projection de l'EXÉCUTION legacy (règle #3).

On projette ce que le legacy a RÉELLEMENT exécuté (SQL, tables, colonnes,
agrégations, GROUP BY, jointures), pas le texte de la réponse — sinon on
comparerait deux intentions au lieu d'une intention résolue vs une exécution.

Parsing SQL HEURISTIQUE et déterministe (suffisant pour la sécurité analytique) ;
il ne prétend pas être un parseur SQL complet.
"""
from __future__ import annotations

import re

_AGG_RE = re.compile(r"\b(sum|avg|min|max|count)\s*\(", re.IGNORECASE)
_COUNT_STAR_RE = re.compile(r"\bcount\s*\(\s*\*\s*\)", re.IGNORECASE)
_COUNT_DISTINCT_RE = re.compile(r"\bcount\s*\(\s*distinct\b", re.IGNORECASE)
_JOIN_RE = re.compile(r"\bjoin\b", re.IGNORECASE)
_GROUP_BY_RE = re.compile(r"\bgroup\s+by\b(.+?)(\border\s+by\b|\blimit\b|\)|$)", re.IGNORECASE | re.DOTALL)
# Pré-agrégation = une sous-requête agrégée (SELECT … GROUP BY … dans des parenthèses).
_SUBQUERY_GROUP_RE = re.compile(r"\(\s*select\b.+?\bgroup\s+by\b.+?\)", re.IGNORECASE | re.DOTALL)


def project_legacy_execution(response) -> dict:
    """Signature d'exécution du legacy (JSON-sérialisable, sans valeurs de données).
    Renvoie {sql_present, aggregations, count_star, count_distinct, joins, group_by,
    pre_aggregated, tables}."""
    sql = getattr(response, "sql", None) or ""
    tables = list(getattr(response, "tables_used", []) or [])
    if not sql:
        return {"sql_present": False, "aggregations": [], "count_star": False,
                "count_distinct": False, "joins": 0, "group_by": [], "pre_aggregated": False,
                "tables": tables}

    aggs = sorted({m.lower() for m in _AGG_RE.findall(sql)})
    gb = _GROUP_BY_RE.search(sql)
    group_by = []
    if gb:
        group_by = [g.strip() for g in re.split(r",", gb.group(1)) if g.strip()][:12]
    return {
        "sql_present": True,
        "aggregations": aggs,
        "count_star": bool(_COUNT_STAR_RE.search(sql)),
        "count_distinct": bool(_COUNT_DISTINCT_RE.search(sql)),
        "joins": len(_JOIN_RE.findall(sql)),
        "group_by": group_by,
        "pre_aggregated": bool(_SUBQUERY_GROUP_RE.search(sql)),
        "tables": tables,
    }
