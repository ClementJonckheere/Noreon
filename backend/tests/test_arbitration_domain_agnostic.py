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
from app.models.concept_arbitration import ConceptArbitration, ConceptReference
from app.models.concept_definition import ConceptDefinition
from app.models.semantic import BusinessConcept
from app.models.tenant import Tenant
from app.services import arbitration, propagation

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
        ConceptReference.__table__, ConceptArbitration.__table__,
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

    # Registre de propagation (E1) : réponses, découverte, rapport figé.
    for kind, immutable in [("answer", False), ("answer", False), ("discovery", False),
                            ("report", True)]:
        db.add(ConceptReference(tenant_id=1, concept_id=concept.id, kind=kind,
               ref_label="v4" if kind == "report" else "", immutable=immutable))
    db.add(ConceptReference(tenant_id=1, concept_id=999, kind="answer"))  # autre concept
    db.flush()

    # Preview d'arbitrage AVANT toute mutation (rule 2) — buckets génériques.
    b_id = next(i.definition_id for i in impacts if i.label == "B")
    prev = arbitration.arbitration_preview(db, concept.id, b_id)
    assert prev["propagation"]["answers_affected"] == 2
    assert prev["propagation"]["discoveries_to_recheck"] == 1
    assert prev["propagation"]["reports_preserved"] == 1
    assert prev["new_version"] == 2 and prev["creates_new_version"]
    # Rien n'a été muté par le preview.
    assert arbitration.is_ambiguous(db, concept.id)

    # Arbitrage TRANSACTIONNEL : B devient référence ; A/C archivées ; version +1 ;
    # audit écrit ; propagation E1 exécutée sur le registre.
    res = arbitration.arbitrate(db, concept.id, b_id, actor="Responsable produit")
    chosen = res["chosen"]
    assert chosen.is_reference and chosen.status == "validated" and chosen.definition_version == 2
    others = [d for d in arbitration.definitions_of(db, concept.id, include_archived=True)
              if d.id != b_id]
    assert all(not d.is_reference and d.status == "archived" for d in others)
    assert not arbitration.is_ambiguous(db, concept.id)
    # E1 : réponses → stale, découverte → en_reverification, rapport figé → preserved.
    refs = propagation.references_for(db, concept.id)
    assert {r.status for r in refs if r.kind == "answer"} == {"stale"}
    assert [r.status for r in refs if r.kind == "discovery"] == ["en_reverification"]
    assert [r.status for r in refs if r.kind == "report"] == ["preserved"]
    # Audit d'arbitrage écrit.
    audit = db.query(ConceptArbitration).filter_by(concept_id=concept.id).all()
    assert len(audit) == 1 and audit[0].definition_version == 2


def _seed_named(db, name: str, entity_label: str, counts: dict) -> BusinessConcept:
    concept = BusinessConcept(tenant_id=1, name=name, description="", origin="system")
    db.add(concept); db.flush()
    for label, cnt in counts.items():
        db.add(ConceptDefinition(tenant_id=1, concept_id=concept.id, scope="universe",
               label=label, definition_text=f"définition {label}", entity_label=entity_label,
               impact_count=cnt, status="needs_arbitration"))
    for kind in ("answer", "answer", "discovery", "report"):
        db.add(ConceptReference(tenant_id=1, concept_id=concept.id, kind=kind,
               immutable=(kind == "report")))
    db.flush()
    return concept


def test_same_machine_retail_and_saas(db):
    """La MÊME machine arbitre « Magasin actif » (Démo Retail) et « Client actif »
    (SaaS) à l'identique — aucune branche métier, aucune isolation cassée."""
    db.add(Tenant(id=1, name="Acme", slug="acme")); db.flush()
    retail = _seed_named(db, "Magasin actif", "magasins", {"A": 58, "B": 61, "C": 54})
    saas = _seed_named(db, "Client actif", "clients", {"A": 4218, "B": 6032})

    for concept in (retail, saas):
        assert arbitration.is_ambiguous(db, concept.id)
        defs = arbitration.definitions_of(db, concept.id)
        chosen = defs[-1]
        prev = arbitration.arbitration_preview(db, concept.id, chosen.id)
        # Preview identique en structure quel que soit le domaine.
        assert prev["propagation"]["answers_affected"] == 2
        assert prev["propagation"]["reports_preserved"] == 1
        res = arbitration.arbitrate(db, concept.id, chosen.id, actor="Analyste")
        assert res["chosen"].is_reference and res["version"] == 2
        assert not arbitration.is_ambiguous(db, concept.id)

    # Isolation : arbitrer l'un n'a rien touché aux références de l'autre concept.
    r_refs = propagation.references_for(db, retail.id)
    s_refs = propagation.references_for(db, saas.id)
    assert all(r.concept_id == retail.id for r in r_refs)
    assert all(r.concept_id == saas.id for r in s_refs)
    # Le libellé d'entité reste celui des données (magasins vs clients), jamais figé.
    assert {d.entity_label for d in arbitration.definitions_of(db, retail.id, include_archived=True)} == {"magasins"}
    assert {d.entity_label for d in arbitration.definitions_of(db, saas.id, include_archived=True)} == {"clients"}


def test_universe_space_scope_inheritance(db):
    """Univers = définition commune ; un espace HÉRITE, sauf s'il SURCHARGE."""
    db.add(Tenant(id=1, name="Acme", slug="acme")); db.flush()
    concept = BusinessConcept(tenant_id=1, name="Client actif", description="", origin="system")
    db.add(concept); db.flush()
    # Univers : deux définitions concurrentes.
    for label in ("U-A", "U-B"):
        db.add(ConceptDefinition(tenant_id=1, concept_id=concept.id, scope="universe",
               label=label, definition_text="", entity_label="clients", status="needs_arbitration"))
    db.flush()
    SPACE = 42
    # Un espace SANS override hérite de l'Univers (mêmes définitions).
    inherited = arbitration.definitions_of(db, concept.id, space_id=SPACE)
    assert {d.label for d in inherited} == {"U-A", "U-B"}
    assert arbitration.effective_scope(db, concept.id, SPACE) == "universe"

    # L'espace SURCHARGE avec sa propre définition → elle PRIME, l'Univers est masqué.
    db.add(ConceptDefinition(tenant_id=1, concept_id=concept.id, scope="space", space_id=SPACE,
           label="S-only", definition_text="propre à cet espace", entity_label="clients",
           status="validated", is_reference=True, definition_version=1))
    db.flush()
    override = arbitration.definitions_of(db, concept.id, space_id=SPACE)
    assert {d.label for d in override} == {"S-only"}
    assert arbitration.effective_scope(db, concept.id, SPACE) == "space"
    # Un AUTRE espace, lui, hérite toujours de l'Univers (isolation des overrides).
    assert {d.label for d in arbitration.definitions_of(db, concept.id, space_id=99)} == {"U-A", "U-B"}
    # La vue Univers reste inchangée.
    assert {d.label for d in arbitration.definitions_of(db, concept.id)} == {"U-A", "U-B"}


def test_stale_impact_blocks_arbitration(db):
    """Un impact obsolète (snapshot changé) bloque l'arbitrage : recalcul requis."""
    db.add(Tenant(id=1, name="Acme", slug="acme")); db.flush()
    concept = BusinessConcept(tenant_id=1, name="Commande valide", description="", origin="system")
    db.add(concept); db.flush()
    for label, snap in (("A", "snap_now"), ("B", "snap_OLD")):
        db.add(ConceptDefinition(tenant_id=1, concept_id=concept.id, scope="universe",
               label=label, definition_text="", entity_label="commandes", impact_count=10,
               status="needs_arbitration", source_ids=[7], snapshot_id=snap))
    db.flush()

    # Le snapshot COURANT de la source 7 = « snap_now » : B (snap_OLD) est obsolète.
    import app.services.arbitration as arb
    orig = arb._current_snapshot_id
    arb._current_snapshot_id = lambda _db, cid: "snap_now"
    try:
        b = next(d for d in arbitration.definitions_of(db, concept.id) if d.label == "B")
        a = next(d for d in arbitration.definitions_of(db, concept.id) if d.label == "A")
        assert arbitration.is_stale(db, b) and not arbitration.is_stale(db, a)
        with pytest.raises(arbitration.StaleImpactError):
            arbitration.arbitrate(db, concept.id, b.id, actor="X")
        # Après recalcul, l'obsolescence est levée → l'arbitrage passe.
        arbitration.recompute_impact(db, b)
        assert not arbitration.is_stale(db, b)
        res = arbitration.arbitrate(db, concept.id, b.id, actor="X")
        assert res["chosen"].is_reference
    finally:
        arb._current_snapshot_id = orig


def test_arbitration_engine_has_no_domain_enum():
    """Le moteur ne doit contenir ni enum de concepts ni branche métier codée en dur."""
    import inspect
    src = inspect.getsource(arbitration).lower()
    # Aucune primitive de LOGIQUE retail : pas de comparaison à un concept nommé.
    for forbidden in ("== \"magasin", "== 'magasin", "active_store", "product_family",
                      "if concept ==", "paca", "high-tech"):
        assert forbidden not in src
