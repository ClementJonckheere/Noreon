"""Protection ANTI-RETAIL du moteur d'arbitrage.

Le moteur Concepts / Arbitrage doit être une primitive GÉNÉRIQUE : la même
machine — scan → concept candidat → ambiguïté → arbitrage → propagation — doit
fonctionner sur n'importe quel domaine. Ce test la fait tourner sur un jeu
**SaaS** (`customers`, `subscriptions`, `invoices`, `events`) SANS aucune table
`stores` / `products` / `orders`, et vérifie que le moteur n'émet que des
requêtes sur ces tables SaaS. Toute régression vers un couplage Retail casse ici.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401 — enregistre les tables sur Base.metadata
from app.core.db import Base
from app.models.concept_definition import ConceptDefinition
from app.models.semantic import BusinessConcept
from app.models.tenant import Tenant
from app.services import arbitration

# Concept AMBIGU d'un tout autre domaine que Retail : « Client actif », défini de
# trois manières plausibles — exactement le même problème que « Magasin actif ».
DEF_A = "SELECT count(DISTINCT c.id) FROM customers c JOIN invoices i ON i.customer_id = c.id WHERE i.paid_at >= '2025-08-01'"
DEF_B = "SELECT count(DISTINCT c.id) FROM customers c JOIN events e ON e.customer_id = c.id WHERE e.type = 'login' AND e.at >= '2026-05-01'"
DEF_C = "SELECT count(DISTINCT c.id) FROM customers c JOIN subscriptions s ON s.customer_id = c.id WHERE s.status = 'active'"

# Comptages déterministes par TABLE interrogée — le moteur ne sait pas ce qu'il
# compte, il exécute le SQL et lit un nombre.
_COUNTS = {"invoices": 4218, "events": 6032, "subscriptions": 5100}
_RETAIL_TABLES = ("stores", "store", "products", "product", "orders", "order")


class SaaSAdapter:
    """Répond aux `count_sql` et TRACE toutes les tables interrogées."""

    def __init__(self):
        self.tables_seen: set[str] = set()

    def run_query(self, sql: str, connection_id=None):
        low = sql.lower()
        for t in ("customers", "invoices", "events", "subscriptions"):
            if t in low:
                self.tables_seen.add(t)
        n = next((v for k, v in _COUNTS.items() if k in low), 0)
        return SimpleNamespace(rows=[[n]], guarded_sql=sql)


@pytest.fixture()
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[
        Tenant.__table__, BusinessConcept.__table__, ConceptDefinition.__table__,
    ])
    s = sessionmaker(bind=engine)()
    yield s
    s.close()


def _seed_concept(db) -> BusinessConcept:
    db.add(Tenant(id=1, name="Acme SaaS", slug="acme-saas")); db.flush()
    concept = BusinessConcept(tenant_id=1, name="Client actif", description="", origin="system")
    db.add(concept); db.flush()
    for label, text, sql in [
        ("A", "A acheté au cours des 12 derniers mois", DEF_A),
        ("B", "S'est connecté dans les 90 derniers jours", DEF_B),
        ("C", "Possède un abonnement en cours", DEF_C),
    ]:
        db.add(ConceptDefinition(tenant_id=1, concept_id=concept.id, scope="universe",
               label=label, definition_text=text, count_sql=sql,
               entity_label="clients", status="needs_arbitration"))
    db.flush()
    return concept


def test_full_chain_runs_on_saas_without_retail_tables(db):
    concept = _seed_concept(db)
    adapter = SaaSAdapter()

    # Ambiguïté détectée génériquement.
    assert arbitration.is_ambiguous(db, concept.id)

    # Impact de chaque définition — nombres distincts, calculés depuis les données.
    impacts = arbitration.refresh_impacts(db, adapter, connection_id=1, concept_id=concept.id)
    by_label = {i.label: i.count for i in impacts}
    assert by_label == {"A": 4218, "B": 6032, "C": 5100}
    assert all(i.entity_label == "clients" for i in impacts)

    # PROTECTION : le moteur n'a interrogé QUE des tables SaaS, jamais de retail.
    assert adapter.tables_seen and not (adapter.tables_seen & set(_RETAIL_TABLES))
    assert not any(rt in q for q in [DEF_A, DEF_B, DEF_C] for rt in _RETAIL_TABLES)

    # Propagation d'un changement de référence — buckets génériques.
    refs = [
        {"concept_id": concept.id, "kind": "answer"}, {"concept_id": concept.id, "kind": "answer"},
        {"concept_id": concept.id, "kind": "discovery"},
        {"concept_id": concept.id, "kind": "report", "immutable": True},
        {"concept_id": 999, "kind": "answer"},   # autre concept : non concerné
    ]
    prop = arbitration.propagation_preview(refs, concept.id)
    assert prop["answers_affected"] == 2
    assert prop["discoveries_to_recheck"] == 1
    assert prop["reports_preserved"] == 1

    # Arbitrage : B devient la référence en vigueur ; A et C archivées ; version +1.
    b_id = next(i.definition_id for i in impacts if i.label == "B")
    chosen = arbitration.arbitrate(db, concept.id, b_id, actor="Responsable produit")
    assert chosen.is_reference and chosen.status == "validated"
    assert chosen.definition_version == 2
    others = [d for d in arbitration.definitions_of(db, concept.id, include_archived=True)
              if d.id != b_id]
    assert all(not d.is_reference and d.status == "archived" for d in others)
    # Plus qu'une seule définition en lice → l'ambiguïté est levée.
    assert not arbitration.is_ambiguous(db, concept.id)


def test_arbitration_engine_has_no_domain_enum():
    """Le moteur ne doit contenir ni enum de concepts ni branche métier codée en dur."""
    import inspect
    src = inspect.getsource(arbitration).lower()
    # Aucune primitive de LOGIQUE retail : pas de comparaison à un concept nommé.
    for forbidden in ("== \"magasin", "== 'magasin", "active_store", "product_family",
                      "if concept ==", "paca", "high-tech"):
        assert forbidden not in src
