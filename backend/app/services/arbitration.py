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
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.concept_definition import ConceptDefinition

# Statuts d'une définition en lice pour l'arbitrage.
_LIVE = ("candidate", "needs_arbitration", "validated")


class StaleImpactError(Exception):
    """L'impact de la définition choisie est obsolète (les données ont changé
    depuis le preview) : il faut le recalculer avant d'arbitrer."""


@dataclass
class DefinitionImpact:
    definition_id: int
    label: str
    definition_text: str
    entity_label: str
    count: int | None
    is_reference: bool
    status: str


def definitions_of(db: Session, concept_id: int, *, space_id: int | None = None,
                   include_archived: bool = False) -> list[ConceptDefinition]:
    """Définitions EFFECTIVES pour une portée. Modèle Univers ↔ Espace : la
    définition de l'Univers est commune ; un espace peut la SURCHARGER. Si l'espace
    courant a ses propres définitions, elles PRIMENT ; sinon il HÉRITE de l'Univers."""
    q = select(ConceptDefinition).where(ConceptDefinition.concept_id == concept_id)
    if not include_archived:
        q = q.where(ConceptDefinition.status.in_(_LIVE))
    rows = list(db.execute(q.order_by(ConceptDefinition.id)).scalars().all())
    if space_id is not None:
        overrides = [d for d in rows if d.scope == "space" and d.space_id == space_id]
        if overrides:
            return overrides
    return [d for d in rows if d.scope == "universe"]


def effective_scope(db: Session, concept_id: int, space_id: int | None) -> str:
    """« space » si l'espace courant surcharge le concept, sinon « universe »
    (hérité). Sert à l'UI : distinguer une définition propre d'une définition héritée."""
    if space_id is None:
        return "universe"
    overrides = db.execute(
        select(ConceptDefinition.id).where(
            ConceptDefinition.concept_id == concept_id,
            ConceptDefinition.scope == "space", ConceptDefinition.space_id == space_id,
            ConceptDefinition.status.in_(_LIVE),
        ).limit(1)
    ).scalar_one_or_none()
    return "space" if overrides is not None else "universe"


def is_ambiguous(db: Session, concept_id: int, *, space_id: int | None = None) -> bool:
    """Ambigu = au moins deux définitions concurrentes en lice (dans la portée)."""
    return len(definitions_of(db, concept_id, space_id=space_id)) >= 2


# --- Fraîcheur de l'impact : quand, sur quel snapshot, quelles sources ---------
def _current_snapshot_id(db: Session, connection_id: int) -> str | None:
    from app.models.schema_catalog import SchemaSnapshot
    row = db.execute(
        select(SchemaSnapshot.id).where(
            SchemaSnapshot.connection_id == connection_id,
            SchemaSnapshot.is_current.is_(True),
        )
    ).scalar_one_or_none()
    return str(row) if row is not None else None


def _sources_snapshot(db: Session, source_ids: list | None) -> str | None:
    ids = [_current_snapshot_id(db, cid) for cid in (source_ids or [])]
    ids = [i for i in ids if i]
    return ",".join(sorted(ids)) if ids else None


def is_stale(db: Session, d: ConceptDefinition) -> bool:
    """Obsolète si le snapshot COURANT des sources diffère de celui évalué. Si le
    snapshot courant est indéterminable, on ne bloque pas (bénéfice du doute)."""
    if not d.source_ids:
        return False
    cur = _sources_snapshot(db, d.source_ids)
    if cur is None:
        return False
    return d.snapshot_id != cur


def freshness(db: Session, d: ConceptDefinition) -> dict:
    return {
        "evaluated_at": d.evaluated_at.isoformat() if d.evaluated_at else None,
        "snapshot_id": d.snapshot_id,
        "source_ids": d.source_ids or [],
        "is_stale": is_stale(db, d),
    }


def recompute_impact(db: Session, d: ConceptDefinition, *, adapter=None,
                     connection_id: int | None = None) -> ConceptDefinition:
    """Recalcule l'impact sur la source (si disponible) et rafraîchit la fraîcheur
    (evaluated_at + snapshot courant) — ce qui lève l'obsolescence."""
    if adapter is not None and connection_id is not None and d.count_sql:
        try:
            d.impact_count = evaluate_impact(adapter, connection_id, d)
        except Exception:
            pass
    d.evaluated_at = datetime.now(timezone.utc)
    cur = _sources_snapshot(db, d.source_ids)
    if cur is not None:
        d.snapshot_id = cur
    db.flush()
    return d


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


def next_version_for(db: Session, concept_id: int, *, space_id: int | None = None) -> int:
    defs = definitions_of(db, concept_id, space_id=space_id, include_archived=True)
    return max((d.definition_version for d in defs), default=0) + 1


def arbitration_preview(db: Session, concept_id: int, chosen_definition_id: int,
                        *, space_id: int | None = None) -> dict:
    """Preview COMPLET calculé AVANT toute mutation (rule 2) : définition actuelle,
    options candidates + impact ET FRAÎCHEUR de chacune, effets de propagation,
    future version. Aucun effet de bord : jamais un PATCH aveugle."""
    from app.services import propagation

    defs = definitions_of(db, concept_id, space_id=space_id)
    current = next((d for d in defs if d.is_reference), None)
    chosen = next((d for d in defs if d.id == chosen_definition_id), None)
    nv = next_version_for(db, concept_id, space_id=space_id)
    options = [
        {"id": d.id, "label": d.label, "definition_text": d.definition_text,
         "impact_count": d.impact_count, "entity_label": d.entity_label,
         "is_reference": d.is_reference, **freshness(db, d)}
        for d in defs
    ]
    return {
        "concept_id": concept_id,
        "scope_type": effective_scope(db, concept_id, space_id),
        "current_definition_id": current.id if current else None,
        "chosen_definition_id": chosen_definition_id,
        "options": options,
        "chosen_is_stale": bool(chosen is not None and is_stale(db, chosen)),
        "any_stale": any(o["is_stale"] for o in options),
        "propagation": propagation.preview(db, concept_id, next_version=nv),
        "new_version": nv,
        "creates_new_version": chosen is not None and not chosen.is_reference,
    }


def arbitrate(db: Session, concept_id: int, chosen_definition_id: int,
              *, actor: str | None = None, space_id: int | None = None) -> dict:
    """TRANSACTIONNEL (rule 3) : une seule opération passe la définition choisie en
    référence, archive les concurrentes, incrémente la version, écrit l'audit et
    déclenche la propagation E1. Contrôle de FRAÎCHEUR final : refuse d'arbitrer sur
    un impact obsolète. Le commit relève de l'appelant : si une étape lève, rien
    n'est validé. Générique : aucune règle ne dépend de la nature du concept."""
    from app.models.concept_arbitration import ConceptArbitration
    from app.services import propagation

    defs = definitions_of(db, concept_id, space_id=space_id, include_archived=True)
    chosen = next((d for d in defs if d.id == chosen_definition_id), None)
    if chosen is None:
        raise ValueError("Définition introuvable pour ce concept.")
    if is_stale(db, chosen):
        raise StaleImpactError(
            "L'impact a été calculé sur des données qui ont changé depuis. "
            "Recalculez l'impact avant d'arbitrer.")
    next_version = max((d.definition_version for d in defs), default=0) + 1
    tenant_id = chosen.tenant_id
    for d in defs:
        if d.id == chosen.id:
            d.is_reference = True
            d.status = "validated"
            d.definition_version = next_version
            d.owner_ref = actor or d.owner_ref
        elif d.status in _LIVE:
            d.is_reference = False
            d.status = "archived"
    # Propagation E1 (logique partagée, jamais dupliquée) DANS la même transaction.
    effects = propagation.apply(db, concept_id, next_version=next_version)
    db.add(ConceptArbitration(
        tenant_id=tenant_id, concept_id=concept_id, chosen_definition_id=chosen.id,
        definition_version=next_version, actor=actor, propagation=effects,
    ))
    db.flush()
    return {"chosen": chosen, "version": next_version, "propagation": effects}
