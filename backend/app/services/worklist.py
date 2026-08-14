"""Worklist — dérive les `WorkItem` (À traiter) et `ActivityEvent` (Suivi) de l'état
RÉEL du produit, jamais de notifications fictives.

Invariants (verrouillés) :
- LECTURE ≠ RÉSOLUTION : marquer lu ne change jamais le `status` d'un WorkItem.
  Un WorkItem ne quitte « À traiter » que lorsque l'objet métier atteint réellement
  l'état attendu (réconciliation ci-dessous).
- ASSIGNATION PAR CAPABILITY : chaque WorkItem porte une `required_capability` ;
  un utilisateur ne voit que ce qu'il peut traiter. Un entrepreneur seul possède
  les capacités et reçoit tout ; une organisation filtre par capacité, sans aucun
  rôle codé en dur.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.concept_definition import ConceptDefinition
from app.models.decision import DecisionRecord
from app.models.measurement import MeasurementPlan
from app.models.relation_candidate import RelationCandidate
from app.models.semantic import BusinessConcept
from app.models.space import Space
from app.models.user import ROLE_ANALYST, ROLE_ADMIN, ROLE_ORDER
from app.models.work_item import ActivityEvent, WorkItem

# kind (primitive produit) → capability requise (jamais un rôle en dur).
CAP_BY_KIND = {
    "concept_arbitration": "manage_concepts",
    "relation_validation": "manage_concepts",
    "report_validation": "validate_report",
    "measurement_due": "decide_action",
    "quality_review": "inspect_quality",
    "access_approval": "approve_access",
}
# capability → rôle minimal (traduction locale ; l'assignation reste par capacité).
CAP_MIN_ROLE = {
    "manage_concepts": ROLE_ANALYST,
    "validate_report": ROLE_ANALYST,
    "decide_action": ROLE_ANALYST,
    "inspect_quality": ROLE_ANALYST,
    "approve_access": ROLE_ADMIN,
}


def can_act(role: str, capability: str | None) -> bool:
    if capability is None:
        return True
    need = CAP_MIN_ROLE.get(capability, ROLE_ANALYST)
    return ROLE_ORDER.get(role, 0) >= ROLE_ORDER.get(need, 0)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _upsert_work(db: Session, tenant_id: int, kind: str, otype: str, oid,
                 *, title: str, reason: str, space_id: int | None = None) -> WorkItem:
    oid = str(oid)
    wi = db.execute(
        select(WorkItem).where(
            WorkItem.tenant_id == tenant_id, WorkItem.kind == kind,
            WorkItem.object_type == otype, WorkItem.object_id == oid)
    ).scalars().first()
    if wi is not None:
        # L'objet est (de nouveau) dans l'état déclencheur : rouvrir si besoin.
        if wi.status in ("traite", "clos"):
            wi.status = "a_traiter"
            wi.resolved_at = None
        wi.title, wi.reason, wi.space_id = title, reason, space_id
        return wi
    wi = WorkItem(tenant_id=tenant_id, kind=kind, object_type=otype, object_id=oid,
                  title=title, reason=reason, space_id=space_id,
                  required_capability=CAP_BY_KIND.get(kind), status="a_traiter")
    db.add(wi)
    return wi


def _upsert_activity(db: Session, tenant_id: int, kind: str, otype: str, oid,
                     *, title: str, detail: str, space_id: int | None = None) -> None:
    oid = str(oid)
    ev = db.execute(
        select(ActivityEvent).where(
            ActivityEvent.tenant_id == tenant_id, ActivityEvent.kind == kind,
            ActivityEvent.object_type == otype, ActivityEvent.object_id == oid).limit(1)
    ).scalars().first()
    if ev is None:
        db.add(ActivityEvent(tenant_id=tenant_id, kind=kind, object_type=otype,
                             object_id=oid, title=title, detail=detail, space_id=space_id))
    else:  # rafraîchit le libellé/espace (idempotent, pas de doublon)
        ev.title, ev.detail = title, detail
        if space_id is not None:
            ev.space_id = space_id


def reconcile(db: Session, tenant_id: int) -> None:
    """Aligne les WorkItems sur l'état réel : crée ceux qui manquent, RÉSOUT ceux
    dont l'objet a quitté l'état déclencheur (et émet alors un ActivityEvent de suivi).
    Réels événements branchés — aucune notification fictive."""
    active: set[tuple[str, str, str]] = set()

    # 1. Concept ambigu (≥ 2 définitions en lice) → arbitrage nécessaire.
    concepts = db.execute(
        select(BusinessConcept).where(BusinessConcept.tenant_id == tenant_id)
    ).scalars().all()
    for c in concepts:
        live = db.execute(
            select(ConceptDefinition.id).where(
                ConceptDefinition.concept_id == c.id,
                ConceptDefinition.status.in_(("candidate", "needs_arbitration", "validated")))
        ).scalars().all()
        if len(live) >= 2:
            _upsert_work(db, tenant_id, "concept_arbitration", "concept", c.id,
                         title=c.name, reason="Définition à arbitrer",
                         space_id=_concept_space(db, tenant_id, c.id))
            active.add(("concept_arbitration", "concept", str(c.id)))

    # 2. Relation à valider.
    rels = db.execute(
        select(RelationCandidate).where(
            RelationCandidate.tenant_id == tenant_id,
            RelationCandidate.status == "needs_validation")
    ).scalars().all()
    for r in rels:
        n = r.exceptions_count or 0
        _upsert_work(db, tenant_id, "relation_validation", "relation", r.id,
                     title=_relation_title(db, tenant_id, r),
                     reason=f"{n} exception{'s' if n != 1 else ''} · validation nécessaire",
                     space_id=_space_of_connection(db, tenant_id, r.connection_id))
        active.add(("relation_validation", "relation", str(r.id)))

    # 3. Mesure disponible : action mise en œuvre, baseline figé, aucune mesure encore.
    decisions = db.execute(
        select(DecisionRecord).where(DecisionRecord.tenant_id == tenant_id)
    ).scalars().all()
    for d in decisions:
        plan = db.execute(
            select(MeasurementPlan).where(MeasurementPlan.decision_id == d.id)
        ).scalars().first()
        if plan is not None and plan.baseline_target is not None and not plan.runs \
                and d.status == "implemented":
            _upsert_work(db, tenant_id, "measurement_due", "decision", d.id,
                         title=d.recommendation[:80], reason="Résultat mesurable disponible")
            active.add(("measurement_due", "decision", str(d.id)))
        # Suivi : une mesure déjà effectuée est un ActivityEvent, pas un WorkItem.
        # Rattaché à l'espace RÉEL de la source (jamais un univers live générique).
        if d.status == "measured":
            _upsert_activity(db, tenant_id, "measurement_done", "decision", d.id,
                             title=d.recommendation[:80], detail="Résultat contrôlé disponible",
                             space_id=_space_of_connection(db, tenant_id, d.connection_id))

    # Suivi : relations validées.
    for r in db.execute(
        select(RelationCandidate).where(
            RelationCandidate.tenant_id == tenant_id,
            RelationCandidate.status == "validated")
    ).scalars().all():
        _upsert_activity(db, tenant_id, "relation_validated", "relation", r.id,
                         title=_relation_title(db, tenant_id, r), detail="Relation validée",
                         space_id=_space_of_connection(db, tenant_id, r.connection_id))

    # Résolution : tout WorkItem « À traiter » dont l'objet n'est PLUS déclencheur.
    for wi in db.execute(
        select(WorkItem).where(
            WorkItem.tenant_id == tenant_id, WorkItem.status == "a_traiter")
    ).scalars().all():
        if (wi.kind, wi.object_type, wi.object_id) not in active:
            wi.status = "traite"
            wi.resolved_at = _now()
            _upsert_activity(db, tenant_id, f"{wi.kind}_resolved", wi.object_type, wi.object_id,
                             title=wi.title, detail="Traité", space_id=wi.space_id)
    db.flush()


def _space_of_connection(db: Session, tenant_id: int, connection_id: int | None) -> int | None:
    if connection_id is None:
        return None
    from app.models.space import SpaceConnection
    return db.execute(
        select(SpaceConnection.space_id).where(SpaceConnection.connection_id == connection_id).limit(1)
    ).scalar_one_or_none()


# --- Libellés MÉTIER via la Semantic Layer (jamais de nom physique dans la file) ---
def _entity_label(db: Session, tenant_id: int, table: str) -> str:
    """Concept métier représentatif d'une table (« products » → « Produit »). Aucun
    domaine codé : on choisit parmi les concepts RÉELS mappés à la table."""
    from app.services.concepts import subject_domain
    from app.services.relations import _concepts_on
    concepts = _concepts_on(db, tenant_id, table)
    if not concepts:
        return subject_domain(table)
    toks = set(re.findall(r"[a-z]+", table.lower()))
    for c in concepts:                       # concept dont le nom recoupe la table
        cl = c.lower()
        if any(t[:4] and (t[:4] in cl or cl[:4] in t) for t in toks):
            return c
    return concepts[0]                        # à défaut, le concept représentatif


def _relation_title(db: Session, tenant_id: int, r) -> str:
    left = _entity_label(db, tenant_id, r.left_table)
    right = _entity_label(db, tenant_id, r.right_table)
    return f"Relation {left} → {right}"


def _concept_space(db: Session, tenant_id: int, concept_id: int) -> int | None:
    """Espace RÉEL des données d'un concept (via les sources de ses définitions)."""
    for d in db.execute(
        select(ConceptDefinition).where(ConceptDefinition.concept_id == concept_id)
    ).scalars().all():
        for cid in (d.source_ids or []):
            sp = _space_of_connection(db, tenant_id, cid)
            if sp is not None:
                return sp
    return None


def _concept_scope_label(db: Session, concept_id: int) -> str | None:
    """« Portée Univers » (définition commune) vs « Portée Espace » (surcharge locale)."""
    scopes = db.execute(
        select(ConceptDefinition.scope).where(
            ConceptDefinition.concept_id == concept_id,
            ConceptDefinition.status.in_(("candidate", "needs_arbitration", "validated")))
    ).scalars().all()
    if not scopes:
        return None
    return "Portée Espace" if any(s == "space" for s in scopes) else "Portée Univers"


def _space_names(db: Session, tenant_id: int) -> dict[int, str]:
    return {s.id: s.name for s in db.execute(
        select(Space).where(Space.tenant_id == tenant_id)).scalars().all()}


def for_user(db: Session, tenant_id: int, role: str) -> dict:
    """« Pour vous » : les À TRAITER que cet utilisateur peut réellement traiter
    (par capacité), + le fil de SUIVI. Un solo (admin) voit tout."""
    names = _space_names(db, tenant_id)

    def space_label(sid: int | None) -> str:
        return names.get(sid, "Univers") if sid is not None else "Univers"

    todo = db.execute(
        select(WorkItem).where(
            WorkItem.tenant_id == tenant_id, WorkItem.status == "a_traiter")
        .order_by(WorkItem.created_at.desc())
    ).scalars().all()
    to_process = [{
        "id": w.id, "kind": w.kind, "object_type": w.object_type, "object_id": w.object_id,
        "title": w.title, "reason": w.reason,
        "space_id": w.space_id, "space_label": space_label(w.space_id),
        # Portée sémantique (Univers/Espace) — distincte du conteneur (l'espace).
        "scope_label": _concept_scope_label(db, int(w.object_id))
        if w.kind == "concept_arbitration" and w.object_id.isdigit() else None,
        "read": w.read_at is not None,
        "created_at": w.created_at.isoformat() if w.created_at else None,
    } for w in todo if can_act(role, w.required_capability)]

    events = db.execute(
        select(ActivityEvent).where(ActivityEvent.tenant_id == tenant_id)
        .order_by(ActivityEvent.created_at.desc()).limit(15)
    ).scalars().all()
    activity = [{
        "id": e.id, "kind": e.kind, "title": e.title, "detail": e.detail,
        "space_id": e.space_id, "space_label": space_label(e.space_id),
        "read": e.read_at is not None,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    } for e in events]
    return {"to_process": to_process, "to_process_count": len(to_process), "activity": activity}


def mark_read(db: Session, tenant_id: int) -> None:
    """Marque tout comme LU (read_at) — sans jamais toucher au `status` : « Tout
    marquer comme lu » ne vide pas « À traiter »."""
    now = _now()
    for w in db.execute(
        select(WorkItem).where(WorkItem.tenant_id == tenant_id, WorkItem.read_at.is_(None))
    ).scalars().all():
        w.read_at = now
    for e in db.execute(
        select(ActivityEvent).where(ActivityEvent.tenant_id == tenant_id, ActivityEvent.read_at.is_(None))
    ).scalars().all():
        e.read_at = now
    db.flush()
