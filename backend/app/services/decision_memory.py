"""Mémoire métier des décisions — boucle d'amélioration continue.

Chaque analyse ne repart pas de zéro : le moteur **se souvient** des
recommandations que les décideurs ont retenues, mises en œuvre ou dont ils ont
constaté l'effet. La fois suivante, sur un sujet comparable, il annote la
recommandation :

    « Déjà appliquée avec succès dans un contexte similaire. »

C'est un signal ancré sur des faits (l'humain qualifie le résultat), jamais une
promesse. Tout est déterministe, borné au tenant via la connexion, et ne stocke
aucune donnée métier brute — seulement l'axe d'analyse (table de faits), le rôle
et le texte de la recommandation.
"""
from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.decision import DecisionRecord

# Statuts qualifiés par l'humain (human-in-the-loop).
STATUSES = {"retained", "implemented", "successful", "abandoned"}


def _norm(text: str) -> set[str]:
    """Sac de mots normalisé d'une recommandation, pour rapprocher deux
    formulations proches (« campagne de réactivation ciblée sur … »)."""
    return {w for w in re.findall(r"[a-zàâçéèêëîïôûùüÿœ]{4,}", (text or "").lower())}


def record_feedback(db: Session, connection_id: int, tenant_id: int, *, subject: str,
                    role: str, recommendation: str, status: str,
                    note: str | None = None) -> DecisionRecord:
    """Journalise le retour d'un décideur sur une recommandation.

    Le caller valide la transaction (on se contente d'un flush)."""
    if status not in STATUSES:
        status = "retained"
    rec = DecisionRecord(
        tenant_id=tenant_id, connection_id=connection_id, subject=subject,
        role=role, recommendation=recommendation, status=status, note=note,
    )
    db.add(rec)
    db.flush()
    return rec


def history_for(db: Session, connection_id: int, subject: str) -> list[DecisionRecord]:
    """Décisions déjà journalisées pour ce sujet (table de faits), récentes d'abord."""
    return list(
        db.execute(
            select(DecisionRecord)
            .where(
                DecisionRecord.connection_id == connection_id,
                DecisionRecord.subject == subject,
            )
            .order_by(DecisionRecord.created_at.desc())
            .limit(50)
        ).scalars()
    )


# Formulations ancrées sur le fait constaté — jamais une promesse.
_HISTORY_PHRASE = {
    "successful": "Déjà appliquée avec succès dans un contexte similaire.",
    "implemented": "Déjà mise en œuvre sur ce périmètre — l'effet reste à confirmer.",
    "retained": "Déjà retenue lors d'une analyse précédente.",
    "abandoned": "Déjà envisagée puis écartée précédemment — à réexaminer.",
}
# Ordre de préséance : un succès prime sur une simple rétention.
_STATUS_RANK = {"successful": 3, "implemented": 2, "retained": 1, "abandoned": 0}


def annotate(records: list[DecisionRecord], role: str, recommendation: str) -> str | None:
    """Renvoie une annotation d'historique si une recommandation proche a déjà été
    qualifiée pour ce rôle. On rapproche par recouvrement lexical (≥ 40 %)."""
    target = _norm(recommendation)
    if not target:
        return None
    best: DecisionRecord | None = None
    for r in records:
        if r.role != role:
            continue
        prior = _norm(r.recommendation)
        if not prior:
            continue
        overlap = len(target & prior) / len(target)
        if overlap < 0.4:
            continue
        if best is None or _STATUS_RANK.get(r.status, 0) > _STATUS_RANK.get(best.status, 0):
            best = r
    if best is None:
        return None
    return _HISTORY_PHRASE.get(best.status, _HISTORY_PHRASE["retained"])
