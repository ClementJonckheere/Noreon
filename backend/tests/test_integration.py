"""Tests d'intégration bout-en-bout sur la base source réelle noreon_demo.

Couvre : connexion + vérification read-only (Module 1), scan + FK implicites
(Module 2), profilage + PII (Module 3), chat NL→SQL + garde-fous + confiance
(Modules 7/8/10). Nécessite la base de démo (scripts/setup_demo.sh) et la base
interne migrée.
"""
from __future__ import annotations

import pytest

from app.core.db import SessionLocal
from app.models.schema_catalog import DbRelation
from app.models.tenant import Tenant, TenantSettings
from app.services import chat as chat_svc
from app.services import connections as conn_svc
from app.services import scanner
from app.services.profiler import persist_profiles, profile_table
from app.services.schema_context import current_snapshot
from sqlalchemy import select

from tests.conftest import DEMO, demo_required

pytestmark = demo_required


@pytest.fixture
def session_with_conn():
    db = SessionLocal()
    tenant = Tenant(slug="itest", name="Itest")
    tenant.settings = TenantSettings(tenant=tenant)
    db.add(tenant)
    db.flush()
    conn, probe = conn_svc.create_connection(
        db, tenant_id=tenant.id, name="demo", host=DEMO["host"], port=DEMO["port"],
        database=DEMO["database"], username=DEMO["username"], password=DEMO["password"],
    )
    db.flush()
    try:
        yield db, conn, probe
    finally:
        db.rollback()
        db.close()


def test_connection_is_read_only(session_with_conn):
    _, _, probe = session_with_conn
    assert probe["connection_ok"] is True
    assert probe["read_only"] is True


def test_scan_detects_tables_and_implicit_fk(session_with_conn):
    db, conn, _ = session_with_conn
    cfg = conn_svc.source_config(conn)
    snapshot, changed = scanner.scan_and_persist(db, conn, cfg)
    assert changed is True
    assert snapshot.table_count >= 6

    relations = db.execute(
        select(DbRelation).where(DbRelation.snapshot_id == snapshot.id)
    ).scalars().all()
    kinds = {(r.from_table, r.from_column, r.to_table, r.kind) for r in relations}
    # FK déclarée orders.customer_id -> customers
    assert any(t == "orders" and c == "customer_id" and k == "declared" for (t, c, _tt, k) in kinds)
    # FK IMPLICITE customers.store_id -> stores (non déclarée en base)
    assert any(
        r.from_table == "customers" and r.from_column == "store_id"
        and r.to_table == "stores" and r.kind == "inferred"
        for r in relations
    )


def test_profiling_computes_stats_and_pii(session_with_conn):
    db, conn, _ = session_with_conn
    cfg = conn_svc.source_config(conn)
    snapshot, _ = scanner.scan_and_persist(db, conn, cfg)
    tables = {t.table_name: t for t in snapshot.tables}
    customers = tables["customers"]
    columns = sorted(customers.columns, key=lambda c: c.ordinal)

    profiles = profile_table(cfg, customers, columns)
    persist_profiles(db, conn, customers, profiles)
    by_col = {p.column_name: p for p in profiles}

    # email : ~1/13 de NULL + détection PII
    assert by_col["email"].null_rate is not None and by_col["email"].null_rate > 0
    assert by_col["email"].pii_type == "email"
    # loyalty_points : colonne numérique, distinct > 1
    assert by_col["loyalty_points"].distinct_count and by_col["loyalty_points"].distinct_count > 1
    # id : clé primaire, aucun NULL
    assert by_col["id"].null_rate == 0


def test_chat_count_end_to_end(session_with_conn):
    db, conn, _ = session_with_conn
    cfg = conn_svc.source_config(conn)
    scanner.scan_and_persist(db, conn, cfg)

    resp = chat_svc.answer_question(db, conn, "Combien de clients ?")
    assert resp.status == "answered"
    assert "count(*)" in resp.sql.lower()
    assert resp.row_count == 1
    assert resp.rows[0][0] == 500
    assert resp.confidence is not None
    assert 0 <= resp.confidence["score"] <= 1
    assert resp.confidence["factors"]  # jamais décoratif


def test_chat_blocks_write_attempt(session_with_conn):
    db, conn, _ = session_with_conn
    cfg = conn_svc.source_config(conn)
    scanner.scan_and_persist(db, conn, cfg)

    # On force un SQL d'écriture via le garde-fou directement (le LLM ne doit
    # jamais en produire, mais la défense en profondeur doit bloquer).
    from app.services.executor import run_query
    from app.services.sql_guard import SQLGuardError

    with pytest.raises(SQLGuardError):
        run_query(cfg, "DELETE FROM customers", connection_id=conn.id)


def test_chat_clarification_on_unknown(session_with_conn):
    db, conn, _ = session_with_conn
    cfg = conn_svc.source_config(conn)
    scanner.scan_and_persist(db, conn, cfg)

    resp = chat_svc.answer_question(db, conn, "Quel est le taux de désabonnement SaaS mensuel ?")
    assert resp.status == "clarification"
    assert resp.message


def _profile_all(db, conn, cfg, snapshot):
    from sqlalchemy import select as _select

    from app.models.schema_catalog import DbColumn
    from app.services.profiler import persist_profiles, profile_table

    for t in snapshot.tables:
        if t.table_type != "table":
            continue
        cols = db.execute(
            _select(DbColumn).where(DbColumn.table_id == t.id).order_by(DbColumn.ordinal)
        ).scalars().all()
        persist_profiles(db, conn, t, profile_table(cfg, t, cols))


def test_quality_scores_are_auditable(session_with_conn):
    from app.services import quality as quality_svc

    db, conn, _ = session_with_conn
    cfg = conn_svc.source_config(conn)
    snapshot, _ = scanner.scan_and_persist(db, conn, cfg)
    _profile_all(db, conn, cfg, snapshot)

    summary = quality_svc.run_quality(db, conn, cfg)
    assert 0 < summary["base_score"] <= 1
    assert summary["columns_scored"] > 0
    assert summary["relations_scored"] > 0

    # Validité : les emails volontairement invalides doivent faire chuter la validité.
    from app.models.quality import QualityScore
    from sqlalchemy import select as _select

    email_q = db.execute(
        _select(QualityScore).where(
            QualityScore.connection_id == conn.id,
            QualityScore.level == "column",
            QualityScore.table_name == "customers",
            QualityScore.column_name == "email",
        )
    ).scalar_one()
    validity = next(d for d in email_q.dimensions if d["name"] == "Validité")
    assert validity["applicable"] is True
    assert validity["score"] < 1.0  # emails 'pas-un-email' détectés

    # Cohérence : store_id orphelins → intégrité < 100% sur au moins une relation.
    relations = db.execute(
        _select(QualityScore).where(
            QualityScore.connection_id == conn.id, QualityScore.level == "relation"
        )
    ).scalars().all()
    assert any(r.score < 1.0 for r in relations)

    # Un score de table et le score base existent.
    assert quality_svc.table_scores_map(db, conn.id)


def test_semantic_loop_and_memory(session_with_conn):
    from sqlalchemy import select as _select

    from app.models.semantic import BusinessConcept, ConceptMapping
    from app.services import semantic as semantic_svc

    db, conn, _ = session_with_conn
    cfg = conn_svc.source_config(conn)
    snapshot, _ = scanner.scan_and_persist(db, conn, cfg)
    _profile_all(db, conn, cfg, snapshot)

    # 1) Propositions générées, jamais auto-validées.
    summary = semantic_svc.propose_and_persist(db, conn)
    assert summary["proposed"] > 0
    mappings = db.execute(
        _select(ConceptMapping).where(ConceptMapping.connection_id == conn.id)
    ).scalars().all()
    assert mappings and all(m.status == "proposed" for m in mappings)

    # 2) Piège sémantique : net_price (HT) vs amount_ttc (TTC) → arbitrage.
    flagged = [m for m in mappings if m.needs_arbitration]
    flagged_cols = {m.column_name for m in flagged}
    assert {"net_price", "amount_ttc"} <= flagged_cols

    # 3) Boucle humaine : on valide le mapping email → il devient une vérité.
    email_m = next(m for m in mappings if m.column_name == "email")
    email_m.status = "validated"
    db.flush()

    # 4) Mémoire entreprise : une re-proposition n'écrase pas la décision.
    summary2 = semantic_svc.propose_and_persist(db, conn)
    assert summary2["kept_human_decisions"] >= 1
    db.refresh(email_m)
    assert email_m.status == "validated"

    # 5) Le dictionnaire validé alimente le contexte du chat.
    text, syns = semantic_svc.validated_concepts_context(db, conn.id)
    assert "Concept Email" in text
    assert "customers" in syns


def test_chat_uses_validated_concept_synonym(session_with_conn):
    from sqlalchemy import select as _select

    from app.models.semantic import BusinessConcept, ConceptMapping
    from app.services import semantic as semantic_svc

    db, conn, _ = session_with_conn
    cfg = conn_svc.source_config(conn)
    snapshot, _ = scanner.scan_and_persist(db, conn, cfg)
    _profile_all(db, conn, cfg, snapshot)
    semantic_svc.propose_and_persist(db, conn)

    # « adhérent » : vocabulaire propre à l'entreprise, inconnu du lexique.
    concept = semantic_svc._get_or_create_concept(db, conn.tenant_id, "Adhérent")
    concept.synonyms = ["adherent", "adherents"]
    mapping = db.execute(
        _select(ConceptMapping).where(
            ConceptMapping.connection_id == conn.id,
            ConceptMapping.table_name == "customers",
            ConceptMapping.column_name == "id",
        )
    ).scalars().first()
    assert mapping is not None
    mapping.concept_id = concept.id
    mapping.status = "corrected"
    db.flush()

    resp = chat_svc.answer_question(db, conn, "Combien d'adhérents ?")
    assert resp.status == "answered"
    assert "public.customers" in resp.sql
    assert resp.rows[0][0] == 500
    # L'indice de confiance mentionne les concepts validés.
    assert any("concept" in f for f in resp.confidence["factors"])


def test_knowledge_graph(session_with_conn):
    from app.services import quality as quality_svc
    from app.services.graph import build_graph

    db, conn, _ = session_with_conn
    cfg = conn_svc.source_config(conn)
    snapshot, _ = scanner.scan_and_persist(db, conn, cfg)
    _profile_all(db, conn, cfg, snapshot)
    quality_svc.run_quality(db, conn, cfg)

    graph = build_graph(db, conn)
    names = {n["name"] for n in graph["nodes"]}
    assert {"customers", "orders", "stores"} <= names

    # Chaque nœud profilé porte son score qualité et sa volumétrie.
    customers = next(n for n in graph["nodes"] if n["name"] == "customers")
    assert customers["quality"] is not None and customers["rows"]

    # Chaque relation est documentée : source, cardinalité, intégrité.
    edges = graph["edges"]
    assert edges
    inferred = next(
        e for e in edges
        if e["from"].endswith("customers") and e["from_column"] == "store_id"
    )
    assert inferred["kind"] == "inferred"
    assert inferred["cardinality"] == "n-1"
    assert inferred["integrity_ratio"] is not None and inferred["integrity_ratio"] < 1.0

    # payments.order_id : une commande a au plus un paiement dans la démo ? Non —
    # on vérifie simplement qu'une cardinalité est mesurée partout où l'intégrité l'est.
    assert all(e["cardinality"] for e in edges if e["integrity_ratio"] is not None)


def test_rejected_relation_leaves_sql_context(session_with_conn):
    from sqlalchemy import select as _select

    from app.models.schema_catalog import DbRelation
    from app.services.schema_context import build_context

    db, conn, _ = session_with_conn
    cfg = conn_svc.source_config(conn)
    snapshot, _ = scanner.scan_and_persist(db, conn, cfg)

    rel = db.execute(
        _select(DbRelation).where(
            DbRelation.snapshot_id == snapshot.id, DbRelation.kind == "inferred"
        )
    ).scalars().first()
    assert rel is not None
    ref = f"{rel.from_schema}.{rel.from_table}.{rel.from_column}"
    assert ref in build_context(db, snapshot)
    rel.status = "rejected"
    db.flush()
    assert ref not in build_context(db, snapshot)


def test_chat_privacy_engine_end_to_end(session_with_conn):
    db, conn, _ = session_with_conn
    cfg = conn_svc.source_config(conn)
    snapshot, _ = scanner.scan_and_persist(db, conn, cfg)
    _profile_all(db, conn, cfg, snapshot)

    resp = chat_svc.answer_question(db, conn, "Montre les clients")
    assert resp.status == "answered"
    # L'audit du Privacy Engine expose les colonnes protégées.
    assert resp.privacy is not None
    assert resp.privacy["method"] == "pseudonymisation"
    assert "email" in resp.privacy["protected_columns"]
    # Les lignes AFFICHÉES à l'utilisateur restent réelles (ré-identification
    # locale) : la protection ne concerne que ce qui part au LLM.
    email_idx = resp.columns.index("email")
    real_emails = [r[email_idx] for r in resp.rows if r[email_idx]]
    assert any("@" in str(e) for e in real_emails)
