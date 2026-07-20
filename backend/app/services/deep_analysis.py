"""Analyste approfondi — la valeur métier au-delà de la sortie de données.

Un vrai data analyst ne se contente pas de restituer le résultat d'une requête :
il CROISE les dimensions autour du sujet, cherche à comprendre QUI se cache
derrière les chiffres, identifie les FACTEURS explicatifs (drivers) et rédige
une PRÉSENTATION métier structurée.

Ce service reproduit ce comportement **par le calcul, hors-ligne** : à partir du
résultat primaire, il localise la table de faits, choisit une mesure, énumère
les dimensions disponibles (colonnes de la table, tables liées par des
relations, tranches numériques, périodes), puis lance des **requêtes de suivi
en lecture seule** (mêmes garde-fous que le chat) pour :

  1. segmenter la mesure selon chaque dimension pertinente ;
  2. mesurer le pouvoir explicatif de chaque dimension (drivers) ;
  3. croiser les deux dimensions les plus structurantes (ex. âge × ville) ;
  4. repérer les segments atypiques ;
  5. produire des enseignements et recommandations métier.

Les requêtes de suivi sont **agrégées** (GROUP BY) : elles ne renvoient que des
libellés de segments et des compteurs — aucune donnée identifiante brute. Les
colonnes PII et quasi-uniques sont exclues des dimensions par construction.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from statistics import mean, pstdev

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.profile import ColumnProfile
from app.models.schema_catalog import DbColumn, DbRelation, DbTable, SchemaSnapshot

log = get_logger("noreon.deep")

# Budget d'exécution : borne le nombre de requêtes de suivi lancées par analyse.
_MAX_DIMENSION_QUERIES = 8
_MAX_GROUPS = 25          # au-delà, une « dimension » n'est plus une segmentation
_MIN_GROUPS = 2
_TOP_GROUPS_IN_REPORT = 4
_NUMERIC_BANDS = 5


# ---------------------------------------------------------------------------
# Modèle de schéma léger (chargé depuis la base interne)
# ---------------------------------------------------------------------------
@dataclass
class _Col:
    name: str
    data_type: str
    is_pk: bool
    profile: ColumnProfile | None = None

    @property
    def is_numeric(self) -> bool:
        d = self.data_type.lower()
        num = any(k in d for k in ("int", "numeric", "decimal", "real", "double", "float", "money", "dec"))
        return num and "point" not in d

    @property
    def is_temporal(self) -> bool:
        d = self.data_type.lower()
        if any(k in d for k in ("date", "timestamp", "time")):
            return True
        return bool(self.profile and self.profile.detected_type == "date")

    @property
    def is_key_like(self) -> bool:
        n = self.name.lower()
        return self.is_pk or n == "id" or n.endswith("_id") or n.endswith("id")


@dataclass
class _Table:
    schema: str
    name: str
    estimated_rows: int | None
    columns: list[_Col]

    @property
    def fq(self) -> str:
        return f"{self.schema}.{self.name}"

    def col(self, name: str) -> _Col | None:
        return next((c for c in self.columns if c.name == name), None)


@dataclass
class _Rel:
    from_table: str
    from_column: str
    to_schema: str
    to_table: str
    to_column: str


@dataclass
class _Schema:
    tables: dict[str, _Table]          # clé = nom court de table
    relations: list[_Rel]


def _load_schema(db: Session, connection_id: int) -> _Schema | None:
    snapshot = db.execute(
        select(SchemaSnapshot).where(
            SchemaSnapshot.connection_id == connection_id,
            SchemaSnapshot.is_current.is_(True),
        )
    ).scalar_one_or_none()
    if snapshot is None:
        return None

    profiles = db.execute(
        select(ColumnProfile).where(ColumnProfile.connection_id == connection_id)
    ).scalars().all()
    pmap: dict[tuple[str, str], ColumnProfile] = {
        (p.table_name, p.column_name): p for p in profiles
    }

    tables: dict[str, _Table] = {}
    db_tables = db.execute(
        select(DbTable).where(DbTable.snapshot_id == snapshot.id)
    ).scalars().all()
    for t in db_tables:
        cols = db.execute(
            select(DbColumn).where(DbColumn.table_id == t.id).order_by(DbColumn.ordinal)
        ).scalars().all()
        tables[t.table_name] = _Table(
            schema=t.schema_name, name=t.table_name, estimated_rows=t.estimated_rows,
            columns=[
                _Col(name=c.name, data_type=c.data_type, is_pk=c.is_primary_key,
                     profile=pmap.get((t.table_name, c.name)))
                for c in cols
            ],
        )

    relations = [
        _Rel(from_table=r.from_table, from_column=r.from_column,
             to_schema=r.to_schema, to_table=r.to_table, to_column=r.to_column)
        for r in db.execute(
            select(DbRelation).where(
                DbRelation.snapshot_id == snapshot.id,
                DbRelation.status != "rejected",
            )
        ).scalars().all()
    ]
    return _Schema(tables=tables, relations=relations)


# ---------------------------------------------------------------------------
# Dimensions candidates
# ---------------------------------------------------------------------------
@dataclass
class _Dimension:
    label: str            # libellé lisible (« ville », « tranche d'âge », « mois »)
    expr: str             # expression SQL du groupe (déjà qualifiée/quotée)
    kind: str             # categorical | temporal | numeric-band
    join_sql: str = ""    # clause JOIN éventuelle (dimension d'une table liée)
    bands: dict | None = None  # métadonnées de tranche numérique (min, width)


def _q(adapter, ident: str) -> str:
    return adapter.quote_ident(ident)


def _date_bucket(adapter, unit: str, col_sql: str) -> str:
    d = adapter.dialect
    if d == "mysql":
        fmt = {"month": "%Y-%m-01", "year": "%Y-01-01"}.get(unit, "%Y-%m-01")
        return f"DATE_FORMAT({col_sql}, '{fmt}')"
    if d == "sqlite":
        fmt = {"month": "%Y-%m", "year": "%Y"}.get(unit, "%Y-%m")
        return f"strftime('{fmt}', {col_sql})"
    return f"to_char({col_sql}, 'YYYY-MM')" if unit == "month" else f"to_char({col_sql}, 'YYYY')"


def _is_pii(col: _Col) -> bool:
    return bool(col.profile and col.profile.pii_type)


def _is_low_cardinality(col: _Col) -> bool:
    p = col.profile
    if p is None:
        # Sans profil, on se fie au type : un texte court peut être catégoriel.
        return not col.is_numeric
    if p.distinct_count is None:
        return True
    if p.distinct_count < _MIN_GROUPS or p.distinct_count > _MAX_GROUPS:
        return False
    # Une colonne quasi-unique (ratio proche de 1) est un identifiant, pas un axe.
    return not (p.distinct_ratio is not None and p.distinct_ratio > 0.9)


def _numeric_band_expr(adapter, col: _Col, fact_alias: str) -> _Dimension | None:
    """Découpe une colonne numérique métier en tranches (ex. âge → 18-27, …)."""
    p = col.profile
    if p is None or p.min_value is None or p.max_value is None:
        return None
    try:
        lo, hi = float(p.min_value), float(p.max_value)
    except (TypeError, ValueError):
        return None
    if hi <= lo:
        return None
    width = max(1, round((hi - lo) / _NUMERIC_BANDS))
    lo_i = int(lo)
    col_sql = f"{fact_alias}.{_q(adapter, col.name)}"
    # Indice de tranche : cast en entier (portable PG/MySQL/SQLite).
    expr = f"cast(({col_sql} - {lo_i}) / {width} as integer)"
    return _Dimension(
        label=f"tranche de {col.name}", expr=expr, kind="numeric-band",
        bands={"lo": lo_i, "width": width, "column": col.name},
    )


def _band_label(idx, bands: dict) -> str:
    try:
        i = int(idx)
    except (TypeError, ValueError):
        return str(idx)
    lo = bands["lo"] + i * bands["width"]
    hi = lo + bands["width"] - 1
    return f"{lo}–{hi}"


def _candidate_dimensions(
    adapter, schema: _Schema, fact: _Table, measure_col: str | None = None,
) -> list[_Dimension]:
    dims: list[_Dimension] = []
    fa = "f"  # alias de la table de faits
    seen: set[str] = set()

    def add(dim: _Dimension) -> None:
        if dim.expr not in seen:
            seen.add(dim.expr)
            dims.append(dim)

    for col in fact.columns:
        if _is_pii(col) or col.name == measure_col:
            continue
        col_sql = f"{fa}.{_q(adapter, col.name)}"
        if col.is_temporal:
            add(_Dimension(label=f"{col.name} (par mois)",
                           expr=_date_bucket(adapter, "month", col_sql), kind="temporal"))
        elif col.is_numeric and not col.is_key_like:
            band = _numeric_band_expr(adapter, col, fa)
            if band is not None:
                add(band)
        elif not col.is_key_like and _is_low_cardinality(col):
            add(_Dimension(label=col.name, expr=col_sql, kind="categorical"))

    # Dimensions des tables liées (1 saut) : fact.<fk> -> dim.<pk>.
    joined = 0
    for rel in schema.relations:
        if rel.from_table != fact.name or joined >= 3:
            continue
        dim_table = schema.tables.get(rel.to_table)
        if dim_table is None or dim_table.name == fact.name:
            continue
        da = f"d{joined}"
        join_sql = (
            f" JOIN {adapter.qualified(dim_table.schema, dim_table.name)} {da} "
            f"ON {fa}.{_q(adapter, rel.from_column)} = {da}.{_q(adapter, rel.to_column)}"
        )
        added_here = False
        for col in dim_table.columns:
            if _is_pii(col) or col.is_key_like:
                continue
            if col.is_temporal:
                band = None  # les périodes d'une dimension liée restent secondaires
            elif col.is_numeric:
                # Une variable numérique d'une table liée (ex. âge du client) est
                # découpée en tranches : c'est exactement le croisement démographique
                # attendu (« qui achète » → tranche d'âge).
                band = _numeric_band_expr(adapter, col, da)
                if band is None:
                    continue
                band.label = f"tranche de {col.name} ({dim_table.name})"
                band.join_sql = join_sql
                add(band)
                added_here = True
                continue
            elif not _is_low_cardinality(col):
                continue
            add(_Dimension(
                label=f"{col.name} ({dim_table.name})",
                expr=f"{da}.{_q(adapter, col.name)}", kind="categorical", join_sql=join_sql,
            ))
            added_here = True
        if added_here:
            joined += 1
    return dims


# ---------------------------------------------------------------------------
# Exécution des agrégations de suivi
# ---------------------------------------------------------------------------
@dataclass
class _Group:
    label: str
    n: int
    total: float | None       # somme de la mesure (None si pas de mesure)

    @property
    def avg(self) -> float | None:
        return (self.total / self.n) if (self.total is not None and self.n) else None


@dataclass
class _Segmentation:
    dim: _Dimension
    groups: list[_Group]
    sql: str
    metric_is_measure: bool
    # Statistiques dérivées
    top_share: float = 0.0    # part du 1er segment dans la mesure
    hhi: float = 0.0          # concentration (Herfindahl)
    cv_avg: float = 0.0       # variation de la mesure moyenne entre segments
    power: float = 0.0        # score global de pouvoir explicatif


def _num(v) -> float:
    if v is None:
        return 0.0
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.replace(",", "."))
        except ValueError:
            return 0.0
    return float(v)


def _run_segmentation(
    adapter, conn_id: int, guard_args: dict, fact: _Table,
    dim: _Dimension, measure_sql: str | None,
) -> _Segmentation | None:
    fa = "f"
    metric_select = f", sum({measure_sql}) AS total" if measure_sql else ""
    order_by = "total DESC" if measure_sql else "n DESC"
    sql = (
        f"SELECT {dim.expr} AS grp, count(*) AS n{metric_select} "
        f"FROM {adapter.qualified(fact.schema, fact.name)} {fa}{dim.join_sql} "
        f"WHERE {dim.expr} IS NOT NULL "
        f"GROUP BY {dim.expr} ORDER BY {order_by}"
    )
    try:
        result = adapter.run_query(sql, connection_id=conn_id, **guard_args)
    except Exception as exc:  # noqa: BLE001 - une dimension qui échoue est ignorée
        log.info("Dimension ignorée (%s) : %s", dim.label, exc)
        return None

    rows = result.rows
    if len(rows) < _MIN_GROUPS or len(rows) > _MAX_GROUPS:
        return None

    groups: list[_Group] = []
    has_measure = measure_sql is not None
    for r in rows:
        raw_label = r[0]
        label = _band_label(raw_label, dim.bands) if dim.bands else str(raw_label)
        n = int(_num(r[1]))
        total = _num(r[2]) if has_measure and len(r) > 2 else None
        groups.append(_Group(label=label, n=n, total=total))

    seg = _Segmentation(
        dim=dim, groups=groups, sql=result.guarded_sql, metric_is_measure=has_measure,
    )
    _compute_stats(seg)
    return seg


def _compute_stats(seg: _Segmentation) -> None:
    if seg.metric_is_measure:
        weights = [max(g.total or 0.0, 0.0) for g in seg.groups]
    else:
        weights = [float(g.n) for g in seg.groups]
    total = sum(weights)
    if total <= 0:
        return
    shares = [w / total for w in weights]
    seg.top_share = max(shares)
    seg.hhi = sum(s * s for s in shares)

    if seg.metric_is_measure:
        avgs = [g.avg for g in seg.groups if g.avg is not None]
        if len(avgs) >= 2 and mean(avgs):
            seg.cv_avg = pstdev(avgs) / mean(avgs)

    # Pouvoir explicatif : si une mesure existe, une dimension « structurante »
    # est celle où la mesure MOYENNE varie fortement d'un segment à l'autre
    # (cv_avg) ET/OU où la mesure se concentre (hhi au-dessus de l'équirépartition).
    even = 1.0 / len(seg.groups)
    concentration = max(0.0, seg.hhi - even)
    # Bonus de lisibilité : un axe démographique compact (2 à 8 segments : ville,
    # tranche d'âge, genre…) est plus parlant qu'une série de dizaines de mois.
    # Départage les quasi-égalités en faveur des dimensions actionnables.
    readable = 0.03 if 2 <= len(seg.groups) <= 8 else 0.0
    seg.power = (seg.cv_avg if seg.metric_is_measure else 0.0) + concentration + readable


# ---------------------------------------------------------------------------
# Croisement de deux dimensions
# ---------------------------------------------------------------------------
@dataclass
class _CrossCell:
    a: str
    b: str
    n: int
    total: float | None


@dataclass
class _CrossTab:
    dim_a: _Dimension
    dim_b: _Dimension
    cells: list[_CrossCell]
    sql: str
    metric_is_measure: bool


def _run_crosstab(
    adapter, conn_id: int, guard_args: dict, fact: _Table,
    a: _Dimension, b: _Dimension, measure_sql: str | None,
) -> _CrossTab | None:
    fa = "f"
    metric_select = f", sum({measure_sql}) AS total" if measure_sql else ""
    order_by = "total DESC" if measure_sql else "n DESC"
    join_sql = a.join_sql + (b.join_sql if b.join_sql != a.join_sql else "")
    sql = (
        f"SELECT {a.expr} AS ga, {b.expr} AS gb, count(*) AS n{metric_select} "
        f"FROM {adapter.qualified(fact.schema, fact.name)} {fa}{join_sql} "
        f"WHERE {a.expr} IS NOT NULL AND {b.expr} IS NOT NULL "
        f"GROUP BY {a.expr}, {b.expr} ORDER BY {order_by}"
    )
    try:
        result = adapter.run_query(sql, connection_id=conn_id, **guard_args)
    except Exception as exc:  # noqa: BLE001
        log.info("Croisement ignoré (%s × %s) : %s", a.label, b.label, exc)
        return None
    if len(result.rows) < 2:
        return None
    has_measure = measure_sql is not None
    cells = [
        _CrossCell(
            a=_band_label(r[0], a.bands) if a.bands else str(r[0]),
            b=_band_label(r[1], b.bands) if b.bands else str(r[1]),
            n=int(_num(r[2])),
            total=_num(r[3]) if has_measure and len(r) > 3 else None,
        )
        for r in result.rows[:12]
    ]
    return _CrossTab(dim_a=a, dim_b=b, cells=cells, sql=result.guarded_sql,
                     metric_is_measure=has_measure)


# ---------------------------------------------------------------------------
# Résultat structuré
# ---------------------------------------------------------------------------
@dataclass
class DeepAnalysis:
    subject: str
    metric_label: str
    context: list[str] = field(default_factory=list)
    segments: list[dict] = field(default_factory=list)
    drivers: list[str] = field(default_factory=list)
    crosstab: dict | None = None
    findings: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


def _fmt(v: float) -> str:
    return f"{v:,.0f}".replace(",", " ")


def _pick_fact_table(schema: _Schema, tables_used: list[str]) -> _Table | None:
    names = [t.split(".")[-1] for t in tables_used]
    candidates = [schema.tables[n] for n in names if n in schema.tables]
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    # Table de faits = celle qui référence le plus d'autres tables (FK sortantes),
    # à défaut la plus volumineuse.
    def out_fks(t: _Table) -> int:
        return sum(1 for r in schema.relations if r.from_table == t.name)
    return max(candidates, key=lambda t: (out_fks(t), t.estimated_rows or 0))


# Une colonne n'est une MESURE additive que si son nom l'y prête (montant,
# quantité, points…). Sommer un « âge » ou une « année » n'a aucun sens métier :
# dans ce cas on retombe sur l'EFFECTIF (count), et la variable numérique
# redevient une DIMENSION (tranche) — c'est le profil « qui achète » recherché.
_MEASURE_HINTS = (
    "amount", "montant", "price", "prix", "total", "ca", "revenue", "revenu",
    "chiffre", "net", "cost", "cout", "sales", "vente", "quantity", "qty",
    "quantite", "points", "score", "solde", "balance", "sum",
)


@dataclass
class _Measure:
    sql: str | None       # None → count(*)
    column: str | None    # nom de la colonne mesurée (pour l'exclure des dimensions)
    label: str            # libellé long (contexte)
    noun: str             # groupe nominal court pour les phrases (« du total de X »)


_COUNT_INTENT = re.compile(r"\b(combien|nombre|count|compter|how many|effectif)\b", re.IGNORECASE)


def _pick_measure(adapter, fact: _Table, question: str) -> _Measure:
    numeric = [
        c for c in fact.columns
        if c.is_numeric and not c.is_key_like and not _is_pii(c)
    ]
    # Question de dénombrement (« combien de clients ») : la valeur ajoutée n'est
    # pas de sommer une mesure au hasard, mais de dresser le PROFIL de la
    # population (qui sont-ils : âge, ville, genre…). Métrique = effectif.
    measure = None
    if not _COUNT_INTENT.search(question):
        measure = next(
            (c for c in numeric if any(k in c.name.lower() for k in _MEASURE_HINTS)), None
        )
    if measure is None:
        return _Measure(sql=None, column=None,
                        label=f"effectif de « {fact.name} » (nombre de lignes)",
                        noun="de l'effectif")
    col_sql = f"f.{adapter.quote_ident(measure.name)}"
    return _Measure(sql=col_sql, column=measure.name,
                    label=f"total de {measure.name}", noun=f"du total de {measure.name}")


def run_deep_analysis(
    db: Session,
    conn,
    adapter,
    question: str,
    *,
    tables_used: list[str],
    guard_args: dict,
) -> DeepAnalysis | None:
    """Produit une présentation métier approfondie en croisant les dimensions.

    Renvoie None si le sujet ne se prête pas à une analyse multi-dimensionnelle
    (aucune table de faits identifiable, aucune dimension exploitable).
    """
    schema = _load_schema(db, conn.id)
    if schema is None:
        return None
    fact = _pick_fact_table(schema, tables_used)
    if fact is None:
        return None

    measure = _pick_measure(adapter, fact, question)
    measure_sql = measure.sql
    metric_label = measure.label
    metric_noun = measure.noun
    dims = _candidate_dimensions(adapter, schema, fact, measure.column)
    if not dims:
        return None

    # Segmentation par dimension (budget borné).
    segmentations: list[_Segmentation] = []
    for dim in dims[:_MAX_DIMENSION_QUERIES]:
        seg = _run_segmentation(adapter, conn.id, guard_args, fact, dim, measure_sql)
        if seg is not None:
            segmentations.append(seg)
    if not segmentations:
        return None

    segmentations.sort(key=lambda s: s.power, reverse=True)
    queries = [s.sql for s in segmentations]

    # Volume global (dénombrement de la table de faits).
    volume = sum(g.n for g in segmentations[0].groups)
    report = DeepAnalysis(
        subject=fact.name,
        metric_label=metric_label,
    )
    report.context.append(
        f"Sujet analysé : « {fact.name} » ({_fmt(volume)} enregistrement(s) couverts "
        f"par la segmentation). Mesure retenue : {metric_label}."
    )
    linked = sorted({s.dim.label.split("(")[-1].rstrip(")").strip()
                     for s in segmentations if s.dim.join_sql})
    if linked:
        report.context.append(
            "Dimensions rapprochées via les relations du modèle : "
            + ", ".join(linked) + "."
        )
    report.context.append(
        f"{len(segmentations)} dimension(s) explorée(s) par agrégation en lecture "
        "seule ; seuls des libellés de segments et des compteurs sont calculés "
        "(aucune donnée identifiante)."
    )

    # Segments détaillés (top dimensions).
    for seg in segmentations[:4]:
        total = sum((g.total if seg.metric_is_measure else g.n) or 0 for g in seg.groups)
        entries = []
        for g in seg.groups[:_TOP_GROUPS_IN_REPORT]:
            val = (g.total if seg.metric_is_measure else g.n) or 0
            share = (val / total * 100) if total else 0
            entry = {"segment": g.label, "value": round(val), "share": round(share, 1),
                     "count": g.n}
            if seg.metric_is_measure and g.avg is not None:
                entry["avg"] = round(g.avg, 1)
            entries.append(entry)
        report.segments.append({
            "dimension": seg.dim.label,
            "kind": seg.dim.kind,
            "metric": metric_label,
            "groups": entries,
            "n_groups": len(seg.groups),
        })

    # Drivers : les dimensions les plus structurantes. Deux signaux possibles —
    # (a) un GRADIENT : la mesure moyenne varie nettement d'un segment à l'autre
    # (ex. le panier moyen croît avec l'âge) ; (b) une CONCENTRATION : un segment
    # capte une part disproportionnée du total.
    for seg in segmentations[:3]:
        top = seg.groups[0]
        gradient = None
        if seg.metric_is_measure:
            valued = [g for g in seg.groups if g.avg is not None]
            if len(valued) >= 3:
                hi = max(valued, key=lambda g: g.avg)
                lo = min(valued, key=lambda g: g.avg)
                if lo.avg and hi.avg / lo.avg >= 1.2:
                    gradient = (lo, hi, hi.avg / lo.avg)
        if gradient is not None:
            lo, hi, ratio = gradient
            report.drivers.append(
                f"« {seg.dim.label} » influence fortement {metric_label} : la moyenne "
                f"passe de {_fmt(lo.avg)} ({lo.label}) à {_fmt(hi.avg)} ({hi.label}), "
                f"soit un rapport de {ratio:.1f}× — c'est un vrai facteur explicatif, "
                "pas un simple total."
            )
        else:
            report.drivers.append(
                f"« {seg.dim.label} » structure la répartition : le segment "
                f"« {top.label} » concentre {seg.top_share * 100:.0f}% {metric_noun}."
            )

    # Croisement de deux dimensions pour comprendre QUI se cache derrière les
    # chiffres (ex. âge × ville). On part de la dimension la plus structurante ;
    # pour la seconde, on privilégie un axe « qui » (démographique / catégoriel)
    # plutôt que le temps — la question temporelle est déjà l'axe principal, et
    # croiser un driver avec un mois apprend moins que le croiser avec un profil.
    def _base(dim: _Dimension) -> str:
        return dim.bands["column"] if dim.bands else dim.expr

    distinct_dims: list[tuple[_Dimension, str]] = []
    if segmentations:
        first = segmentations[0].dim
        distinct_dims.append((first, _base(first)))
        pool = segmentations[1:]
        second = next(
            (s for s in pool if _base(s.dim) != _base(first)
             and not (first.kind != "temporal" and s.dim.kind == "temporal")),
            None,
        )
        if second is None:  # à défaut, n'importe quelle autre dimension distincte
            second = next((s for s in pool if _base(s.dim) != _base(first)), None)
        if second is not None:
            distinct_dims.append((second.dim, _base(second.dim)))
    if len(distinct_dims) == 2:
        cross = _run_crosstab(
            adapter, conn.id, guard_args, fact,
            distinct_dims[0][0], distinct_dims[1][0], measure_sql,
        )
        if cross is not None:
            queries.append(cross.sql)
            top = cross.cells[0]
            val = (top.total if cross.metric_is_measure else top.n) or 0
            grand = sum((c.total if cross.metric_is_measure else c.n) or 0 for c in cross.cells)
            share = (val / grand * 100) if grand else 0
            report.crosstab = {
                "dim_a": cross.dim_a.label,
                "dim_b": cross.dim_b.label,
                "metric": metric_label,
                "cells": [
                    {"a": c.a, "b": c.b, "value": round((c.total if cross.metric_is_measure else c.n) or 0),
                     "count": c.n}
                    for c in cross.cells[:6]
                ],
            }
            report.findings.append(
                f"En croisant « {cross.dim_a.label} » et « {cross.dim_b.label} », "
                f"le profil dominant est « {top.a} » / « {top.b} » "
                f"({_fmt(val)}, {share:.0f}% du haut de tableau) : c'est là que se "
                "concentre l'essentiel de la valeur."
            )

    # Segments atypiques (un groupe très au-dessus des autres sur la mesure moyenne).
    for seg in segmentations[:3]:
        if not seg.metric_is_measure:
            continue
        avgs = [g.avg for g in seg.groups if g.avg is not None]
        if len(avgs) >= 4:
            m, sd = mean(avgs), pstdev(avgs)
            if sd > 0:
                for g in seg.groups:
                    if g.avg is not None and (g.avg - m) > 2 * sd:
                        report.findings.append(
                            f"Segment atypique : « {g.label} » ({seg.dim.label}) présente "
                            f"une moyenne de {_fmt(g.avg)} pour {metric_label}, très "
                            f"au-dessus de la moyenne des segments ({_fmt(m)})."
                        )
                        break

    # Recommandations métier, dérivées des enseignements.
    strongest = segmentations[0]
    if strongest.top_share > 0.5:
        report.recommendations.append(
            f"Dépendance marquée à « {strongest.groups[0].label} » "
            f"({strongest.dim.label}) : sécuriser ce segment et surveiller son "
            "évolution en priorité (risque de concentration)."
        )
    if report.crosstab:
        report.recommendations.append(
            f"Cibler les actions sur le profil « {report.crosstab['cells'][0]['a']} / "
            f"{report.crosstab['cells'][0]['b']} » (meilleur rendement observé) et "
            "tester une montée en gamme sur les profils voisins sous-exploités."
        )
    weak_driver = next(
        (s for s in segmentations if s.metric_is_measure and s.cv_avg > 0.3), None
    )
    if weak_driver:
        report.recommendations.append(
            f"« {weak_driver.dim.label} » discrimine nettement la performance : en "
            "faire un axe de pilotage (objectifs et suivi par segment)."
        )
    if not report.recommendations:
        report.recommendations.append(
            "Répartition équilibrée entre segments : pas de dépendance critique "
            "détectée ; poursuivre le suivi périodique de ces dimensions."
        )

    report.queries = queries
    return report
