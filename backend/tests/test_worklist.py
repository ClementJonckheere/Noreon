"""Invariants VERROUILLÉS de la worklist (Notifications).

- Les WorkItems dérivent de l'état RÉEL (concept ambigu, relation à valider…).
- LECTURE ≠ RÉSOLUTION : « tout marquer comme lu » ne vide jamais « À traiter ».
- Un WorkItem n'est résolu que lorsque l'objet atteint réellement l'état attendu.
- Assignation par CAPABILITY : un lecteur ne voit pas ce qu'il ne peut pas traiter.
- Aucun vocabulaire métier dans le moteur.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.core.db import Base
from app.models.concept_definition import ConceptDefinition
from app.models.decision import DecisionRecord
from app.models.measurement import MeasurementPlan, MeasurementRun
from app.models.relation_candidate import RelationCandidate
from app.models.semantic import BusinessConcept
from app.models.space import Space, SpaceConnection
from app.models.tenant import Tenant
from app.models.user import ROLE_ADMIN, ROLE_READER
from app.models.work_item import ActivityEvent, WorkItem
from app.services import worklist


@pytest.fixture()
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[
        Tenant.__table__, Space.__table__, SpaceConnection.__table__,
        BusinessConcept.__table__, ConceptDefinition.__table__,
        RelationCandidate.__table__, DecisionRecord.__table__,
        MeasurementPlan.__table__, MeasurementRun.__table__,
        WorkItem.__table__, ActivityEvent.__table__,
    ])
    s = sessionmaker(bind=engine)()
    s.add(Tenant(id=1, name="Acme", slug="acme")); s.flush()
    yield s
    s.close()


def _seed_two_triggers(db):
    # Concept ambigu (2 définitions en lice) → arbitrage nécessaire.
    c = BusinessConcept(tenant_id=1, name="Client actif", description="", origin="system")
    db.add(c); db.flush()
    for label in ("A", "B"):
        db.add(ConceptDefinition(tenant_id=1, concept_id=c.id, scope="universe",
               label=label, definition_text="", entity_label="clients", status="needs_arbitration"))
    # Relation à valider.
    r = RelationCandidate(tenant_id=1, connection_id=7,
        left_table="subscriptions", left_column="account_id",
        right_table="accounts", right_column="id", exceptions_count=3,
        status="needs_validation")
    db.add(r); db.flush()
    return c, r


def test_reconcile_creates_work_from_real_state(db):
    _seed_two_triggers(db)
    worklist.reconcile(db, 1)
    res = worklist.for_user(db, 1, ROLE_ADMIN)
    kinds = {w["kind"] for w in res["to_process"]}
    assert kinds == {"concept_arbitration", "relation_validation"}
    assert res["to_process_count"] == 2


def test_read_is_not_resolution(db):
    _seed_two_triggers(db)
    worklist.reconcile(db, 1)
    worklist.mark_read(db, 1)
    res = worklist.for_user(db, 1, ROLE_ADMIN)
    # « Tout marquer comme lu » n'enlève RIEN de « À traiter ».
    assert res["to_process_count"] == 2
    assert all(w["read"] for w in res["to_process"])
    # Les WorkItems sont lus mais non résolus.
    assert all(w.read_at is not None and w.status == "a_traiter"
               for w in db.query(WorkItem).all())


def test_workitem_resolves_only_when_object_reaches_state(db):
    _c, r = _seed_two_triggers(db)
    worklist.reconcile(db, 1)
    assert worklist.for_user(db, 1, ROLE_ADMIN)["to_process_count"] == 2

    # L'humain valide réellement la relation → l'objet quitte l'état déclencheur.
    r.status = "validated"
    worklist.reconcile(db, 1)
    res = worklist.for_user(db, 1, ROLE_ADMIN)
    assert res["to_process_count"] == 1
    assert {w["kind"] for w in res["to_process"]} == {"concept_arbitration"}
    wi = db.query(WorkItem).filter(WorkItem.kind == "relation_validation").one()
    assert wi.status == "traite" and wi.resolved_at is not None
    # Un suivi apparaît (relation validée + résolution).
    assert db.query(ActivityEvent).count() >= 1


def test_capability_filter_solo_vs_reader(db):
    _seed_two_triggers(db)
    worklist.reconcile(db, 1)
    # Un entrepreneur seul (admin) possède les capacités → voit tout.
    assert worklist.for_user(db, 1, ROLE_ADMIN)["to_process_count"] == 2
    # Un lecteur ne peut ni arbitrer ni valider → ne reçoit rien à traiter.
    assert worklist.for_user(db, 1, ROLE_READER)["to_process_count"] == 0


def test_worklist_engine_has_no_domain_literal():
    import inspect
    src = inspect.getsource(worklist).lower()
    for term in ("magasin", "paca", "directeur réseau", "boutique", "high-tech", "gamme"):
        assert term not in src
