"""Propagation E1 — moteur GÉNÉRIQUE des effets d'un changement de définition.

Quand la définition de référence d'un concept change, les artefacts qui s'appuient
dessus doivent réagir — TOUJOURS de la même façon, quel que soit le domaine :

    réponses non figées        → recalcul (marquées « stale »)
    découvertes                → « en_reverification » (+ cache invalidé)
    rapports validés (figés)    → CONSERVÉS intacts, avec une mention

C'est la SEULE logique de propagation du produit : l'arbitrage l'appelle, il ne la
recrée pas. `preview` calcule les effets AVANT toute mutation ; `apply` les exécute.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.concept_arbitration import ConceptReference


def references_for(db: Session, concept_id: int) -> list[ConceptReference]:
    return list(db.execute(
        select(ConceptReference).where(ConceptReference.concept_id == concept_id)
    ).scalars().all())


def preview(db: Session, concept_id: int, *, next_version: int | None = None) -> dict:
    """Effets ATTENDUS d'un changement de référence — sans rien muter. Buckets
    génériques : réponses concernées, découvertes à revérifier, rapports conservés."""
    refs = references_for(db, concept_id)
    answers = [r for r in refs if r.kind == "answer"]
    discoveries = [r for r in refs if r.kind == "discovery"]
    reports_kept = [r for r in refs if r.kind == "report" and r.immutable]
    reports_open = [r for r in refs if r.kind == "report" and not r.immutable]
    return {
        "answers_affected": len(answers),
        "discoveries_to_recheck": len(discoveries),
        "reports_preserved": len(reports_kept),
        "reports_to_revise": len(reports_open),
        "preserved_labels": [r.ref_label for r in reports_kept if r.ref_label][:5],
        "new_version": next_version,
    }


def apply(db: Session, concept_id: int, *, next_version: int | None = None) -> dict:
    """Exécute la propagation. Idempotent sur le statut. À appeler DANS la même
    transaction que l'arbitrage (rien ne doit rester partiellement modifié)."""
    refs = references_for(db, concept_id)
    touched_connections: set[int] = set()
    for r in refs:
        if r.kind == "answer" and not r.immutable:
            r.status = "stale"                    # non figée → recalcul
        elif r.kind == "discovery":
            r.status = "en_reverification"
            if r.connection_id:
                touched_connections.add(r.connection_id)
        elif r.kind == "report":
            # Rapport validé = figé : conservé tel quel, seulement mentionné.
            r.status = "preserved" if r.immutable else "stale"
    # Réutilise le mécanisme existant : invalider le cache des Découvertes force
    # leur recalcul (pas de seconde logique de propagation).
    from app.services import discoveries as disc_svc
    for cid in touched_connections:
        try:
            disc_svc.invalidate(cid)
        except Exception:
            pass
    db.flush()
    return preview(db, concept_id, next_version=next_version)
