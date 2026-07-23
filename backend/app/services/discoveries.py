"""Suggestions automatiques (« Découvertes ») — l'analyste proactif.

À l'ouverture, plutôt que « posez votre question », Noreon met en avant ce qu'un
analyste humain aurait remarqué :

    N anomalies · N tendances · N colonnes suspectes · N relations incohérentes

Tout est calculé HORS-LIGNE à partir de signaux déjà produits :
- **anomalies / tendances** : évolution de la mesure clé dans le temps
  (chute/à-coup > seuil, valeur atypique) ;
- **colonnes suspectes** : profils (valeurs invalides, taux de NULL élevé) ;
- **relations incohérentes** : intégrité référentielle < 100 % (orphelins).
"""
from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass, field
from statistics import mean, pstdev

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.profile import ColumnProfile
from app.models.schema_catalog import DbRelation, SchemaSnapshot
from app.services.deep_analysis import (
    _date_bucket,
    _fmt,
    _load_schema,
    _num,
    _pick_fact_table,
    _pick_measure,
    _q,
)

log = get_logger("noreon.discoveries")


@dataclass
class Finding:
    category: str      # anomaly | trend | opportunity | suspicious_column | incoherent_relation
    severity: str      # high | medium | low
    # Hiérarchie premium (retour utilisateur) : critical 🔴 | important 🟠 |
    # opportunity 🟢 | info ⚪.
    level: str
    title: str
    detail: str
    narrative: str = ""   # « raconte une histoire » : phrase métier actionnable
    table: str | None = None
    column: str | None = None
    # Question prête à l'emploi pour creuser (déclenche l'agent / le chat).
    suggested_question: str | None = None


@dataclass
class Discoveries:
    scanned: bool = False
    counts: dict = field(default_factory=dict)          # par catégorie
    levels: dict = field(default_factory=dict)          # par niveau de hiérarchie
    headline: list = field(default_factory=list)        # accroche « depuis votre dernière visite »
    items: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


_SEV_RANK = {"high": 0, "medium": 1, "low": 2}
_LEVEL_RANK = {"critical": 0, "important": 1, "opportunity": 2, "info": 3}


def run_discoveries(
    db: Session, conn, adapter, *,
    hidden_tables: set[str] | None = None,
    hidden_columns: set[tuple[str, str]] | None = None,
    max_items: int = 12,
) -> Discoveries:
    hidden_tables = {t.lower() for t in (hidden_tables or set())}
    hidden_columns = {(t.lower(), c.lower()) for t, c in (hidden_columns or set())}

    snapshot = db.execute(
        select(SchemaSnapshot).where(
            SchemaSnapshot.connection_id == conn.id, SchemaSnapshot.is_current.is_(True)
        )
    ).scalar_one_or_none()
    if snapshot is None:
        return Discoveries(scanned=False)

    findings: list[Finding] = []

    # --- Relations incohérentes (orphelins) ---
    relations = db.execute(
        select(DbRelation).where(
            DbRelation.snapshot_id == snapshot.id, DbRelation.status != "rejected"
        )
    ).scalars().all()
    for r in relations:
        if r.from_table.lower() in hidden_tables or r.to_table.lower() in hidden_tables:
            continue
        if r.integrity_ratio is not None and r.integrity_ratio < 0.999:
            pct = (1 - r.integrity_ratio) * 100
            sev = "high" if pct >= 5 else "medium"
            findings.append(Finding(
                category="incoherent_relation", severity=sev,
                level="critical" if pct >= 5 else "important",
                title=f"Relation incohérente : {r.from_table}.{r.from_column} → {r.to_table}",
                detail=f"{pct:.1f}% de valeurs orphelines (sans correspondance dans {r.to_table}).",
                narrative=(f"{pct:.1f}% des « {r.from_table} » pointent vers un « {r.to_table} » "
                           "inexistant : ces lignes risquent d'être ignorées dans les jointures, "
                           "donc de fausser les totaux."),
                table=r.from_table, column=r.from_column,
                suggested_question=f"Combien de {r.from_table} par {r.from_column} ?",
            ))

    # --- Colonnes suspectes (profils) ---
    profiles = db.execute(
        select(ColumnProfile).where(ColumnProfile.connection_id == conn.id)
    ).scalars().all()
    for p in profiles:
        if p.table_name.lower() in hidden_tables:
            continue
        if (p.table_name.lower(), p.column_name.lower()) in hidden_columns:
            continue
        if p.invalid_count and p.invalid_count > 0:
            fmt = f" ({p.format_checked})" if p.format_checked else ""
            findings.append(Finding(
                category="suspicious_column", severity="medium", level="important",
                title=f"Colonne « {p.table_name}.{p.column_name} » : valeurs non conformes",
                detail=f"{p.invalid_count} valeur(s) hors format attendu{fmt}.",
                narrative=(f"La colonne « {p.column_name} » contient {p.invalid_count} valeur(s) "
                           f"hors format{fmt} : fiabilité à surveiller pour toute analyse qui s'appuie dessus."),
                table=p.table_name, column=p.column_name,
            ))
        elif p.null_rate is not None and p.null_rate >= 0.3:
            hi = p.null_rate >= 0.6
            findings.append(Finding(
                category="suspicious_column", severity="high" if hi else "medium",
                level="critical" if hi else "important",
                title=f"Colonne « {p.table_name}.{p.column_name} » : beaucoup de valeurs manquantes",
                detail=f"{p.null_rate * 100:.0f}% de valeurs nulles.",
                narrative=(f"« {p.column_name} » est vide à {p.null_rate * 100:.0f}% : les analyses "
                           "qui la mobilisent porteront sur une population partielle."),
                table=p.table_name, column=p.column_name,
            ))

    # --- Anomalies & tendance sur la mesure clé ---
    _temporal_findings(db, conn, adapter, findings, hidden_tables, hidden_columns)

    # Tri par niveau de hiérarchie (critique d'abord), plafonnement.
    findings.sort(key=lambda f: (_LEVEL_RANK.get(f.level, 3), _SEV_RANK.get(f.severity, 3)))
    findings = findings[:max_items]

    counts = {
        "anomalies": sum(1 for f in findings if f.category == "anomaly"),
        "trends": sum(1 for f in findings if f.category == "trend"),
        "opportunities": sum(1 for f in findings if f.category == "opportunity"),
        "suspicious_columns": sum(1 for f in findings if f.category == "suspicious_column"),
        "incoherent_relations": sum(1 for f in findings if f.category == "incoherent_relation"),
    }
    levels = {lv: sum(1 for f in findings if f.level == lv)
              for lv in ("critical", "important", "opportunity", "info")}
    return Discoveries(
        scanned=True, counts=counts, levels=levels,
        headline=_headline(findings), items=[asdict(f) for f in findings],
    )


def _headline(findings: list[Finding]) -> list[str]:
    """Accroche « ce que j'ai remarqué » — 2 à 3 phrases prioritaires."""
    lines: list[str] = []
    trend = next((f for f in findings if f.category == "trend"), None)
    if trend:
        lines.append(trend.title.replace("Tendance : ", "") + ".")
    opp = next((f for f in findings if f.category == "opportunity"), None)
    if opp:
        lines.append(opp.title.replace("Opportunité : ", "") + ".")
    crit = sum(1 for f in findings if f.level == "critical")
    quality = sum(1 for f in findings
                  if f.category in ("suspicious_column", "incoherent_relation"))
    if quality:
        lines.append(f"Qualité des données : {quality} point(s) à corriger"
                     + (" (dont critiques)" if crit else "") + ".")
    if not lines:
        lines.append(f"{len(findings)} observation(s) sur vos données.")
    return lines[:3]


def _temporal_findings(db, conn, adapter, findings, hidden_tables, hidden_columns) -> None:
    schema = _load_schema(db, conn.id)
    if schema is None:
        return

    def has_date(t) -> bool:
        return any(c.is_temporal and (t.name.lower(), c.name.lower()) not in hidden_columns
                   for c in t.columns)

    # Sujet temporel = table de faits AYANT une colonne date (sinon pas de série).
    names = [n for n, t in schema.tables.items()
             if n.lower() not in hidden_tables and has_date(t)]
    if not names:
        return
    fact = _pick_fact_table(schema, names)
    if fact is None or fact.name.lower() in hidden_tables:
        return
    measure = _pick_measure(adapter, fact, "")
    date_col = next((c for c in fact.columns if c.is_temporal
                     and (fact.name.lower(), c.name.lower()) not in hidden_columns), None)
    if date_col is None:
        return

    col_sql = f"f.{_q(adapter, date_col.name)}"
    expr = _date_bucket(adapter, "month", col_sql)
    metric_expr = f"sum({measure.sql})" if measure.sql else "count(*)"
    label = measure.label
    sql = (
        f"SELECT {expr} AS periode, {metric_expr} AS valeur "
        f"FROM {adapter.qualified(fact.schema, fact.name)} f "
        f"WHERE {col_sql} IS NOT NULL GROUP BY {expr} ORDER BY {expr}"
    )
    try:
        res = adapter.run_query(sql, connection_id=conn.id, row_limit=10_000,
                                timeout_seconds=30, max_cost=1_000_000.0, max_concurrent=1)
        rows = [[str(r[0]), _num(r[1])] for r in res.rows]
    except Exception as exc:  # noqa: BLE001
        log.info("Découvertes temporelles ignorées : %s", exc)
        return
    if len(rows) < 3:
        return

    values = [v for _, v in rows]
    first, last = values[0], values[-1]
    pct = ((last - first) / first * 100) if first else 0
    if pct <= -5:  # baisse → tendance à surveiller
        findings.append(Finding(
            category="trend", severity="high" if pct <= -25 else "medium",
            level="important",
            title=f"Tendance : {label} en baisse de {abs(pct):.0f}%",
            detail=f"De {_fmt(first)} ({rows[0][0]}) à {_fmt(last)} ({rows[-1][0]}).",
            narrative=(f"Sur la période, {label} recule de {abs(pct):.0f}%. "
                       "À surveiller : identifions ce qui porte la baisse."),
            table=fact.name,
            suggested_question=f"Pourquoi {label} baisse ?",
        ))
    elif pct >= 5:  # hausse → opportunité à exploiter
        findings.append(Finding(
            category="opportunity", severity="low", level="opportunity",
            title=f"Opportunité : {label} en hausse de {pct:.0f}%",
            detail=f"De {_fmt(first)} ({rows[0][0]}) à {_fmt(last)} ({rows[-1][0]}).",
            narrative=(f"{label} progresse de {pct:.0f}% : une dynamique à comprendre et à "
                       "amplifier (quels segments la portent ?)."),
            table=fact.name,
            suggested_question=f"Qu'est-ce qui explique la hausse de {label} ?",
        ))

    # Chutes/à-coups mois à mois (> 30 %) → anomalie critique.
    for i in range(1, len(rows)):
        prev, cur = values[i - 1], values[i]
        if prev and (cur - prev) / prev <= -0.3:
            drop = abs((cur - prev) / prev) * 100
            findings.append(Finding(
                category="anomaly", severity="high", level="critical",
                title=f"Anomalie : chute de {drop:.0f}% en {rows[i][0]}",
                detail=f"{label} passe de {_fmt(prev)} à {_fmt(cur)}.",
                narrative=(f"Décrochage brutal en {rows[i][0]} : {label} tombe de {_fmt(prev)} à "
                           f"{_fmt(cur)} (-{drop:.0f}%). À investiguer en priorité "
                           "(événement métier, promotion, ou données incomplètes ?)."),
                table=fact.name,
                suggested_question=f"Pourquoi {label} chute en {rows[i][0]} ?",
            ))

    # Valeurs atypiques (> 2σ de la moyenne) → à surveiller.
    if len(values) >= 6:
        m, sd = mean(values), pstdev(values)
        if sd > 0:
            for (per, v) in rows:
                if abs(v - m) > 2 * sd:
                    findings.append(Finding(
                        category="anomaly", severity="medium", level="important",
                        title=f"Valeur atypique en {per}",
                        detail=f"{label} = {_fmt(v)} (moyenne {_fmt(m)}, > 2σ).",
                        narrative=(f"En {per}, {label} s'écarte nettement de la normale "
                                   f"({_fmt(v)} vs moyenne {_fmt(m)})."),
                        table=fact.name,
                        suggested_question=f"Que s'est-il passé en {per} ?",
                    ))


# ---------------------------------------------------------------------------
# Cache (perf) : les Insights sont rejoués à chaque ouverture du chat. On évite
# de relancer la requête source à chaque fois — cache in-process par
# (connexion, version de schéma), avec TTL et invalidation au re-scan.
# ---------------------------------------------------------------------------
_CACHE: dict[tuple[int, int], tuple[float, dict]] = {}
_CACHE_LOCK = threading.Lock()
_TTL_SECONDS = 300


def cached_discoveries(db: Session, conn, adapter, *, force: bool = False,
                       ttl: int = _TTL_SECONDS) -> dict:
    snapshot = db.execute(
        select(SchemaSnapshot).where(
            SchemaSnapshot.connection_id == conn.id, SchemaSnapshot.is_current.is_(True)
        )
    ).scalar_one_or_none()
    if snapshot is None:
        return Discoveries(scanned=False).as_dict()

    key = (conn.id, snapshot.id)
    now = time.time()
    if not force:
        with _CACHE_LOCK:
            hit = _CACHE.get(key)
        if hit is not None and (now - hit[0]) < ttl:
            out = dict(hit[1])
            out["cached"] = True
            return out

    value = run_discoveries(db, conn, adapter).as_dict()
    value["cached"] = False
    with _CACHE_LOCK:
        _CACHE[key] = (now, value)
        # Purge des versions de schéma périmées pour cette connexion.
        for k in [k for k in _CACHE if k[0] == conn.id and k != key]:
            _CACHE.pop(k, None)
    return value


def invalidate(connection_id: int) -> None:
    """À appeler après un re-scan / re-profilage pour rafraîchir les Insights."""
    with _CACHE_LOCK:
        for k in [k for k in _CACHE if k[0] == connection_id]:
            _CACHE.pop(k, None)
