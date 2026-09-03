"""Cloisonnement des Sources par espace (durcissement).

Une capability ne suffit pas : la liste des sources doit aussi respecter
l'ESPACE. Depuis un espace, `?space_id=` ne renvoie que les sources RÉELLEMENT
rattachées — une source d'un autre espace (ex. « Démo Retail ») est INVISIBLE.
Sans espace, catalogue complet, chaque source portant son badge d'espace.

Ces invariants sont ceux sur lesquels s'appuie la recherche ⌘K (une source de
Démo Retail ne doit pas apparaître depuis CRM).
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.core.db import Base
from app.models.connection import Connection
from app.models.space import Space, SpaceConnection
from app.models.tenant import Tenant
from app.api.routes.connections import list_connections


@pytest.fixture()
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[
        Tenant.__table__, Connection.__table__, Space.__table__, SpaceConnection.__table__,
    ])
    s = sessionmaker(bind=engine)()
    s.add(Tenant(id=1, name="Acme", slug="acme")); s.flush()
    yield s
    s.close()


def _conn(db, name: str) -> Connection:
    c = Connection(
        tenant_id=1, name=name, engine="postgresql", host="h", port=5432,
        database="d", username="u", secret_encrypted="x", options={},
        created_at=datetime.now(timezone.utc),
    )
    db.add(c); db.flush()
    return c


@pytest.fixture()
def world(db):
    crm = Space(tenant_id=1, name="CRM", slug="crm"); db.add(crm)
    retail = Space(tenant_id=1, name="Démo Retail", slug="demo-retail"); db.add(retail)
    db.flush()
    crm_src = _conn(db, "Source CRM")
    retail_src = _conn(db, "Source Retail")
    orphan = _conn(db, "Source non rattachée")
    db.add(SpaceConnection(space_id=crm.id, connection_id=crm_src.id))
    db.add(SpaceConnection(space_id=retail.id, connection_id=retail_src.id))
    db.flush()
    return crm, retail, crm_src, retail_src, orphan


def _tenant(db) -> Tenant:
    return db.get(Tenant, 1)


def test_space_scope_hides_other_spaces(db, world):
    crm, retail, crm_src, retail_src, orphan = world
    got = list_connections(space_id=crm.id, db=db, tenant=_tenant(db))
    names = {c.name for c in got}
    assert names == {"Source CRM"}
    # La source de Démo Retail est INVISIBLE depuis CRM (base de ⌘K item 4).
    assert "Source Retail" not in names
    # La source non rattachée n'apparaît dans AUCUN espace.
    assert "Source non rattachée" not in names
    assert got[0].spaces == ["CRM"]


def test_other_space_is_symmetric(db, world):
    crm, retail, *_ = world
    got = list_connections(space_id=retail.id, db=db, tenant=_tenant(db))
    assert {c.name for c in got} == {"Source Retail"}


def test_global_catalog_labels_every_space(db, world):
    got = list_connections(space_id=None, db=db, tenant=_tenant(db))
    by_name = {c.name: c.spaces for c in got}
    assert set(by_name) == {"Source CRM", "Source Retail", "Source non rattachée"}
    assert by_name["Source CRM"] == ["CRM"]
    assert by_name["Source Retail"] == ["Démo Retail"]
    # Non rattachée = liste vide (jamais confondue avec « appartient à l'espace »).
    assert by_name["Source non rattachée"] == []
