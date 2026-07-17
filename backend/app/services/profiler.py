"""Profilage des données (Module 3).

Pour chaque colonne : taux de NULL, valeurs distinctes, min/max, moyenne,
longueur moyenne, top valeurs, exemples, détection du type réel et des PII.

Stratégie de volume (cahier des charges) :
- tables < seuil (défaut 1 M lignes) : profilage exhaustif ;
- tables ≥ seuil : échantillonnage (TABLESAMPLE / échantillon aléatoire),
  avec indication explicite du caractère échantillonné.

Sobriété : une requête agrégée par table (plutôt qu'une par colonne) pour les
statistiques principales, exécutée en lecture seule avec timeout.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from psycopg import sql as pgsql
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.models.connection import Connection
from app.models.profile import ColumnProfile
from app.models.schema_catalog import DbColumn, DbTable
from app.services import pii
from app.services.source_db import SourceConfig, open_source

log = get_logger("noreon.profiler")

_NUMERIC_TYPES = {
    "integer", "bigint", "smallint", "numeric", "decimal", "real",
    "double precision", "money", "int", "int2", "int4", "int8", "float", "float4", "float8",
}
_SORTABLE_UNSAFE = {"json", "jsonb", "xml", "bytea", "array", "USER-DEFINED"}

_TEXT_TYPES = {"character varying", "varchar", "text", "char", "character", "citext", "bpchar"}

# Motifs POSIX (côté PostgreSQL, opérateur ~) pour compter les valeurs
# NON conformes au format attendu — base auditable de la dimension Validité.
_FORMAT_REGEX = {
    "email": r"^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$",
    "phone": r"^\+?[0-9 ().-]{8,20}$",
    "iban": r"^[A-Z]{2}[0-9]{2}[A-Z0-9]{10,30}$",
    "siret": r"^[0-9]{14}$",
    "date": r"^[0-9]{4}-[0-9]{2}-[0-9]{2}([ T][0-9]{2}:[0-9]{2}([0-9:]*)?)?$",
    "integer": r"^-?[0-9]+$",
    "numeric": r"^-?[0-9]+([.,][0-9]+)?$",
}

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2}(:\d{2})?)?$")
_INT_RE = re.compile(r"^-?\d+$")
_FLOAT_RE = re.compile(r"^-?\d+[.,]\d+$")
_BOOL_VALUES = {"true", "false", "t", "f", "0", "1", "yes", "no", "oui", "non"}


@dataclass
class ColumnProfileData:
    column_name: str
    declared_type: str
    sampled: bool
    sample_size: int
    row_count_estimate: int | None
    null_rate: float | None = None
    null_count: int | None = None
    non_null_count: int | None = None
    invalid_count: int | None = None
    format_checked: str | None = None
    distinct_count: int | None = None
    distinct_ratio: float | None = None
    min_value: str | None = None
    max_value: str | None = None
    mean_value: float | None = None
    avg_length: float | None = None
    detected_type: str | None = None
    pii_type: str | None = None
    top_values: list = field(default_factory=list)
    sample_values: list = field(default_factory=list)


def _is_numeric(dtype: str) -> bool:
    return dtype.lower() in _NUMERIC_TYPES


def _sortable(dtype: str) -> bool:
    return not any(u in dtype.lower() for u in _SORTABLE_UNSAFE)


def _jsonify(v):
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (bytes, bytearray, memoryview)):
        return "<binary>"
    return v


def _detect_type(declared: str, samples: list) -> str:
    d = declared.lower()
    if _is_numeric(d):
        return "integer" if any(k in d for k in ("int", "serial")) else "numeric"
    if "bool" in d:
        return "boolean"
    if any(k in d for k in ("date", "time")):
        return "datetime"
    # Type réel derrière un VARCHAR/TEXT
    values = [str(v).strip() for v in samples if v is not None and str(v).strip()]
    if not values:
        return "text"
    if all(_DATE_RE.match(v) for v in values):
        return "datetime (stocké en texte)"
    if all(_INT_RE.match(v) for v in values):
        return "integer (stocké en texte)"
    if all(_FLOAT_RE.match(v) or _INT_RE.match(v) for v in values):
        return "numeric (stocké en texte)"
    if all(v.lower() in _BOOL_VALUES for v in values):
        return "boolean (stocké en texte)"
    return "text"


def _sample_clause(estimated_rows: int | None) -> tuple[bool, str]:
    """Retourne (sampled, clause SQL de la source à profiler)."""
    threshold = settings.profiling_sample_threshold
    if estimated_rows is not None and estimated_rows >= threshold:
        # Pourcentage visant ~sample_size lignes, borné [0.01%, 100%].
        pct = max(0.01, min(100.0, settings.profiling_sample_size * 100.0 / estimated_rows))
        return True, f"TABLESAMPLE SYSTEM ({pct:.4f})"
    return False, ""


def profile_table(cfg: SourceConfig, table: DbTable, columns: list[DbColumn]) -> list[ColumnProfileData]:
    sampled, sample_clause = _sample_clause(table.estimated_rows)
    ident = pgsql.SQL("{}.{}").format(
        pgsql.Identifier(table.schema_name), pgsql.Identifier(table.table_name)
    )
    src = pgsql.SQL("{} {}").format(ident, pgsql.SQL(sample_clause)) if sample_clause else ident

    # 1) Une requête agrégée pour les stats principales de toutes les colonnes.
    select_items = [pgsql.SQL("count(*) AS __n")]
    for col in columns:
        c = pgsql.Identifier(col.name)
        alias = col.name
        select_items.append(pgsql.SQL("count({}) AS {}").format(c, pgsql.Identifier(f"{alias}__nn")))
        select_items.append(pgsql.SQL("count(distinct {}) AS {}").format(c, pgsql.Identifier(f"{alias}__d")))
        select_items.append(pgsql.SQL("avg(length({}::text)) AS {}").format(c, pgsql.Identifier(f"{alias}__len")))
        if _sortable(col.data_type):
            select_items.append(pgsql.SQL("min({})::text AS {}").format(c, pgsql.Identifier(f"{alias}__min")))
            select_items.append(pgsql.SQL("max({})::text AS {}").format(c, pgsql.Identifier(f"{alias}__max")))
        if _is_numeric(col.data_type):
            select_items.append(pgsql.SQL("avg({}::double precision) AS {}").format(c, pgsql.Identifier(f"{alias}__avg")))

    agg_query = pgsql.SQL("SELECT {} FROM {}").format(
        pgsql.SQL(", ").join(select_items), src
    )

    results: list[ColumnProfileData] = []
    with open_source(cfg, statement_timeout_ms=settings.sql_timeout_seconds * 1000) as conn:
        with conn.cursor() as cur:
            cur.execute(agg_query)
            row = dict(zip([d.name for d in cur.description], cur.fetchone()))
            n = int(row["__n"]) or 0

            for col in columns:
                a = col.name
                nn = int(row.get(f"{a}__nn") or 0)
                data = ColumnProfileData(
                    column_name=col.name,
                    declared_type=col.data_type,
                    sampled=sampled,
                    sample_size=n,
                    row_count_estimate=table.estimated_rows,
                    null_rate=(1 - nn / n) if n else None,
                    null_count=(n - nn) if n else None,
                    non_null_count=nn,
                    distinct_count=int(row.get(f"{a}__d") or 0),
                    distinct_ratio=((row.get(f"{a}__d") or 0) / nn) if nn else None,
                    min_value=_str_or_none(row.get(f"{a}__min")),
                    max_value=_str_or_none(row.get(f"{a}__max")),
                    mean_value=_float_or_none(row.get(f"{a}__avg")),
                    avg_length=_float_or_none(row.get(f"{a}__len")),
                )
                results.append(data)

            # 2) Top valeurs + exemples (par colonne, sur l'échantillon).
            for data, col in zip(results, columns):
                c = pgsql.Identifier(col.name)
                try:
                    cur.execute(
                        pgsql.SQL(
                            "SELECT {c}::text AS v, count(*) AS n FROM {src} "
                            "WHERE {c} IS NOT NULL GROUP BY {c} ORDER BY n DESC LIMIT 10"
                        ).format(c=c, src=src)
                    )
                    data.top_values = [{"value": v, "count": int(cnt)} for v, cnt in cur.fetchall()]
                    data.sample_values = [tv["value"] for tv in data.top_values[:5]]
                except Exception as exc:  # noqa: BLE001 - colonnes non groupables
                    log.debug("top values skipped for %s.%s: %s", table.table_name, col.name, exc)
                    conn.rollback()

                data.detected_type = _detect_type(col.data_type, data.sample_values)
                data.pii_type = pii.detect(col.name, data.sample_values)

                # 3) Validité : nombre exact de valeurs mal formées (pour les
                # colonnes TEXTE dont on a détecté un format attendu).
                fmt = _expected_format(col.data_type, data.detected_type, data.pii_type)
                if fmt and data.non_null_count:
                    try:
                        cur.execute(
                            pgsql.SQL(
                                "SELECT count(*) FROM {src} "
                                "WHERE {c} IS NOT NULL AND {c}::text !~ %s"
                            ).format(c=c, src=src),
                            (_FORMAT_REGEX[fmt],),
                        )
                        data.invalid_count = int(cur.fetchone()[0])
                        data.format_checked = fmt
                    except Exception as exc:  # noqa: BLE001
                        log.debug("validity check skipped for %s.%s: %s", table.table_name, col.name, exc)
                        conn.rollback()

    return results


def _expected_format(declared_type: str, detected_type: str | None, pii_type: str | None) -> str | None:
    """Format attendu d'une colonne TEXTE, sinon None (validité non applicable).

    On ne vérifie que les colonnes textuelles : pour les types natifs (date,
    integer…), le format est garanti par le SGBD et la validité n'est pas un
    enjeu de qualité de donnée.
    """
    if declared_type.lower() not in _TEXT_TYPES:
        return None
    if pii_type in ("email", "phone", "iban", "siret"):
        return pii_type
    dt = (detected_type or "").lower()
    if "stocké en texte" in dt or "stocke en texte" in dt:
        if "date" in dt:
            return "date"
        if "integer" in dt:
            return "integer"
        if "numeric" in dt:
            return "numeric"
    return None


def persist_profiles(db: Session, conn: Connection, table: DbTable, profiles: list[ColumnProfileData]) -> None:
    for p in profiles:
        db.add(ColumnProfile(
            connection_id=conn.id,
            schema_name=table.schema_name,
            table_name=table.table_name,
            column_name=p.column_name,
            sampled=p.sampled,
            sample_size=p.sample_size,
            row_count_estimate=p.row_count_estimate,
            null_rate=p.null_rate,
            null_count=p.null_count,
            non_null_count=p.non_null_count,
            invalid_count=p.invalid_count,
            format_checked=p.format_checked,
            distinct_count=p.distinct_count,
            distinct_ratio=p.distinct_ratio,
            min_value=p.min_value,
            max_value=p.max_value,
            mean_value=p.mean_value,
            avg_length=p.avg_length,
            declared_type=p.declared_type,
            detected_type=p.detected_type,
            pii_type=p.pii_type,
            top_values=[{"value": _jsonify(tv["value"]), "count": tv["count"]} for tv in p.top_values],
            sample_values=[_jsonify(v) for v in p.sample_values],
        ))
    db.flush()


def _str_or_none(v) -> str | None:
    return None if v is None else str(v)


def _float_or_none(v) -> float | None:
    return None if v is None else float(v)
