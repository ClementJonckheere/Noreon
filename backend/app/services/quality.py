"""Score qualité auditable (Module 4).

Chaque colonne, table, relation et base reçoit un score qualité **auditable** :
une moyenne pondérée de cinq dimensions, chacune accompagnée de son détail
chiffré et vérifiable (« Complétude 99,2 % (312 NULL sur 39 000) »), jamais
d'une justification générique.

Les pondérations par défaut viennent du cahier des charges et sont
configurables par entreprise (TenantSettings.quality_weights). Une dimension
non applicable (ex. fraîcheur d'une colonne texte) est exclue et les poids
sont renormalisés sur les dimensions applicables.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.connection import Connection
from app.models.profile import ColumnProfile
from app.models.quality import QualityScore
from app.models.query_log import QueryLog
from app.models.schema_catalog import DbColumn, DbRelation, DbTable, SchemaSnapshot
from app.services.sources.base import SourceAdapter

log = get_logger("noreon.quality")

DEFAULT_WEIGHTS = {
    "completeness": 0.30,
    "validity": 0.25,
    "uniqueness": 0.15,
    "consistency": 0.15,
    "freshness": 0.15,
}

# Fraîcheur : période de grâce (score plein) puis décroissance linéaire jusqu'à 0.
FRESHNESS_GRACE_DAYS = 90
FRESHNESS_ZERO_DAYS = 730

_FMT_LABEL = {
    "email": "email",
    "phone": "téléphone",
    "iban": "IBAN",
    "siret": "SIRET",
    "date": "date",
    "integer": "entier",
    "numeric": "nombre",
}


@dataclass
class Dimension:
    name: str
    applicable: bool
    score: float | None
    weight: float
    detail: str

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "applicable": self.applicable,
            "score": round(self.score, 4) if self.score is not None else None,
            "weight": self.weight,
            "detail": self.detail,
        }


@dataclass
class EntityQuality:
    level: str
    score: float
    dimensions: list[Dimension]
    detail: str
    schema_name: str | None = None
    table_name: str | None = None
    column_name: str | None = None
    relation_ref: str | None = None


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%".replace(".", ",")


def _weighted(dims: list[Dimension]) -> float:
    applicable = [d for d in dims if d.applicable and d.score is not None]
    total_w = sum(d.weight for d in applicable)
    if total_w == 0:
        return 1.0
    return sum(d.weight * d.score for d in applicable) / total_w


# --------------------------------------------------------------------------
# Dimensions au niveau colonne
# --------------------------------------------------------------------------
def _completeness(p: ColumnProfile, w: float) -> Dimension:
    total = (p.null_count or 0) + (p.non_null_count or 0)
    if total == 0:
        return Dimension("Complétude", True, 1.0, w, "Aucune ligne à évaluer.")
    score = (p.non_null_count or 0) / total
    scope = " sur échantillon" if p.sampled else ""
    return Dimension(
        "Complétude", True, score, w,
        f"Complétude {_pct(score)} ({p.null_count or 0} NULL sur {total}{scope}).",
    )


def _validity(p: ColumnProfile, w: float) -> Dimension:
    if p.format_checked is None or p.invalid_count is None or not p.non_null_count:
        return Dimension("Validité", False, None, w, "Non applicable (aucun format attendu).")
    score = 1 - p.invalid_count / p.non_null_count
    label = _FMT_LABEL.get(p.format_checked, p.format_checked)
    return Dimension(
        "Validité", True, score, w,
        f"Validité {_pct(score)} ({p.invalid_count} valeur(s) au format {label} "
        f"invalide sur {p.non_null_count}).",
    )


def _uniqueness(p: ColumnProfile, w: float, is_pk: bool) -> Dimension:
    temporal = (p.detected_type or "").startswith("datetime") or any(
        k in (p.declared_type or "").lower() for k in ("date", "timestamp", "time")
    )
    expected = (
        is_pk
        or p.pii_type in ("email", "iban", "siret")
        or (
            not temporal
            and p.distinct_ratio is not None
            and p.distinct_ratio >= 0.98
            and (p.non_null_count or 0) > 20
        )
    )
    if not expected or not p.non_null_count or p.distinct_count is None:
        return Dimension("Unicité", False, None, w, "Non applicable (unicité non attendue).")
    score = min(1.0, p.distinct_count / p.non_null_count)
    duplicates = max(0, p.non_null_count - p.distinct_count)
    reason = "clé primaire" if is_pk else ("identifiant" if p.pii_type else "quasi-unique")
    return Dimension(
        "Unicité", True, score, w,
        f"Unicité {_pct(score)} ({duplicates} doublon(s) sur {p.non_null_count}, {reason}).",
    )


def _consistency(p: ColumnProfile, w: float, integrity: dict | None) -> Dimension:
    if integrity is None:
        return Dimension("Cohérence", False, None, w, "Non applicable (colonne hors relation).")
    score = integrity["ratio"]
    return Dimension(
        "Cohérence", True, score, w,
        f"Cohérence {_pct(score)} ({integrity['orphans']} valeur(s) orpheline(s) sur "
        f"{integrity['total']} vers {integrity['to_table']}).",
    )


def _freshness(p: ColumnProfile, w: float) -> Dimension:
    is_date = (p.detected_type or "").startswith("datetime") or any(
        k in (p.declared_type or "").lower() for k in ("date", "timestamp", "time")
    )
    if not is_date or not p.max_value:
        return Dimension("Fraîcheur", False, None, w, "Non applicable (pas une colonne temporelle).")
    latest = _parse_date(p.max_value)
    if latest is None:
        return Dimension("Fraîcheur", False, None, w, "Non applicable (date max illisible).")
    age = (datetime.now(timezone.utc).date() - latest.date()).days
    if age <= FRESHNESS_GRACE_DAYS:
        score = 1.0
    elif age >= FRESHNESS_ZERO_DAYS:
        score = 0.0
    else:
        score = 1 - (age - FRESHNESS_GRACE_DAYS) / (FRESHNESS_ZERO_DAYS - FRESHNESS_GRACE_DAYS)
    return Dimension(
        "Fraîcheur", True, score, w,
        f"Fraîcheur {_pct(score)} (dernière valeur {latest.date().isoformat()}, il y a {age} jours).",
    )


def _parse_date(value: str) -> datetime | None:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(value[: len(fmt) + 2].strip(), fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(value.replace(" ", "T")).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def column_quality(
    p: ColumnProfile, weights: dict, is_pk: bool, integrity: dict | None
) -> EntityQuality:
    dims = [
        _completeness(p, weights["completeness"]),
        _validity(p, weights["validity"]),
        _uniqueness(p, weights["uniqueness"], is_pk),
        _consistency(p, weights["consistency"], integrity),
        _freshness(p, weights["freshness"]),
    ]
    score = _weighted(dims)
    applicable = [d.name for d in dims if d.applicable]
    return EntityQuality(
        level="column", score=score, dimensions=dims,
        detail=f"Score {_pct(score)} — dimensions évaluées : {', '.join(applicable)}.",
        schema_name=p.schema_name, table_name=p.table_name, column_name=p.column_name,
    )


# --------------------------------------------------------------------------
# Orchestration : calcule et persiste tous les scores d'une connexion
# --------------------------------------------------------------------------
def run_quality(db: Session, conn: Connection, adapter: SourceAdapter, timeout_seconds: int = 60) -> dict:
    weights = _tenant_weights(db, conn.tenant_id)
    snapshot = db.execute(
        select(SchemaSnapshot).where(
            SchemaSnapshot.connection_id == conn.id, SchemaSnapshot.is_current.is_(True)
        )
    ).scalar_one_or_none()
    if snapshot is None:
        raise ValueError("Aucun schéma courant — lancez un scan avant le calcul qualité.")

    # is_pk par (table, colonne)
    pk_map: dict[tuple[str, str], bool] = {}
    tables = db.execute(select(DbTable).where(DbTable.snapshot_id == snapshot.id)).scalars().all()
    for t in tables:
        cols = db.execute(select(DbColumn).where(DbColumn.table_id == t.id)).scalars().all()
        for c in cols:
            pk_map[(t.table_name, c.name)] = c.is_primary_key

    # Intégrité par relation → dimension Cohérence + score relation
    relations = db.execute(
        select(DbRelation).where(DbRelation.snapshot_id == snapshot.id)
    ).scalars().all()
    integrity_map: dict[tuple[str, str], dict] = {}
    relation_entities: list[tuple[DbRelation, EntityQuality]] = []
    timeout_ms = timeout_seconds * 1000
    for rel in relations:
        info = adapter.compute_integrity(rel, timeout_ms)
        if info is None:
            continue
        rel.integrity_ratio = info["ratio"]
        rel.cardinality = info["cardinality"]
        key = (rel.from_table, rel.from_column)
        # En cas de FK multiples on garde la pire intégrité (la plus prudente).
        if key not in integrity_map or info["ratio"] < integrity_map[key]["ratio"]:
            integrity_map[key] = info
        ref = f"{rel.from_schema}.{rel.from_table}.{rel.from_column} → {rel.to_schema}.{rel.to_table}.{rel.to_column}"
        relation_entities.append((rel, EntityQuality(
            level="relation", score=info["ratio"],
            dimensions=[Dimension("Intégrité référentielle", True, info["ratio"], 1.0,
                                  f"{info['orphans']} orphelin(s) sur {info['total']}.")],
            detail=f"Intégrité {_pct(info['ratio'])} ({info['orphans']} orphelin(s) sur {info['total']}).",
            relation_ref=ref,
        )))

    usage = _column_usage(db, conn.id)
    profiles = db.execute(
        select(ColumnProfile).where(ColumnProfile.connection_id == conn.id)
    ).scalars().all()
    profiles_by_table: dict[str, list[ColumnProfile]] = {}
    for p in profiles:
        profiles_by_table.setdefault(p.table_name, []).append(p)

    # Purge des anciens scores de la connexion (recalcul complet)
    db.query(QualityScore).filter(QualityScore.connection_id == conn.id).delete()

    entities: list[EntityQuality] = []
    table_scores: list[float] = []

    for table_name, cols in profiles_by_table.items():
        col_entities: list[EntityQuality] = []
        for p in cols:
            is_pk = pk_map.get((p.table_name, p.column_name), False)
            integrity = integrity_map.get((p.table_name, p.column_name))
            cq = column_quality(p, weights, is_pk, integrity)
            col_entities.append(cq)
            entities.append(cq)

        # Score table : moyenne des colonnes pondérée par leur usage.
        num = 0.0
        den = 0.0
        for cq in col_entities:
            uw = 1.0 + usage.get((table_name, cq.column_name), 0)
            num += uw * cq.score
            den += uw
        tscore = num / den if den else 1.0
        table_scores.append(tscore)
        schema_name = cols[0].schema_name
        entities.append(EntityQuality(
            level="table", score=tscore, dimensions=[],
            detail=f"Score table {_pct(tscore)} — moyenne de {len(col_entities)} colonne(s), "
                   f"pondérée par l'usage.",
            schema_name=schema_name, table_name=table_name,
        ))

    for rel, rq in relation_entities:
        entities.append(rq)

    base_score = sum(table_scores) / len(table_scores) if table_scores else 1.0
    entities.append(EntityQuality(
        level="base", score=base_score, dimensions=[],
        detail=f"Score base {_pct(base_score)} — moyenne de {len(table_scores)} table(s) profilée(s).",
    ))

    # Persistance
    for e in entities:
        db.add(QualityScore(
            connection_id=conn.id, level=e.level,
            schema_name=e.schema_name, table_name=e.table_name,
            column_name=e.column_name, relation_ref=e.relation_ref,
            score=e.score, detail=e.detail,
            dimensions=[d.as_dict() for d in e.dimensions],
        ))
    conn_updated = datetime.now(timezone.utc)
    db.flush()

    return {
        "base_score": base_score,
        "tables_scored": len(table_scores),
        "columns_scored": sum(1 for e in entities if e.level == "column"),
        "relations_scored": len(relation_entities),
        "computed_at": conn_updated.isoformat(),
    }


def _tenant_weights(db: Session, tenant_id: int) -> dict:
    from app.models.tenant import TenantSettings

    ts = db.get(TenantSettings, tenant_id)
    weights = dict(DEFAULT_WEIGHTS)
    if ts and ts.quality_weights:
        weights.update({k: float(v) for k, v in ts.quality_weights.items() if k in DEFAULT_WEIGHTS})
    return weights


def _column_usage(db: Session, connection_id: int) -> dict[tuple[str, str], int]:
    """Compte l'usage réel des colonnes dans le journal des requêtes."""
    logs = db.execute(
        select(QueryLog.tables_used, QueryLog.columns_used).where(
            QueryLog.connection_id == connection_id
        )
    ).all()
    usage: dict[tuple[str, str], int] = {}
    for tables_used, columns_used in logs:
        tnames = [t.split(".")[-1] for t in (tables_used or [])]
        for col in columns_used or []:
            cname = col.split(".")[-1]
            for tn in tnames:
                usage[(tn, cname)] = usage.get((tn, cname), 0) + 1
    return usage


def table_scores_map(db: Session, connection_id: int) -> dict[str, float]:
    rows = db.execute(
        select(QualityScore.table_name, QualityScore.score).where(
            QualityScore.connection_id == connection_id, QualityScore.level == "table"
        )
    ).all()
    return {tn: sc for tn, sc in rows if tn}
