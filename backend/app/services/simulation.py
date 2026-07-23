"""« What if ? » — la simulation. Noreon quitte l'analyse pour la projection.

    « Et si le panier moyen augmentait de 10 % ? »
       → le CA passerait de X à Y (+10 %), gain concentré sur les magasins urbains.

Tout est calculé HORS-LIGNE et de façon TRANSPARENTE : on mesure la base réelle,
on applique le levier, et on répartit le gain selon la structure actuelle des
données (dimension dominante). Les hypothèses de la projection sont explicites
(volume constant, structure inchangée) — Noreon ne prétend pas prédire, il
projette sous hypothèses affichées.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.services import agent as agent_svc
from app.services.deep_analysis import (
    _candidate_dimensions,
    _fmt,
    _load_schema,
    _num,
    _pick_measure,
    _run_segmentation,
)

log = get_logger("noreon.simulation")

_WHATIF_RE = re.compile(r"\b(et si|what if|si l[ea']|simul|scénario|scenario|imagine|supposons)\b", re.I)
_PCT_RE = re.compile(r"([+-]?\d+(?:[.,]\d+)?)\s*%")
_DOWN_RE = re.compile(r"\b(baiss|diminu|r[ée]dui|chut|recul|perd|moins)\w*", re.I)
_UP_RE = re.compile(r"\b(augment|hausse|progress|croiss|monte|gagne|plus)\w*", re.I)


def detect(question: str) -> bool:
    """Vrai si la question est un scénario « et si … % »."""
    return bool(_WHATIF_RE.search(question) and _PCT_RE.search(question))


@dataclass
class Simulation:
    scenario: str
    lever: str
    delta_pct: float
    metric_label: str
    baseline: dict = field(default_factory=dict)      # {count, total, avg}
    projected: dict = field(default_factory=dict)     # {before, after, delta_pct, delta_abs}
    breakdown: list = field(default_factory=list)     # [{segment, dimension, share, gain}]
    assumptions: list[str] = field(default_factory=list)
    narrative: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def run_simulation(
    db: Session, conn, adapter, question: str, *,
    guard_args: dict,
    hidden_tables: set[str] | None = None,
    hidden_columns: set[tuple[str, str]] | None = None,
) -> Simulation | None:
    m = _PCT_RE.search(question)
    if m is None:
        return None
    pct = float(m.group(1).replace(",", "."))
    if m.group(1).lstrip()[0] not in "+-":
        # Pas de signe explicite : la direction vient des mots.
        if _DOWN_RE.search(question) and not _UP_RE.search(question):
            pct = -pct
    delta = pct / 100.0

    schema = _load_schema(db, conn.id)
    if schema is None:
        return None
    hidden_tables = {t.lower() for t in (hidden_tables or set())}
    names = [n for n in schema.tables if n.lower() not in hidden_tables]
    fact = agent_svc._pick_subject(schema, question, names)
    if fact is None or fact.name.lower() in hidden_tables:
        return None

    measure = _pick_measure(adapter, fact, question)
    if measure.sql is None:
        return None  # pas de mesure monétaire → on ne simule pas un effectif

    sql = (
        f"SELECT count(*) AS n, sum({measure.sql}) AS total, avg({measure.sql}) AS moyenne "
        f"FROM {adapter.qualified(fact.schema, fact.name)} f"
    )
    try:
        res = adapter.run_query(sql, connection_id=conn.id, **guard_args)
    except Exception as exc:  # noqa: BLE001
        log.info("Simulation ignorée (base) : %s", exc)
        return None
    if not res.rows:
        return None
    count, total, avg = _num(res.rows[0][0]), _num(res.rows[0][1]), _num(res.rows[0][2])
    if not total:
        return None

    lever = "panier moyen" if re.search(r"panier|moyen", question, re.I) else (measure.column or "la mesure")
    after = total * (1 + delta)
    delta_abs = after - total

    # Répartition du gain selon la structure actuelle (dimension dominante).
    breakdown: list[dict] = []
    dims = _candidate_dimensions(adapter, schema, fact, measure.column)
    seg = None
    for dim in dims[:5]:
        s = _run_segmentation(adapter, conn.id, guard_args, fact, dim, measure.sql)
        if s is not None and s.metric_is_measure and s.groups:
            seg = s
            break
    if seg is not None:
        tot = sum((g.total or 0) for g in seg.groups) or 1
        for g in seg.groups[:4]:
            share = (g.total or 0) / tot
            breakdown.append({
                "segment": g.label, "dimension": seg.dim.label,
                "share": round(share * 100, 1), "gain": round(delta_abs * share),
            })

    sim = Simulation(
        scenario=f"{lever} {pct:+.0f}%",
        lever=lever, delta_pct=round(pct, 1),
        metric_label=f"CA ({measure.column})" if measure.column else "total",
        baseline={"count": round(count), "total": round(total), "avg": round(avg, 2)},
        projected={"before": round(total), "after": round(after),
                   "delta_pct": round(delta * 100, 1), "delta_abs": round(delta_abs)},
        breakdown=breakdown,
        assumptions=[
            "Projection à volume de commandes constant.",
            "Répartition proportionnelle à la structure actuelle des données.",
            "Simulation hors-ligne — une projection sous hypothèses, pas une prédiction.",
        ],
    )
    lead = (f"Si {lever} évoluait de {pct:+.0f}%, le {sim.metric_label} passerait de "
            f"{_fmt(total)} à {_fmt(after)} ({delta*100:+.1f}%).")
    if breakdown:
        top = breakdown[0]
        lead += (f" Le gain se concentrerait surtout sur « {top['segment']} » "
                 f"({top['dimension']}), qui pèse {top['share']:.0f}% du {sim.metric_label}.")
    sim.narrative = lead
    return sim
