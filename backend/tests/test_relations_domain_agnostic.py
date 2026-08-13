"""Protection ANTI-RETAIL du moteur de relations.

Le même code doit évaluer et valider une relation Retail (« sales.article_reference
→ articles.reference ») et une relation SaaS (« subscriptions.account_id →
accounts.id ») : couverture, unicité cible, exceptions, cardinalité, alternatives,
fenêtre, preview métier, validation. Aucun `if retail`, aucun nom métier dans le moteur.
"""
from __future__ import annotations

import re
from datetime import date
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.core.db import Base
from app.models.relation_candidate import RelationCandidate
from app.models.semantic import BusinessConcept, ConceptMapping
from app.models.tenant import Tenant
from app.services import relations as rel

_RETAIL = ("magasin", "paca", "produit", "gamme", "région", "article", "boutique")


class FakeAdapter:
    """Interprète le SQL de couverture/unicité et TRACE les tables interrogées."""

    def __init__(self, left_table, right_table, nums):
        self.lt, self.rt, self.n = left_table.lower(), right_table.lower(), nums
        self.tables_seen: set[str] = set()

    def run_query(self, sql, connection_id=None):
        low = sql.lower()
        for m in re.findall(r"from (\w+)", low):
            self.tables_seen.add(m)
        if "count(distinct" in low:
            v = self.n["r_distinct"]
        elif "in (select" in low:
            v = self.n["matched"]
        else:
            first = re.search(r"from (\w+)", low)
            t = first.group(1) if first else ""
            v = self.n["total"] if t == self.lt else self.n["r_total"]
        return SimpleNamespace(rows=[[v]], guarded_sql=sql)


@pytest.fixture()
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[
        Tenant.__table__, BusinessConcept.__table__, ConceptMapping.__table__,
        RelationCandidate.__table__,
    ])
    s = sessionmaker(bind=engine)()
    s.add(Tenant(id=1, name="Acme", slug="acme")); s.flush()
    yield s
    s.close()


# Faits identiques quel que soit le domaine : couverture 99,8 %, cible unique.
_NUMS = {"total": 1000, "matched": 998, "r_total": 500, "r_distinct": 500}


@pytest.mark.parametrize("lt,lc,rt,rc", [
    ("sales", "article_reference", "articles", "reference"),          # Retail
    ("subscriptions", "account_id", "accounts", "id"),                # SaaS
])
def test_same_engine_evaluates_any_domain(lt, lc, rt, rc):
    adapter = FakeAdapter(lt, rt, _NUMS)
    facts = rel.evaluate(adapter, 1, {"table": lt, "column": lc}, {"table": rt, "column": rc})
    assert round(facts["coverage"], 3) == 0.998
    assert facts["target_uniqueness"] == 1.0
    assert facts["exceptions_count"] == 2
    assert facts["cardinality"] == "n-1"
    # Le moteur n'a interrogé QUE les tables du candidat — jamais une table retail.
    assert adapter.tables_seen == {lt, rt}


def _concept(db, name, table, column):
    c = BusinessConcept(tenant_id=1, name=name, description="", origin="system")
    db.add(c); db.flush()
    db.add(ConceptMapping(tenant_id=1, connection_id=1, concept_id=c.id,
           schema_name="public", table_name=table, column_name=column))
    db.flush()


def test_saas_preview_from_real_concepts_no_retail(db):
    # Concepts SaaS mappés aux deux tables → le preview en dérive, sans phrase codée.
    _concept(db, "MRR", "subscriptions", "amount")
    _concept(db, "Abonnement actif", "subscriptions", "status")
    _concept(db, "Client actif", "accounts", "id")
    r = RelationCandidate(tenant_id=1, connection_id=1,
        left_table="subscriptions", left_column="account_id",
        right_table="accounts", right_column="id", cardinality="n-1",
        coverage=0.998, target_uniqueness=1.0, type_compatibility="conforme",
        exceptions_count=2, origin="inferred", status="needs_validation")
    db.add(r); db.flush()

    pv = rel.preview(db, r)
    assert pv["analyses_possible"] == 2      # 2 concepts à gauche × 1 à droite
    assert pv["concepts_linkable"] == 3
    blob = " ".join(pv["examples"] + pv["linkable_labels"]).lower()
    assert "mrr" in blob and "client actif" in blob
    for term in _RETAIL:
        assert term not in blob


def test_validate_freezes_window_and_evidence(db):
    r = RelationCandidate(tenant_id=1, connection_id=1,
        left_table="subscriptions", left_column="account_id",
        right_table="accounts", right_column="id", cardinality="n-1",
        coverage=0.998, target_uniqueness=1.0, type_compatibility="conforme",
        exceptions_count=2, origin="inferred", status="needs_validation",
        valid_from=date(2021, 3, 1))
    db.add(r); db.flush()
    rel.validate(db, r, actor="Analyste")
    assert r.status == "validated" and r.validated_by == "Analyste"
    assert r.validation_window["from"] == "2021-03-01" and r.validation_window["to"]
    # L'evidence fige les faits (auditable a posteriori), y compris l'origine.
    assert r.evidence["coverage"] == 0.998 and r.evidence["origin"] == "inferred"


def test_stale_relation_blocks_validation(db):
    r = RelationCandidate(tenant_id=1, connection_id=1,
        left_table="a", left_column="x", right_table="b", right_column="id",
        coverage=0.99, status="needs_validation", source_ids=[7], snapshot_id="snap_OLD")
    db.add(r); db.flush()
    orig = rel._current_snapshot_id
    rel._current_snapshot_id = lambda _db, cid: "snap_now"
    try:
        assert rel.is_stale(db, r)   # snapshot courant ≠ celui évalué
    finally:
        rel._current_snapshot_id = orig


def test_relations_engine_has_no_domain_literal():
    import inspect
    src = inspect.getsource(rel).lower()
    for term in ("magasin", "paca", "directeur", "gamme de produits", "high-tech"):
        assert term not in src
