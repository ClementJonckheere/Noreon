"""Garde-fous d'analyse SQL (Module 8, PIT-6/PIT-8).

Défense en profondeur AVANT toute exécution :
1. Une seule instruction.
2. Lecture seule stricte : blocage syntaxique de tout DDL/DML.
3. LIMIT automatique sur les résultats bruts.

L'analyse repose sur sqlglot (AST), pas sur des expressions régulières
fragiles. Le coût estimé (EXPLAIN) est vérifié séparément par l'executor,
qui a accès à la base source.
"""
from __future__ import annotations

from dataclasses import dataclass

import sqlglot
from sqlglot import exp

# Types de nœuds interdits (DDL / DML / commandes) — lecture seule stricte.
_FORBIDDEN = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Merge,
    exp.Drop,
    exp.Create,
    exp.Alter,
    exp.TruncateTable,
    exp.Grant,
    exp.Command,  # SET, CALL, VACUUM, COPY, GRANT, etc. non parsés finement
)


class SQLGuardError(ValueError):
    """Requête rejetée par les garde-fous (avec motif explicite)."""


@dataclass
class GuardedSQL:
    sql: str  # SQL sûr, prêt à exécuter (LIMIT appliqué)
    original_sql: str
    limit_applied: int | None
    is_aggregate: bool


def _statements(raw: str, dialect: str = "postgres") -> list[exp.Expression]:
    try:
        parsed = sqlglot.parse(raw, read=dialect)
    except Exception as exc:  # noqa: BLE001
        raise SQLGuardError(f"SQL non analysable : {exc}") from exc
    return [s for s in parsed if s is not None]


def _assert_read_only(statement: exp.Expression) -> None:
    if isinstance(statement, _FORBIDDEN):
        raise SQLGuardError(
            "Instruction rejetée : seules les requêtes de lecture (SELECT) sont autorisées. "
            "Noreon n'écrit jamais dans les bases sources."
        )
    for node in statement.walk():
        node_expr = node[0] if isinstance(node, tuple) else node
        if isinstance(node_expr, _FORBIDDEN):
            raise SQLGuardError(
                "Instruction rejetée : présence d'une opération d'écriture/DDL "
                f"({node_expr.key.upper()}). Lecture seule stricte."
            )


def _is_select(statement: exp.Expression) -> bool:
    if isinstance(statement, (exp.Select, exp.Union, exp.Intersect, exp.Except)):
        return True
    # WITH ... SELECT
    if isinstance(statement, exp.With):
        return True
    if isinstance(statement, exp.Subquery):
        return True
    # sqlglot enveloppe parfois le SELECT ; on vérifie la présence d'un SELECT.
    return statement.find(exp.Select) is not None and not isinstance(statement, _FORBIDDEN)


def _has_top_level_limit(statement: exp.Expression) -> int | None:
    limit = statement.args.get("limit")
    if isinstance(limit, exp.Limit):
        try:
            return int(limit.expression.this)
        except (AttributeError, TypeError, ValueError):
            return -1  # LIMIT présent mais non littéral (paramètre) → on ne touche pas
    return None


def _looks_aggregate(statement: exp.Expression) -> bool:
    select = statement if isinstance(statement, exp.Select) else statement.find(exp.Select)
    if select is None:
        return False
    if select.args.get("group"):
        return True
    for proj in select.expressions:
        if proj.find(exp.AggFunc) is not None:
            return True
    return False


def guard(raw_sql: str, row_limit: int, dialect: str = "postgres") -> GuardedSQL:
    """Valide et sécurise une requête. Lève SQLGuardError si non conforme."""
    raw_sql = raw_sql.strip().rstrip(";").strip()
    if not raw_sql:
        raise SQLGuardError("Requête vide.")

    statements = _statements(raw_sql, dialect=dialect)
    if len(statements) != 1:
        raise SQLGuardError(
            f"Une seule instruction autorisée par exécution ({len(statements)} détectées)."
        )

    statement = statements[0]
    _assert_read_only(statement)
    if not _is_select(statement):
        raise SQLGuardError("Seules les requêtes SELECT (éventuellement avec CTE) sont autorisées.")

    is_aggregate = _looks_aggregate(statement)
    existing = _has_top_level_limit(statement)
    limit_applied: int | None = None

    if existing is None:
        # Pas de LIMIT → on en impose un (sauf agrégat mono-ligne, mais LIMIT reste sûr).
        statement = statement.limit(row_limit)
        limit_applied = row_limit
    elif existing == -1:
        limit_applied = None  # LIMIT paramétré, laissé tel quel
    elif existing > row_limit:
        statement.set("limit", exp.Limit(expression=exp.Literal.number(row_limit)))
        limit_applied = row_limit
    else:
        limit_applied = existing

    safe_sql = statement.sql(dialect=dialect)
    return GuardedSQL(
        sql=safe_sql,
        original_sql=raw_sql,
        limit_applied=limit_applied,
        is_aggregate=is_aggregate,
    )
