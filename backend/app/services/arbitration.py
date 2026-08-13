"""Moteur d'ARBITRAGE de concepts — primitive GÉNÉRIQUE du produit.

Problème générique : plusieurs définitions plausibles ont été détectées pour un
même concept métier. Le moteur :

  1. mesure l'IMPACT de chaque définition (nombre d'entités) — via une requête de
     comptage auditable, sans interpréter aucune sémantique métier ;
  2. prévisualise la PROPAGATION d'un changement de référence (réponses, découvertes
     concernées ; rapports historiques conservés) ;
  3. applique l'ARBITRAGE : la définition choisie devient la référence en vigueur,
     les autres sont archivées, la version du concept est incrémentée.

L'objet arbitré est un CONCEPT. Ce module ne connaît ni magasin, ni client, ni
produit, ni région : il fonctionne à l'identique pour « Magasin actif » (Démo
Retail), « Client actif » (SaaS), « Mission active » (conseil)… (voir CLAUDE.md).
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.concept_definition import ConceptDefinition

# Statuts d'une définition en lice pour l'arbitrage.
_LIVE = ("candidate", "needs_arbitration", "validated")


@dataclass
class DefinitionImpact:
    definition_id: int
    label: str
    definition_text: str
    entity_label: str
    count: int | None
    is_reference: bool
    status: str


def definitions_of(db: Session, concept_id: int, *, include_archived: bool = False) -> list[ConceptDefinition]:
    q = select(ConceptDefinition).where(ConceptDefinition.concept_id == concept_id)
    if not include_archived:
        q = q.where(ConceptDefinition.status.in_(_LIVE))
    return list(db.execute(q.order_by(ConceptDefinition.id)).scalars().all())


def is_ambiguous(db: Session, concept_id: int) -> bool:
    """Ambigu = au moins deux définitions concurrentes en lice."""
    return len(definitions_of(db, concept_id)) >= 2


def evaluate_impact(adapter, connection_id: int, definition: ConceptDefinition) -> int | None:
    """Nombre d'entités satisfaisant la définition — exécution du `count_sql` tel
    quel, aucune connaissance métier. Renvoie None si la définition n'est pas
    mesurable (pas de requête)."""
    if not definition.count_sql:
        return None
    res = adapter.run_query(definition.count_sql, connection_id=connection_id)
    if res.rows and res.rows[0] and res.rows[0][0] is not None:
        return int(res.rows[0][0])
    return 0


def refresh_impacts(db: Session, adapter, connection_id: int, concept_id: int) -> list[DefinitionImpact]:
    """(Re)calcule et mémorise l'impact de chaque définition en lice."""
    out: list[DefinitionImpact] = []
    for d in definitions_of(db, concept_id):
        d.impact_count = evaluate_impact(adapter, connection_id, d)
        out.append(DefinitionImpact(
            definition_id=d.id, label=d.label, definition_text=d.definition_text,
            entity_label=d.entity_label, count=d.impact_count,
            is_reference=d.is_reference, status=d.status,
        ))
    db.flush()
    return out


def propagation_preview(references: list[dict], concept_id: int) -> dict:
    """Prévisualise ce qu'un changement de référence IMPACTE, en buckets GÉNÉRIQUES.

    `references` : les artefacts qui s'appuient sur le concept, chacun
    `{"concept_id", "kind": "answer"|"discovery"|"report", "immutable": bool}`.
    Les rapports historiques immuables sont CONSERVÉS tels quels (jamais réécrits) ;
    les réponses et découvertes sont à revérifier."""
    rel = [r for r in references if r.get("concept_id") == concept_id]
    answers = sum(1 for r in rel if r.get("kind") == "answer")
    discoveries = sum(1 for r in rel if r.get("kind") == "discovery")
    reports_kept = sum(1 for r in rel if r.get("kind") == "report" and r.get("immutable"))
    reports_open = sum(1 for r in rel if r.get("kind") == "report" and not r.get("immutable"))
    return {
        "answers_affected": answers,
        "discoveries_to_recheck": discoveries,
        "reports_preserved": reports_kept,
        "reports_to_revise": reports_open,
    }


def arbitrate(db: Session, concept_id: int, chosen_definition_id: int,
              *, actor: str | None = None) -> ConceptDefinition:
    """La définition choisie devient la RÉFÉRENCE en vigueur ; les concurrentes
    sont archivées ; la version du concept est incrémentée. Générique : aucune
    règle ne dépend de la nature du concept."""
    defs = definitions_of(db, concept_id, include_archived=True)
    chosen = next((d for d in defs if d.id == chosen_definition_id), None)
    if chosen is None:
        raise ValueError("Définition introuvable pour ce concept.")
    next_version = max((d.definition_version for d in defs), default=0) + 1
    for d in defs:
        if d.id == chosen.id:
            d.is_reference = True
            d.status = "validated"
            d.definition_version = next_version
            d.owner_ref = actor or d.owner_ref
        elif d.status in _LIVE:
            d.is_reference = False
            d.status = "archived"
    db.flush()
    return chosen
