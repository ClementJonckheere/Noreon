"""Moteur de raisonnement (agent d'investigation).

Pour une question ouverte (« pourquoi les ventes baissent ? »), un simple
NL→SQL ne suffit pas. L'agent :

    Question → Planification → Sous-questions → Exécution → Synthèse

1. **Planifie** : à partir du sujet (table de faits + mesure) et de ses
   dimensions, il déclare ce qu'il va examiner (tendance, magasins, produits,
   clients, saisonnalité…), avec une justification par étape.
2. **Exécute** chaque sous-question par une agrégation en lecture seule
   (mêmes garde-fous), et en extrait un enseignement chiffré.
3. **Synthétise** : classe les facteurs, conclut, recommande.

Hors-ligne et auditable : chaque étape porte SON SQL et SON constat. Respecte la
gouvernance d'espace (tables/colonnes masquées écartées du raisonnement).
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.services.deep_analysis import (
    _candidate_dimensions,
    _date_bucket,
    _fmt,
    _load_schema,
    _num,
    _pick_fact_table,
    _pick_measure,
    _q,
    _run_segmentation,
)

log = get_logger("noreon.agent")

# Intentions « analytiques » qui déclenchent une investigation plutôt qu'un
# simple SQL.
_INVESTIGATE_RE = re.compile(
    r"\b(pourquoi|why|explique|expliqu|analyse|analyser|comprendre|comprends|"
    r"cause|causes|raison|raisons|driver|facteur|facteurs|diagnos|"
    r"baisse|baisser|hausse|chute|chuter|recul|recule|progress|"
    r"evolue|evolu|évolu|tendance|tendances|se passe|qu'?est[- ]ce qui)\b",
    re.IGNORECASE,
)

_MAX_DIM_STEPS = 5

# Vocabulaire métier → racine de table : oriente le SUJET selon la question
# (« ventes » vise les commandes, pas les lignes de commande).
_TABLE_SYNONYMS = {
    "orders": {"vente", "ventes", "sale", "sales", "commande", "commandes",
               "order", "orders", "ca", "chiffre", "revenu", "revenue", "panier"},
    "customers": {"client", "clients", "customer", "customers", "acheteur", "acheteurs"},
    "products": {"produit", "produits", "product", "products", "article", "articles", "gamme"},
    "stores": {"magasin", "magasins", "store", "stores", "boutique", "boutiques"},
    "payments": {"paiement", "paiements", "payment", "payments"},
}


def should_investigate(question: str) -> bool:
    return bool(_INVESTIGATE_RE.search(question))


def _pick_subject(schema, question: str, allowed: list[str]):
    """Table de faits guidée par la question, à défaut par la topologie."""
    tokens = set(re.findall(r"[a-zà-ÿ0-9_]+", question.lower()))
    best, best_score = None, 0
    for name in allowed:
        t = schema.tables.get(name)
        if t is None:
            continue
        syns = _TABLE_SYNONYMS.get(t.name.lower(), set()) | {t.name.lower(), t.name.lower().rstrip("s")}
        score = len(tokens & syns)
        if score > best_score:
            best, best_score = t, score
    if best is not None:
        return best
    return _pick_fact_table(schema, allowed)


@dataclass
class Step:
    title: str
    question: str
    rationale: str
    sql: str
    finding: str
    figures: list = field(default_factory=list)


@dataclass
class Investigation:
    question: str
    subject: str
    metric_label: str
    plan: list[dict] = field(default_factory=list)          # {title, rationale}
    steps: list[dict] = field(default_factory=list)
    key_drivers: list[str] = field(default_factory=list)
    conclusion: str = ""
    recommendations: list[str] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)
    # Données de tendance (pour un graphique dans la réponse).
    trend_columns: list[str] = field(default_factory=list)
    trend_rows: list[list] = field(default_factory=list)
    # Journal de raisonnement (pour les experts) : chaque étape horodatée, avec
    # les analyses ESSAYÉES, REJETÉES et RETENUES.
    journal: list[dict] = field(default_factory=list)       # {t, phase, detail, status}
    # « Le moteur change d'avis » : hypothèse initiale vs. ce que disent les données.
    revisions: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


def _now() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _initial_hypothesis(dims: list) -> object | None:
    """Ce qu'un analyste supposerait a priori — souvent la fidélité, sinon le
    premier axe candidat. Sert de point de comparaison pour l'auto-révision."""
    for d in dims:
        if re.search(r"loyal|fidel|fidél", d.label, re.IGNORECASE):
            return d
    return dims[0] if dims else None


def _dim_rationale(label: str) -> str:
    l = label.lower()
    if "age" in l:
        return "L'âge de la clientèle change souvent le comportement d'achat."
    if "city" in l or "ville" in l or "region" in l:
        return "Une zone géographique peut porter seule la variation."
    if "store" in l or "magasin" in l:
        return "Un magasin en difficulté peut expliquer l'ensemble."
    if "categor" in l or "product" in l or "produit" in l:
        return "Une gamme de produits peut tirer le résultat."
    if "loyalty" in l or "fidel" in l:
        return "La fidélité distingue les clients à forte valeur."
    if "method" in l or "paiement" in l or "payment" in l:
        return "Le canal / moyen de paiement révèle des usages différents."
    if "mois" in l or "date" in l or "month" in l:
        return "La saisonnalité et les à-coups temporels comptent."
    return "Cet axe peut structurer la variation observée."


def run_investigation(
    db: Session, conn, adapter, question: str, *,
    guard_args: dict,
    hidden_tables: set[str] | None = None,
    hidden_columns: set[tuple[str, str]] | None = None,
) -> Investigation | None:
    schema = _load_schema(db, conn.id)
    if schema is None:
        return None

    hidden_tables = {t.lower() for t in (hidden_tables or set())}
    hidden_columns = {(t.lower(), c.lower()) for t, c in (hidden_columns or set())}

    names = [n for n in schema.tables if n.lower() not in hidden_tables]
    fact = _pick_subject(schema, question, names)
    if fact is None or fact.name.lower() in hidden_tables:
        return None

    measure = _pick_measure(adapter, fact, question)
    measure_sql = measure.sql
    metric = measure.label
    noun = measure.noun

    dims = _candidate_dimensions(adapter, schema, fact, measure.column)

    def dim_allowed(d) -> bool:
        base = d.bands["column"] if d.bands else None
        if base and (fact.name.lower(), base.lower()) in hidden_columns:
            return False
        # Dimension d'une table liée : « label (table) » → écarter si masquée.
        if d.join_sql and "(" in d.label:
            tbl = d.label.split("(")[-1].rstrip(")").strip().lower()
            if tbl in hidden_tables:
                return False
        return True

    dims = [d for d in dims if dim_allowed(d)]

    inv = Investigation(question=question, subject=fact.name, metric_label=metric)
    queries: list[str] = []

    # Journal de raisonnement — trace vivante pour les experts.
    inv.journal.append({"t": _now(), "phase": "question", "status": "info",
                        "detail": f"Question reçue : « {question} ». Sujet retenu : {fact.name} "
                                  f"(mesure : {metric})."})
    # Hypothèse initiale (avant de regarder les données) — servira à l'auto-révision.
    initial = _initial_hypothesis(dims)
    if initial is not None:
        inv.journal.append({"t": _now(), "phase": "plan", "status": "info",
                            "detail": f"Hypothèse de départ : « {initial.label} » porte probablement la variation."})

    # --- Étape tendance (si une date existe sur la table de faits) ---
    date_col = next((c for c in fact.columns if c.is_temporal
                     and (fact.name.lower(), c.name.lower()) not in hidden_columns), None)
    trend_dir = None
    if date_col is not None:
        col_sql = f"f.{_q(adapter, date_col.name)}"
        expr = _date_bucket(adapter, "month", col_sql)
        metric_expr = f"sum({measure_sql})" if measure_sql else "count(*)"
        sql = (
            f"SELECT {expr} AS periode, {metric_expr} AS valeur "
            f"FROM {adapter.qualified(fact.schema, fact.name)} f "
            f"WHERE {col_sql} IS NOT NULL GROUP BY {expr} ORDER BY {expr}"
        )
        try:
            res = adapter.run_query(sql, connection_id=conn.id, **guard_args)
            rows = [[r[0], _num(r[1])] for r in res.rows]
        except Exception as exc:  # noqa: BLE001
            log.info("Étape tendance ignorée : %s", exc)
            rows = []
        if len(rows) >= 2:
            queries.append(res.guarded_sql)
            inv.trend_columns = ["periode", "valeur"]
            inv.trend_rows = rows
            first, last = rows[0][1], rows[-1][1]
            lo = min(rows, key=lambda r: r[1])
            pct = ((last - first) / first * 100) if first else 0
            trend_dir = "baisse" if pct < -2 else "hausse" if pct > 2 else "stable"
            inv.plan.append({"title": "Tendance dans le temps",
                             "rationale": "Situer l'ampleur et le sens de la variation avant d'en chercher la cause."})
            inv.steps.append(asdict(Step(
                title="Tendance dans le temps",
                question=f"Comment évolue {metric} ?",
                rationale="On mesure d'abord l'ampleur et le point bas.",
                sql=res.guarded_sql,
                finding=(f"{metric} passe de {_fmt(first)} ({rows[0][0]}) à {_fmt(last)} "
                         f"({rows[-1][0]}), soit {pct:+.0f}% — point bas en {lo[0]} "
                         f"({_fmt(lo[1])})."),
                figures=[{"label": "début", "value": round(first)},
                         {"label": "fin", "value": round(last)},
                         {"label": "variation_%", "value": round(pct, 1)}],
            )))

    if date_col is not None and inv.trend_rows:
        inv.journal.append({"t": _now(), "phase": "analysis", "status": "accepted",
                            "detail": f"Tendance temporelle établie ({trend_dir})."})

    # --- Étapes par dimension : plan puis exécution ---
    segmentations = []
    for dim in dims[:_MAX_DIM_STEPS]:
        seg = _run_segmentation(adapter, conn.id, guard_args, fact, dim, measure_sql)
        if seg is not None:
            segmentations.append(seg)
            inv.journal.append({"t": _now(), "phase": "analysis", "status": "info",
                                "detail": f"Analyse « {dim.label} » : signal mesuré (force {seg.power:.2f})."})
        else:
            inv.journal.append({"t": _now(), "phase": "analysis", "status": "rejected",
                                "detail": f"Analyse « {dim.label} » écartée : aucun signal exploitable."})
    segmentations.sort(key=lambda s: s.power, reverse=True)

    # Ce que disent réellement les données : le facteur dominant.
    if segmentations:
        winner = segmentations[0].dim
        inv.journal.append({"t": _now(), "phase": "analysis", "status": "accepted",
                            "detail": f"Facteur dominant retenu : « {winner.label} »."})
        # Auto-révision : le moteur change d'avis si les données contredisent
        # l'hypothèse de départ. « Je pensais fidélité, finalement promotions. »
        if initial is not None and initial.label != winner.label:
            revision = (f"Je pensais que « {initial.label} » portait la variation ; "
                        f"finalement ce sont les écarts de « {winner.label} » qui structurent le plus {noun}.")
            inv.revisions.append(revision)
            inv.journal.append({"t": _now(), "phase": "revision", "status": "info",
                                "detail": revision})

    for seg in segmentations:
        top = seg.groups[0]
        total = sum((g.total if seg.metric_is_measure else g.n) or 0 for g in seg.groups)
        share = (((top.total if seg.metric_is_measure else top.n) or 0) / total * 100) if total else 0
        inv.plan.append({"title": seg.dim.label, "rationale": _dim_rationale(seg.dim.label)})
        # Constat : gradient (mesure moyenne) ou concentration.
        gradient = None
        if seg.metric_is_measure:
            valued = [g for g in seg.groups if g.avg is not None]
            if len(valued) >= 3:
                hi = max(valued, key=lambda g: g.avg)
                loo = min(valued, key=lambda g: g.avg)
                if loo.avg and hi.avg / loo.avg >= 1.2:
                    gradient = (loo, hi, hi.avg / loo.avg)
        if gradient is not None:
            loo, hi, ratio = gradient
            finding = (f"« {seg.dim.label} » pèse fort : de {_fmt(loo.avg)} ({loo.label}) à "
                       f"{_fmt(hi.avg)} ({hi.label}), soit ×{ratio:.1f}.")
        else:
            finding = (f"Le segment « {top.label} » concentre {share:.0f}% {noun}.")
        inv.steps.append(asdict(Step(
            title=seg.dim.label,
            question=f"Comment se répartit {metric} par « {seg.dim.label} » ?",
            rationale=_dim_rationale(seg.dim.label),
            sql=seg.sql,
            finding=finding,
            figures=[{"label": g.label, "value": round((g.total if seg.metric_is_measure else g.n) or 0)}
                     for g in seg.groups[:4]],
        )))
        queries.append(seg.sql)

    if not inv.steps:
        return None

    # --- Synthèse ---
    for seg in segmentations[:3]:
        top = seg.groups[0]
        total = sum((g.total if seg.metric_is_measure else g.n) or 0 for g in seg.groups)
        share = (((top.total if seg.metric_is_measure else top.n) or 0) / total * 100) if total else 0
        inv.key_drivers.append(f"{seg.dim.label} — « {top.label} » ({share:.0f}%)")

    parts = []
    if trend_dir == "baisse":
        parts.append(f"{metric} est orienté à la baisse")
    elif trend_dir == "hausse":
        parts.append(f"{metric} est orienté à la hausse")
    elif trend_dir == "stable":
        parts.append(f"{metric} est globalement stable")
    if segmentations:
        d0 = segmentations[0]
        parts.append(
            f"la variation est surtout structurée par « {d0.dim.label} » "
            f"(segment dominant « {d0.groups[0].label} »)"
        )
    inv.conclusion = ("Conclusion : " + " ; ".join(parts) + ".") if parts else \
        "Conclusion : facteurs répartis, pas de cause unique dominante."

    if segmentations:
        d0 = segmentations[0]
        inv.recommendations.append(
            f"Concentrer l'action sur « {d0.groups[0].label} » ({d0.dim.label}) et suivre son évolution."
        )
    if trend_dir == "baisse" and inv.trend_rows:
        lo = min(inv.trend_rows, key=lambda r: r[1])
        inv.recommendations.append(
            f"Investiguer la période « {lo[0]} » (point bas) : événement métier, promotion, ou données incomplètes ?"
        )
    inv.recommendations.append(
        "Valider ces pistes avec le métier avant décision (l'agent identifie des corrélations, pas des causes certaines)."
    )

    inv.journal.append({"t": _now(), "phase": "synthesis", "status": "accepted",
                        "detail": "Synthèse : facteurs classés, conclusion et recommandations produites."})

    inv.queries = queries
    return inv


def summary_message(inv: Investigation) -> str:
    lead = f"J'ai mené une investigation en {len(inv.steps)} étape(s) sur « {inv.subject} »."
    return f"{lead} {inv.conclusion}"
