"""Moteur de RELATIONS candidates — primitive GÉNÉRIQUE (comme l'arbitrage).

Un lien entre deux champs n'est jamais jugé sur la seule COUVERTURE : le moteur
mesure aussi l'unicité de la clé cible, la compatibilité de type, la cardinalité,
le nombre d'exceptions et la fenêtre vérifiée ; il conserve le meilleur CANDIDAT
ALTERNATIF (« pourquoi cette colonne et pas une autre ? ») et prévisualise CE QUE
LA RELATION REND POSSIBLE à partir du graphe/concepts réellement disponibles.

Aucun domaine ici : « sales.article_reference → articles.reference » (Retail) et
« subscriptions.account_id → accounts.id » (SaaS) passent par le même code.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.relation_candidate import RelationCandidate
from app.models.semantic import BusinessConcept, ConceptMapping

_LIVE = ("candidate", "needs_validation", "validated")


class StaleRelationError(Exception):
    """Les faits de la relation ont été recalculés sur des données obsolètes."""


# --- Évaluation FACTUELLE (générique, SQL réel) -------------------------------
def _scalar(adapter, connection_id: int, sql: str):
    res = adapter.run_query(sql, connection_id=connection_id)
    if res.rows and res.rows[0] and res.rows[0][0] is not None:
        return res.rows[0][0]
    return None


def evaluate(adapter, connection_id: int, left: dict, right: dict) -> dict:
    """Faits d'un lien champ→champ : couverture, unicité cible, exceptions,
    cardinalité — via COUNT réels, sans aucune sémantique métier."""
    lt, lc = left["table"], left["column"]
    rt, rc = right["table"], right["column"]
    total = _scalar(adapter, connection_id, f"SELECT count({lc}) FROM {lt} WHERE {lc} IS NOT NULL")
    matched = _scalar(adapter, connection_id,
                      f"SELECT count(*) FROM {lt} l WHERE l.{lc} IS NOT NULL "
                      f"AND l.{lc} IN (SELECT r.{rc} FROM {rt} r)")
    r_total = _scalar(adapter, connection_id, f"SELECT count({rc}) FROM {rt} WHERE {rc} IS NOT NULL")
    r_distinct = _scalar(adapter, connection_id, f"SELECT count(DISTINCT {rc}) FROM {rt} WHERE {rc} IS NOT NULL")
    total = int(total or 0); matched = int(matched or 0)
    coverage = (matched / total) if total else None
    uniqueness = (int(r_distinct) / int(r_total)) if (r_distinct and r_total) else None
    exceptions = (total - matched) if total else None
    # Cardinalité : cible unique ⇒ plusieurs gauches pour une droite (n → 1).
    cardinality = "n-1" if (uniqueness is not None and uniqueness >= 0.999) else "n-n"
    return {"coverage": coverage, "target_uniqueness": uniqueness,
            "exceptions_count": exceptions, "cardinality": cardinality}


# --- Cycle de vie -------------------------------------------------------------
def list_candidates(db: Session, tenant_id: int, *, connection_id: int | None = None,
                    include_archived: bool = False) -> list[RelationCandidate]:
    q = select(RelationCandidate).where(RelationCandidate.tenant_id == tenant_id)
    if connection_id is not None:
        q = q.where(RelationCandidate.connection_id == connection_id)
    if not include_archived:
        q = q.where(RelationCandidate.status.in_(_LIVE))
    return list(db.execute(q.order_by(RelationCandidate.id)).scalars().all())


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


def is_stale(db: Session, r: RelationCandidate) -> bool:
    """Une relation validée peut devenir « à revérifier » : obsolète si le snapshot
    courant des sources diffère de celui évalué (indéterminable ⇒ non bloquant)."""
    if not r.source_ids:
        return False
    cur = _sources_snapshot(db, r.source_ids)
    if cur is None:
        return False
    return r.snapshot_id != cur


def _concepts_on(db: Session, tenant_id: int, table: str) -> list[str]:
    rows = db.execute(
        select(BusinessConcept.name)
        .join(ConceptMapping, ConceptMapping.concept_id == BusinessConcept.id)
        .where(BusinessConcept.tenant_id == tenant_id, ConceptMapping.table_name == table)
        .distinct()
    ).scalars().all()
    return list(rows)


def entity_label(db: Session, tenant_id: int, table: str) -> str:
    """Libellé MÉTIER représentatif d'une table (« products » → « Produit »), via la
    Semantic Layer. Aucun domaine codé : on choisit parmi les concepts RÉELS mappés."""
    import re as _re
    from app.services.concepts import subject_domain
    concepts = _concepts_on(db, tenant_id, table)
    if not concepts:
        return subject_domain(table)
    toks = set(_re.findall(r"[a-z]+", table.lower()))
    for c in concepts:
        cl = c.lower()
        if any(t[:4] and (t[:4] in cl or cl[:4] in t) for t in toks):
            return c
    return concepts[0]


def preview(db: Session, r: RelationCandidate) -> dict:
    """CE QUE LA RELATION REND POSSIBLE — dérivé du graphe/concepts RÉELS, jamais de
    phrases codées. Croiser les concepts d'une table avec ceux de l'autre ouvre des
    analyses ; les concepts des deux tables deviennent reliables."""
    left_concepts = _concepts_on(db, r.tenant_id, r.left_table)
    right_concepts = _concepts_on(db, r.tenant_id, r.right_table)
    linkable = sorted(set(left_concepts) | set(right_concepts))
    analyses_possible = len(left_concepts) * len(right_concepts)
    # Exemples construits à partir des VRAIS libellés de concepts (max 3).
    examples: list[str] = []
    for lc in left_concepts[:3]:
        for rc in right_concepts[:3]:
            if lc != rc:
                examples.append(f"croiser « {lc} » et « {rc} »")
    return {
        "analyses_possible": analyses_possible,
        "concepts_linkable": len(linkable),
        "linkable_labels": linkable[:6],
        "examples": examples[:3],
    }


def freshness(db: Session, r: RelationCandidate) -> dict:
    return {
        "evaluated_at": r.evaluated_at.isoformat() if r.evaluated_at else None,
        "snapshot_id": r.snapshot_id, "source_ids": r.source_ids or [],
        "is_stale": is_stale(db, r),
    }


def validate(db: Session, r: RelationCandidate, *, actor: str | None = None) -> RelationCandidate:
    """Validation = un humain AUTORISE Noreon à utiliser la relation. On fige la
    fenêtre de validation, le snapshot et les faits (evidence). Une FK déclarée par
    la base a un statut supérieur (origin=constraint) à une simple inférence validée."""
    now = datetime.now(timezone.utc)
    r.status = "validated"
    r.validated_by = actor
    r.validated_at = now
    r.validation_window = {
        "from": r.valid_from.isoformat() if r.valid_from else None,
        "to": (r.valid_to or date.today()).isoformat(),
    }
    r.evidence = {
        "coverage": r.coverage, "target_uniqueness": r.target_uniqueness,
        "type_compatibility": r.type_compatibility, "cardinality": r.cardinality,
        "exceptions_count": r.exceptions_count, "snapshot_id": r.snapshot_id,
        "alternatives": r.alternatives, "origin": r.origin,
    }
    db.flush()
    return r


def reject(db: Session, r: RelationCandidate, *, actor: str | None = None) -> RelationCandidate:
    """Refus explicite conservé (historique d'une relation examinée puis écartée)."""
    r.status = "rejected"
    r.validated_by = actor
    r.validated_at = datetime.now(timezone.utc)
    db.flush()
    return r
