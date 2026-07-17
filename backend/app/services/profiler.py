"""Profilage des données (Module 3) — portable multi-sources (V1.0).

Le profilage ne dépend plus d'un SGBD : il s'appuie sur les primitives de
l'adaptateur (`fetch`, `quote_ident`, `sample_source`, `length_of`) et sur du
SQL standard. La validité (conformité de format) est calculée EN PYTHON sur un
échantillon, donc identique sur PostgreSQL, MySQL et fichiers.

Stratégie de volume : profilage exhaustif sous le seuil, échantillonné au-delà,
avec indication explicite du caractère échantillonné.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.connection import Connection
from app.models.profile import ColumnProfile
from app.models.schema_catalog import DbColumn, DbTable
from app.services import pii
from app.services.sources.base import SourceAdapter

log = get_logger("noreon.profiler")

_TEXT_TYPES = {
    "character varying", "varchar", "text", "char", "character", "citext", "bpchar",
    "tinytext", "mediumtext", "longtext", "nvarchar", "nchar", "string", "clob",
}

_VALIDITY_SAMPLE = 2000  # nb max de valeurs vérifiées pour la validité

# Motifs Python (portables) pour la dimension Validité.
_FORMAT_RE = {
    "email": re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$"),
    "phone": re.compile(r"^\+?[0-9 ().-]{8,20}$"),
    "iban": re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9]{10,30}$"),
    "siret": re.compile(r"^\d{14}$"),
    "date": re.compile(r"^\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2}(:\d{2})?)?$"),
    "integer": re.compile(r"^-?\d+$"),
    "numeric": re.compile(r"^-?\d+([.,]\d+)?$"),
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


def _jsonify(v):
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (bytes, bytearray, memoryview)):
        return "<binary>"
    return v


def _detect_type(declared: str, samples: list, is_numeric: bool) -> str:
    d = declared.lower()
    if is_numeric:
        return "integer" if any(k in d for k in ("int", "serial")) else "numeric"
    if "bool" in d:
        return "boolean"
    if any(k in d for k in ("date", "time")):
        return "datetime"
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


def _expected_format(declared_type: str, detected_type: str | None, pii_type: str | None) -> str | None:
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


def profile_table(adapter: SourceAdapter, table: DbTable, columns: list[DbColumn]) -> list[ColumnProfileData]:
    src, sampled = adapter.sample_source(table.schema_name, table.table_name, table.estimated_rows)

    # 1) Requête agrégée standard pour toutes les colonnes.
    select_items = ["count(*) AS __n"]
    for col in columns:
        c = adapter.quote_ident(col.name)
        a = col.name
        select_items.append(f"count({c}) AS {adapter.quote_ident(a + '__nn')}")
        select_items.append(f"count(distinct {c}) AS {adapter.quote_ident(a + '__d')}")
        select_items.append(f"avg({adapter.length_of(c)}) AS {adapter.quote_ident(a + '__len')}")
        if adapter.is_sortable_type(col.data_type):
            select_items.append(f"min({c}) AS {adapter.quote_ident(a + '__min')}")
            select_items.append(f"max({c}) AS {adapter.quote_ident(a + '__max')}")
        if adapter.is_numeric_type(col.data_type):
            select_items.append(f"avg({c}) AS {adapter.quote_ident(a + '__avg')}")

    agg_sql = f"SELECT {', '.join(select_items)} FROM {src}"
    cols_out, rows_out = adapter.fetch(agg_sql)
    row = dict(zip(cols_out, rows_out[0])) if rows_out else {}
    n = int(row.get("__n") or 0)

    results: list[ColumnProfileData] = []
    for col in columns:
        a = col.name
        nn = int(row.get(f"{a}__nn") or 0)
        results.append(ColumnProfileData(
            column_name=col.name, declared_type=col.data_type, sampled=sampled,
            sample_size=n, row_count_estimate=table.estimated_rows,
            null_rate=(1 - nn / n) if n else None,
            null_count=(n - nn) if n else None, non_null_count=nn,
            distinct_count=int(row.get(f"{a}__d") or 0),
            distinct_ratio=((row.get(f"{a}__d") or 0) / nn) if nn else None,
            min_value=_str_or_none(row.get(f"{a}__min")),
            max_value=_str_or_none(row.get(f"{a}__max")),
            mean_value=_float_or_none(row.get(f"{a}__avg")),
            avg_length=_float_or_none(row.get(f"{a}__len")),
        ))

    # 2) Top valeurs + validité (échantillon) par colonne.
    for data, col in zip(results, columns):
        c = adapter.quote_ident(col.name)
        try:
            _, tv_rows = adapter.fetch(
                f"SELECT {c} AS v, count(*) AS n FROM {src} WHERE {c} IS NOT NULL "
                f"GROUP BY {c} ORDER BY n DESC LIMIT 10"
            )
            data.top_values = [{"value": v, "count": int(cnt)} for v, cnt in tv_rows]
            data.sample_values = [tv["value"] for tv in data.top_values[:5]]
        except Exception as exc:  # noqa: BLE001 - colonnes non groupables
            log.debug("top values skipped for %s.%s: %s", table.table_name, col.name, exc)

        is_num = adapter.is_numeric_type(col.data_type)
        data.detected_type = _detect_type(col.data_type, data.sample_values, is_num)
        data.pii_type = pii.detect(col.name, data.sample_values)

        fmt = _expected_format(col.data_type, data.detected_type, data.pii_type)
        if fmt and data.non_null_count:
            data.invalid_count, data.format_checked = _validity(adapter, src, c, fmt)

    return results


def _validity(adapter: SourceAdapter, src: str, quoted_col: str, fmt: str) -> tuple[int | None, str | None]:
    """Compte les valeurs non conformes au format, EN PYTHON (portable)."""
    try:
        _, rows = adapter.fetch(
            f"SELECT {quoted_col} FROM {src} WHERE {quoted_col} IS NOT NULL LIMIT {_VALIDITY_SAMPLE}"
        )
    except Exception:  # noqa: BLE001
        return None, None
    pattern = _FORMAT_RE.get(fmt)
    if pattern is None or not rows:
        return None, None
    invalid = sum(1 for (v,) in rows if not pattern.match(str(v).strip()))
    return invalid, fmt


def persist_profiles(db: Session, conn: Connection, table: DbTable, profiles: list[ColumnProfileData]) -> None:
    for p in profiles:
        db.add(ColumnProfile(
            connection_id=conn.id, schema_name=table.schema_name, table_name=table.table_name,
            column_name=p.column_name, sampled=p.sampled, sample_size=p.sample_size,
            row_count_estimate=p.row_count_estimate, null_rate=p.null_rate,
            null_count=p.null_count, non_null_count=p.non_null_count,
            invalid_count=p.invalid_count, format_checked=p.format_checked,
            distinct_count=p.distinct_count, distinct_ratio=p.distinct_ratio,
            min_value=p.min_value, max_value=p.max_value, mean_value=p.mean_value,
            avg_length=p.avg_length, declared_type=p.declared_type,
            detected_type=p.detected_type, pii_type=p.pii_type,
            top_values=[{"value": _jsonify(tv["value"]), "count": tv["count"]} for tv in p.top_values],
            sample_values=[_jsonify(v) for v in p.sample_values],
        ))
    db.flush()


def _str_or_none(v) -> str | None:
    return None if v is None else str(v)


def _float_or_none(v) -> float | None:
    return None if v is None else float(v)
