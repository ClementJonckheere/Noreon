"""Mémoire du moteur de raisonnement — apprendre les stratégies efficaces.

Aujourd'hui chaque investigation repart de zéro. Ici, l'agent **se souvient** de
quelles dimensions / chaînes de jointures portent le plus de signal pour un sujet
donné, et les **teste en priorité** la fois suivante.

    orders → customers → stores  s'avère souvent une excellente chaîne
      → la prochaine fois, on la teste avant les autres.

L'efficacité est une **moyenne mobile exponentielle** du « power » observé lors
des segmentations. Tout est déterministe, borné au tenant (via la connexion),
et sans aucune donnée métier brute.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.reasoning import ReasoningMemory

_ALPHA = 0.4  # poids de la dernière observation dans la moyenne mobile


def effectiveness_map(db: Session, connection_id: int, subject: str) -> dict[str, float]:
    rows = db.execute(
        select(ReasoningMemory.dimension_label, ReasoningMemory.effectiveness).where(
            ReasoningMemory.connection_id == connection_id,
            ReasoningMemory.subject_table == subject,
        )
    ).all()
    return {label: eff for label, eff in rows}


def rank(dims: list, db: Session, connection_id: int, subject: str) -> tuple[list, list[str]]:
    """Réordonne les dimensions candidates : les stratégies éprouvées d'abord.

    Renvoie (dimensions réordonnées, labels priorisés par la mémoire). Tri stable
    par efficacité décroissante — les dimensions inconnues (efficacité 0) gardent
    leur ordre d'origine, sous les stratégies déjà éprouvées.
    """
    eff = effectiveness_map(db, connection_id, subject)
    if not eff:
        return dims, []
    ordered = sorted(dims, key=lambda d: -eff.get(getattr(d, "label", ""), 0.0))
    prioritized = [getattr(d, "label", "") for d in ordered
                   if eff.get(getattr(d, "label", ""), 0.0) > 0][:3]
    return ordered, prioritized


def record(db: Session, connection_id: int, subject: str,
           observations: list[tuple[str, float]]) -> None:
    """Met à jour la mémoire avec le signal observé (label, power) par dimension.

    Le caller valide la transaction (on se contente d'un flush)."""
    if not observations:
        return
    existing = {
        m.dimension_label: m for m in db.execute(
            select(ReasoningMemory).where(
                ReasoningMemory.connection_id == connection_id,
                ReasoningMemory.subject_table == subject,
            )
        ).scalars()
    }
    for label, power in observations:
        if not label:
            continue
        m = existing.get(label)
        if m is None:
            m = ReasoningMemory(
                connection_id=connection_id, subject_table=subject,
                dimension_label=label, effectiveness=float(power), observations=1,
            )
            db.add(m)
            existing[label] = m
        else:
            m.effectiveness = _ALPHA * float(power) + (1 - _ALPHA) * m.effectiveness
            m.observations += 1
    db.flush()
