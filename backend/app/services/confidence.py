"""Indice de confiance (Module 10) — modèle à composantes pondérées.

L'indice n'est plus un score opaque : c'est une **somme pondérée de composantes**,
ce qui permet d'en montrer la **décomposition** (« confidence breakdown ») et de
comprendre immédiatement ce qui le pénalise :

    confiance = 0.35·qualité + 0.25·concepts + 0.18·relations
              + 0.12·SQL   + 0.06·couverture + 0.04·hypothèses

Chaque composante est un sous-score dans [0,1] adossé à un signal réel (score
qualité auditable, statut des concepts, validation des relations…). L'indice est
TOUJOURS accompagné de ses facteurs ET de sa décomposition.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.profile import ColumnProfile

# Poids des composantes (somme = 1.0).
_WEIGHTS = {
    "qualité": 0.35,
    "concepts": 0.25,
    "relations": 0.18,
    "SQL": 0.12,
    "couverture": 0.06,
    "hypothèses": 0.04,
}


@dataclass
class Confidence:
    score: float  # 0..1
    factors: list[str] = field(default_factory=list)
    breakdown: list[dict] = field(default_factory=list)  # [{factor, weight_pct, subscore_pct, contribution_pct}]

    def as_dict(self) -> dict:
        return {
            "score": round(self.score, 2),
            "percent": round(self.score * 100),
            "factors": self.factors,
            "breakdown": self.breakdown,
        }


def compute(
    db: Session,
    *,
    connection_id: int,
    tables_used: list[str],
    assumptions: list[str],
    sampled: bool,
    truncated: bool,
    row_count: int,
) -> Confidence:
    table_names = [t.split(".")[-1] for t in tables_used]
    factors: list[str] = []

    # --- Composante QUALITÉ : score qualité auditable des tables (Module 4) ---
    q_sub = 0.7  # neutre si inconnu
    if table_names:
        from app.services.quality import table_scores_map  # import local (évite cycle)

        tscores = table_scores_map(db, connection_id)
        used = [tscores[t] for t in table_names if t in tscores]
        if used:
            q_sub = sum(used) / len(used)
            if q_sub < 0.95:
                factors.append(f"score qualité moyen des tables utilisées : {q_sub*100:.0f}%")
        else:
            factors.append("tables utilisées non évaluées (qualité inconnue)")

    # --- Composante CONCEPTS (Module 5) ---
    from app.models.semantic import ConceptMapping  # import local (évite cycle)

    c_sub = 0.5
    if table_names:
        statuses = set(db.execute(
            select(ConceptMapping.status).where(
                ConceptMapping.connection_id == connection_id,
                ConceptMapping.table_name.in_(table_names),
            )
        ).scalars().all())
        if not statuses:
            c_sub = 0.5
            factors.append("aucun concept métier défini sur les tables utilisées")
        elif statuses & {"validated", "corrected"}:
            c_sub = 1.0 if "proposed" not in statuses else 0.8
            if c_sub < 1.0:
                factors.append("certains concepts mobilisés restent proposés (non validés)")
        else:
            c_sub = 0.6
            factors.append("les concepts des tables utilisées ne sont pas encore validés")

    # --- Composante RELATIONS (Module 6) : validation des jointures mobilisées ---
    r_sub = _relation_subscore(db, connection_id, table_names, factors)

    # --- Composante SQL : la requête a passé les garde-fous et s'est exécutée ---
    sql_sub = 1.0

    # --- Composante COUVERTURE ---
    cov_sub = 1.0
    if row_count == 0:
        cov_sub = 0.0
        factors.append("aucune ligne retournée")
    else:
        if sampled:
            cov_sub -= 0.4
            factors.append("analyse fondée sur un échantillon, pas sur l'intégralité")
        if truncated:
            cov_sub -= 0.4
            factors.append("résultats tronqués par le LIMIT automatique")
    cov_sub = max(0.0, cov_sub)

    # --- Composante HYPOTHÈSES ---
    hyp_sub = max(0.0, 1.0 - 0.34 * len(assumptions))
    if assumptions:
        factors.append(f"{len(assumptions)} hypothèse(s) retenue(s) faute de définition explicite")

    subs = {
        "qualité": q_sub, "concepts": c_sub, "relations": r_sub,
        "SQL": sql_sub, "couverture": cov_sub, "hypothèses": hyp_sub,
    }
    score = sum(_WEIGHTS[k] * subs[k] for k in _WEIGHTS)
    score = max(0.0, min(1.0, score))

    breakdown = sorted(
        [
            {
                "factor": k,
                "weight_pct": round(_WEIGHTS[k] * 100),
                "subscore_pct": round(subs[k] * 100),
                "contribution_pct": round(_WEIGHTS[k] * subs[k] * 100, 1),
            }
            for k in _WEIGHTS
        ],
        key=lambda d: d["contribution_pct"],
        reverse=True,
    )

    if not factors:
        factors.append("tous les signaux de confiance sont au vert")

    return Confidence(score=score, factors=factors, breakdown=breakdown)


def _relation_subscore(
    db: Session, connection_id: int, table_names: list[str], factors: list[str]
) -> float:
    """Sous-score des relations mobilisées : 1.0 si mono-table ou jointures
    fiables (FK déclarée / validée), 0.6 si inférées non validées."""
    if len(table_names) < 2:
        return 1.0  # pas de jointure → pas de risque relationnel
    from app.models.schema_catalog import DbRelation, SchemaSnapshot

    snapshot = db.execute(
        select(SchemaSnapshot).where(
            SchemaSnapshot.connection_id == connection_id, SchemaSnapshot.is_current.is_(True)
        )
    ).scalar_one_or_none()
    if snapshot is None:
        return 0.8
    lowered = {t.lower() for t in table_names}
    rels = db.execute(
        select(DbRelation).where(DbRelation.snapshot_id == snapshot.id)
    ).scalars().all()
    involved = [r for r in rels
                if r.from_table.lower() in lowered and r.to_table.lower() in lowered]
    if not involved:
        return 0.9
    if all(r.status == "validated" or r.kind == "declared" for r in involved):
        return 1.0
    factors.append("des relations inférées non validées relient les tables utilisées")
    return 0.6
