"""Indice de confiance (Module 10).

« Combinaison explicite de : score qualité des données utilisées ; statut de
validation des concepts métier mobilisés ; complexité/ambiguïté de la
question ; couverture des données. L'indice est toujours accompagné de ses
facteurs. »

En V0.1 le score qualité complet (Module 4) et la validation des concepts
(Module 5) n'existent pas encore : on calcule un indice à partir des signaux
disponibles (taux de NULL des colonnes utilisées, ambiguïté détectée par le
moteur SQL, échantillonnage / troncature) et on l'accompagne TOUJOURS de ses
facteurs, pour rester calibré et non décoratif.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.profile import ColumnProfile


@dataclass
class Confidence:
    score: float  # 0..1
    factors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"score": round(self.score, 2), "percent": round(self.score * 100), "factors": self.factors}


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
    score = 1.0
    factors: list[str] = []

    # 1) Qualité des données : score qualité auditable des tables utilisées
    # (Module 4). À défaut de score qualité, repli sur le taux de NULL.
    table_names = [t.split(".")[-1] for t in tables_used]
    if table_names:
        from app.services.quality import table_scores_map  # import local (évite cycle)

        tscores = table_scores_map(db, connection_id)
        used = [tscores[t] for t in table_names if t in tscores]
        if used:
            avg_q = sum(used) / len(used)
            if avg_q < 0.95:
                penalty = min(0.3, (1 - avg_q))
                score -= penalty
                factors.append(
                    f"score qualité moyen des tables utilisées : {avg_q*100:.0f}%"
                )
        else:
            profiles = db.execute(
                select(ColumnProfile).where(
                    ColumnProfile.connection_id == connection_id,
                    ColumnProfile.table_name.in_(table_names),
                )
            ).scalars().all()
            null_rates = [p.null_rate for p in profiles if p.null_rate is not None]
            if null_rates:
                avg_null = sum(null_rates) / len(null_rates)
                if avg_null > 0.05:
                    score -= min(0.25, avg_null)
                    factors.append(
                        f"les tables utilisées présentent en moyenne {avg_null*100:.0f}% de valeurs manquantes"
                    )
            else:
                score -= 0.1
                factors.append("les tables utilisées ne sont pas encore évaluées (qualité inconnue)")

    # 2) Concepts métier : aucun concept validé en V0.1.
    factors.append("aucun concept métier validé (compréhension métier disponible en V0.2)")
    score -= 0.05

    # 3) Ambiguïté / hypothèses retenues par le moteur SQL.
    if assumptions:
        score -= min(0.15, 0.05 * len(assumptions))
        factors.append(f"{len(assumptions)} hypothèse(s) retenue(s) faute de définition explicite")

    # 4) Couverture des données.
    if sampled:
        score -= 0.1
        factors.append("analyse fondée sur un échantillon, pas sur l'intégralité des données")
    if truncated:
        score -= 0.1
        factors.append("résultats tronqués par le LIMIT automatique")
    if row_count == 0:
        score -= 0.2
        factors.append("aucune ligne retournée")

    return Confidence(score=max(0.0, min(1.0, score)), factors=factors)
