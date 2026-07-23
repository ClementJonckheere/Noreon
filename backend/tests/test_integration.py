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
    cfg = conn_svc.get_source_adapter(conn)
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
    cfg = conn_svc.get_source_adapter(conn)
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
    cfg = conn_svc.get_source_adapter(conn)
    scanner.scan_and_persist(db, conn, cfg)

    resp = chat_svc.answer_question(db, conn, "Combien de clients ?")
    assert resp.status == "answered"
    assert "count(*)" in resp.sql.lower()
    assert resp.row_count == 1
    assert resp.rows[0][0] == 500
    assert resp.confidence is not None
    assert 0 <= resp.confidence["score"] <= 1
    assert resp.confidence["factors"]  # jamais décoratif
    # Explicabilité : chaque réponse justifie ses choix (au moins la table).
    assert resp.explanations and any("Table" in e for e in resp.explanations)


def test_chat_blocks_write_attempt(session_with_conn):
    db, conn, _ = session_with_conn
    cfg = conn_svc.get_source_adapter(conn)
    scanner.scan_and_persist(db, conn, cfg)

    # On force un SQL d'écriture via le garde-fou directement (le LLM ne doit
    # jamais en produire, mais la défense en profondeur doit bloquer).
    from app.services.sql_guard import SQLGuardError

    with pytest.raises(SQLGuardError):
        cfg.run_query("DELETE FROM customers", connection_id=conn.id)


def test_chat_clarification_on_unknown(session_with_conn):
    db, conn, _ = session_with_conn
    cfg = conn_svc.get_source_adapter(conn)
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
    cfg = conn_svc.get_source_adapter(conn)
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
    cfg = conn_svc.get_source_adapter(conn)
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
    cfg = conn_svc.get_source_adapter(conn)
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
    cfg = conn_svc.get_source_adapter(conn)
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
    # Explicabilité : chaque relation dit EN CLAIR pourquoi elle existe.
    assert inferred["rationale"] and "convention" in inferred["rationale"].lower()

    # payments.order_id : une commande a au plus un paiement dans la démo ? Non —
    # on vérifie simplement qu'une cardinalité est mesurée partout où l'intégrité l'est.
    assert all(e["cardinality"] for e in edges if e["integrity_ratio"] is not None)


def test_rejected_relation_leaves_sql_context(session_with_conn):
    from sqlalchemy import select as _select

    from app.models.schema_catalog import DbRelation
    from app.services.schema_context import build_context

    db, conn, _ = session_with_conn
    cfg = conn_svc.get_source_adapter(conn)
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
    cfg = conn_svc.get_source_adapter(conn)
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


def test_deep_analysis_on_measure_cross_references_age(session_with_conn):
    """Sur « montant des commandes », l'analyste approfondi doit dépasser la
    sortie brute : joindre les clients, découper l'âge en tranches, retrouver
    l'âge comme FACTEUR EXPLICATIF réel (panier moyen croissant) et croiser
    deux dimensions. C'est le cœur de la demande « un vrai data analyst »."""
    db, conn, _ = session_with_conn
    cfg = conn_svc.get_source_adapter(conn)
    snapshot, _ = scanner.scan_and_persist(db, conn, cfg)
    _profile_all(db, conn, cfg, snapshot)

    resp = chat_svc.answer_question(db, conn, "montant total des commandes par mois")
    assert resp.status == "answered"
    deep = resp.deep
    assert deep is not None
    assert deep["subject"] == "orders"
    assert "amount_ttc" in deep["metric_label"]

    # Une dimension issue d'une table LIÉE (clients) doit apparaître : l'analyste
    # est allé chercher « qui achète » au-delà de la table de faits.
    dim_labels = " ".join(s["dimension"] for s in deep["segments"])
    assert "age" in dim_labels and "customers" in dim_labels

    # L'âge est identifié comme un vrai facteur explicatif (gradient de panier),
    # pas un simple total.
    assert any("age" in d and ("facteur explicatif" in d or "influence" in d)
               for d in deep["drivers"])

    # Le panier moyen croît avec la tranche d'âge (driver réel semé dans la démo).
    age_seg = next(s for s in deep["segments"] if "age" in s["dimension"])
    avgs = [g["avg"] for g in age_seg["groups"] if g.get("avg") is not None]
    assert avgs and max(avgs) > min(avgs)

    # Un croisement de deux dimensions est produit + des recommandations métier.
    assert deep["crosstab"] is not None and deep["crosstab"]["cells"]
    assert deep["recommendations"]

    # Les requêtes de suivi sont agrégées (aucune donnée brute identifiante).
    assert deep["queries"] and all("group by" in q.lower() for q in deep["queries"])


def test_deep_analysis_profiles_population_for_count_question(session_with_conn):
    """« Combien de clients » → profil de la population (effectif par âge, ville,
    genre), pas une somme de mesure au hasard."""
    db, conn, _ = session_with_conn
    cfg = conn_svc.get_source_adapter(conn)
    snapshot, _ = scanner.scan_and_persist(db, conn, cfg)
    _profile_all(db, conn, cfg, snapshot)

    resp = chat_svc.answer_question(db, conn, "Combien de clients ?")
    assert resp.deep is not None
    assert resp.deep["subject"] == "customers"
    assert "effectif" in resp.deep["metric_label"]
    dims = " ".join(s["dimension"] for s in resp.deep["segments"])
    assert "age" in dims and "city" in dims


def test_deep_analysis_can_be_disabled(session_with_conn):
    db, conn, _ = session_with_conn
    cfg = conn_svc.get_source_adapter(conn)
    scanner.scan_and_persist(db, conn, cfg)
    resp = chat_svc.answer_question(
        db, conn, "montant total des commandes par mois", deep_analysis=False
    )
    assert resp.status == "answered"
    assert resp.deep is None


def _client_for(db, monkeypatch):
    """Client FastAPI partageant la session de test.

    Les routes appellent `db.commit()` ; en test on l'aliase sur `flush` pour
    rester dans la transaction (rollback au teardown) et ne rien polluer.
    """
    from fastapi.testclient import TestClient

    from app.core.db import get_db
    from app.main import app

    monkeypatch.setattr(db, "commit", db.flush)
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def test_conversations_server_side_history(session_with_conn, monkeypatch):
    db, conn, _ = session_with_conn
    scanner.scan_and_persist(db, conn, conn_svc.get_source_adapter(conn))
    client = _client_for(db, monkeypatch)
    base = f"/connections/{conn.id}/conversations"
    H = {"X-Tenant": "itest"}
    try:
        # Liste vide au départ.
        assert client.get(base, headers=H).json() == []

        # Création d'une conversation + d'un tour (exécute et mémorise la réponse).
        conv = client.post(base, json={}, headers=H).json()
        cid = conv["id"]
        r = client.post(f"{base}/{cid}/turns",
                        json={"question": "Combien de clients ?", "deep_analysis": False},
                        headers=H)
        assert r.status_code == 200
        body = r.json()
        assert body["turn"]["response"]["status"] == "answered"
        assert body["turn"]["response"]["rows"][0][0] == 500
        # Titre auto dérivé de la 1re question.
        assert body["conversation"]["title"].startswith("Combien de clients")

        # Tour approfondi avec des DATES (ventilation par mois) : la réponse
        # doit se sérialiser proprement en JSON (dates → ISO) pour être stockée.
        r2 = client.post(f"{base}/{cid}/turns",
                         json={"question": "Montant total des commandes par mois",
                               "deep_analysis": True},
                         headers=H)
        assert r2.status_code == 200
        assert r2.json()["turn"]["response"]["deep"] is not None

        # Rechargement : le fil est rejouable à l'identique (multi-appareils).
        full = client.get(f"{base}/{cid}", headers=H).json()
        assert len(full["turns"]) == 2
        assert full["turns"][0]["question"] == "Combien de clients ?"
    finally:
        from app.main import app
        app.dependency_overrides.clear()


def test_conversations_folders_and_archive(session_with_conn, monkeypatch):
    db, conn, _ = session_with_conn
    scanner.scan_and_persist(db, conn, conn_svc.get_source_adapter(conn))
    client = _client_for(db, monkeypatch)
    base = f"/connections/{conn.id}/conversations"
    H = {"X-Tenant": "itest"}
    try:
        # Dossier + conversation rangée dedans.
        folder = client.post(f"{base}/folders", json={"name": "Ventes"}, headers=H).json()
        conv = client.post(base, json={"title": "Analyse CA", "folder_id": folder["id"]},
                           headers=H).json()
        assert conv["folder_id"] == folder["id"]

        # Archivage : disparaît de la liste courante, apparaît dans les archivées.
        client.patch(f"{base}/{conv['id']}", json={"archived": True}, headers=H)
        active = client.get(base, headers=H).json()
        assert all(c["id"] != conv["id"] for c in active)
        archived = client.get(f"{base}?archived=true", headers=H).json()
        assert any(c["id"] == conv["id"] for c in archived)

        # Désarchivage + déplacement hors dossier.
        client.patch(f"{base}/{conv['id']}", json={"archived": False, "folder_id": None}, headers=H)
        back = client.get(f"{base}/{conv['id']}", headers=H).json()
        assert back["archived"] is False and back["folder_id"] is None

        # Suppression du dossier : les conversations restantes deviennent sans dossier.
        client.delete(f"{base}/folders/{folder['id']}", headers=H)
        assert client.get(f"{base}/folders", headers=H).json() == []
    finally:
        from app.main import app
        app.dependency_overrides.clear()


def test_space_governance_end_to_end(session_with_conn, monkeypatch):
    """Espace CRM : rattacher une BDD, gouverner les tables/colonnes, et vérifier
    que le chat de l'espace respecte la gouvernance (table masquée → inaccessible)."""
    db, conn, _ = session_with_conn
    scanner.scan_and_persist(db, conn, conn_svc.get_source_adapter(conn))
    client = _client_for(db, monkeypatch)
    H = {"X-Tenant": "itest"}
    try:
        # Création d'un espace + rattachement de la BDD (réservé admin).
        sp = client.post("/spaces", json={"name": "CRM"}, headers=H)
        assert sp.status_code == 200
        sid = sp.json()["id"]
        client.post(f"/spaces/{sid}/connections", json={"connection_id": conn.id}, headers=H)

        base = f"/spaces/{sid}/connections/{conn.id}"
        gov = client.get(f"{base}/governance", headers=H).json()
        assert gov["scanned"] is True
        cust = next(t for t in gov["tables"] if t["table"] == "customers")
        assert cust["enabled"] is True

        # Chat d'espace : fonctionne tant que la table est autorisée.
        ask = {"connection_id": conn.id, "question": "Combien de clients ?", "deep_analysis": False}
        r1 = client.post(f"/spaces/{sid}/chat", json=ask, headers=H).json()
        assert r1["status"] == "answered" and r1["rows"][0][0] == 500

        # Décocher la table customers → masquée pour l'espace.
        client.put(f"{base}/tables/public/customers", json={"enabled": False}, headers=H)
        gov2 = client.get(f"{base}/governance", headers=H).json()
        assert next(t for t in gov2["tables"] if t["table"] == "customers")["enabled"] is False

        # Le chat ne peut plus atteindre customers (retirée du contexte).
        r2 = client.post(f"/spaces/{sid}/chat", json=ask, headers=H).json()
        assert r2["status"] in ("clarification", "blocked")

        # Re-cocher → de nouveau accessible.
        client.put(f"{base}/tables/public/customers", json={"enabled": True}, headers=H)
        r3 = client.post(f"/spaces/{sid}/chat", json=ask, headers=H).json()
        assert r3["status"] == "answered" and r3["rows"][0][0] == 500

        # Gouvernance au niveau colonne : masquer email.
        client.put(f"{base}/columns/public/customers/email", json={"enabled": False}, headers=H)
        gov3 = client.get(f"{base}/governance", headers=H).json()
        cust3 = next(t for t in gov3["tables"] if t["table"] == "customers")
        assert next(c for c in cust3["columns"] if c["name"] == "email")["enabled"] is False
    finally:
        from app.main import app
        app.dependency_overrides.clear()


def test_discoveries_proactive(session_with_conn, monkeypatch):
    """À l'ouverture, l'analyste proactif remonte : colonnes suspectes (emails
    invalides), relations incohérentes (store_id orphelins), anomalie/tendance
    (chute du CA sur la période)."""
    from app.services import quality as quality_svc
    from app.services import discoveries as disc_svc

    db, conn, _ = session_with_conn
    cfg = conn_svc.get_source_adapter(conn)
    snapshot, _ = scanner.scan_and_persist(db, conn, cfg)
    _profile_all(db, conn, cfg, snapshot)
    quality_svc.run_quality(db, conn, cfg)  # calcule l'intégrité des relations

    d = disc_svc.run_discoveries(db, conn, cfg)
    assert d.scanned is True
    c = d.counts
    assert c["suspicious_columns"] >= 1
    assert c["incoherent_relations"] >= 1
    assert c["anomalies"] + c["trends"] >= 1
    # Chaque découverte propose une question prête à creuser.
    assert any(i.get("suggested_question") for i in d.items)
    # Hiérarchie premium (critique/important/opportunité/info) + accroche + récit.
    assert set(d.levels) == {"critical", "important", "opportunity", "info"}
    assert sum(d.levels.values()) == len(d.items)
    assert d.headline and all(isinstance(h, str) for h in d.headline)
    assert all("level" in i and i.get("narrative") for i in d.items)

    # Cache (perf) : le 2e appel est servi depuis le cache, sans recalcul.
    calls = {"n": 0}
    real = disc_svc.run_discoveries

    def counting(*a, **k):
        calls["n"] += 1
        return real(*a, **k)

    import app.services.discoveries as _mod
    _mod.invalidate(conn.id)
    monkeypatch.setattr(_mod, "run_discoveries", counting)
    first = disc_svc.cached_discoveries(db, conn, cfg)
    second = disc_svc.cached_discoveries(db, conn, cfg)
    assert first["cached"] is False and second["cached"] is True
    assert calls["n"] == 1  # un seul vrai calcul
    # Le forçage recalcule.
    disc_svc.cached_discoveries(db, conn, cfg, force=True)
    assert calls["n"] == 2

    # Versionnement par empreinte : l'insight porte son empreinte à 3 composants
    # (schéma / profils / qualité) et une empreinte combinée déterministe.
    fp = first["fingerprint"]
    assert set(fp) == {"schema", "profiles", "quality", "combined"}
    assert all(isinstance(fp[k], str) and fp[k] for k in fp)
    # Empreinte reproductible tant que les données ne bougent pas.
    assert disc_svc._fingerprint(db, conn, disc_svc.current_snapshot(db, conn))["combined"] == fp["combined"]
    # Si le schéma change, l'empreinte schéma change → obsolescence explicable.
    prev = dict(fp)
    changed = {**fp, "schema": "deadbeef0000"}
    assert disc_svc._stale_reason(changed, prev) == ["schéma"]
    assert disc_svc._stale_reason({**fp, "quality": "0000deadbeef"}, prev) == ["qualité"]
    assert disc_svc._stale_reason(None, prev) == []


def test_sql_non_regression(session_with_conn):
    """Jeu métier de référence (indicateur CDC « ≥ 90 % de requêtes correctes »).

    Chaque question passe par le pipeline complet ; un validateur vérifie la
    forme du SQL et/ou le résultat. On exige un taux de réussite ≥ 90 %.
    """
    db, conn, _ = session_with_conn
    cfg = conn_svc.get_source_adapter(conn)
    snapshot, _ = scanner.scan_and_persist(db, conn, cfg)
    _profile_all(db, conn, cfg, snapshot)

    def sql(r):
        return (r.sql or "").lower()

    CASES = [
        ("Combien de clients ?", lambda r: r.rows[0][0] == 500 and "count(*)" in sql(r)),
        ("Nombre de commandes", lambda r: r.rows[0][0] == 3000),
        ("Combien de produits ?", lambda r: r.rows[0][0] == 80),
        ("Montre les magasins", lambda r: r.row_count == 4),
        ("Montant total des commandes", lambda r: "sum(amount_ttc)" in sql(r) and r.rows[0][0] > 0),
        ("Quel est le montant moyen des commandes ?", lambda r: "avg(amount_ttc)" in sql(r)),
        ("Montant total des commandes par mois",
         lambda r: "group by" in sql(r) and r.row_count >= 12),
        ("Nombre de commandes par magasin",
         lambda r: "group by" in sql(r) and r.row_count >= 1),
        ("Top 5 clients par loyalty_points",
         lambda r: r.row_count == 5 and "order by" in sql(r) and "desc" in sql(r)),
        ("Montant total des commandes par magasin",
         lambda r: "sum(amount_ttc)" in sql(r) and "group by" in sql(r)),
    ]

    passed, failures = 0, []
    for question, ok in CASES:
        try:
            resp = chat_svc.answer_question(db, conn, question, deep_analysis=False)
            if resp.status == "answered" and ok(resp):
                passed += 1
            else:
                failures.append(f"{question} → status={resp.status}, sql={resp.sql}")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{question} → exception {exc}")

    rate = passed / len(CASES)
    assert rate >= 0.9, f"Taux de réussite {rate:.0%} < 90% — échecs : {failures}"


def test_agent_investigation_multi_step(session_with_conn):
    """Question ANALYTIQUE ouverte → l'agent planifie, enchaîne des
    sous-questions et synthétise (vrai moteur de raisonnement)."""
    db, conn, _ = session_with_conn
    cfg = conn_svc.get_source_adapter(conn)
    snapshot, _ = scanner.scan_and_persist(db, conn, cfg)
    _profile_all(db, conn, cfg, snapshot)

    resp = chat_svc.answer_question(db, conn, "Pourquoi les ventes baissent ?")
    assert resp.status == "answered"
    inv = resp.investigation
    assert inv is not None
    # Sujet guidé par la question (« ventes » → orders, pas order_items).
    assert inv["subject"] == "orders"
    # Un plan explicite + plusieurs sous-questions exécutées.
    assert len(inv["plan"]) >= 3
    assert len(inv["steps"]) >= 3
    # Étape de tendance temporelle chiffrée + conclusion + recommandations.
    assert any("Tendance" in s["title"] for s in inv["steps"])
    assert inv["conclusion"] and inv["recommendations"]
    # Chaque étape porte SON SQL (auditable).
    assert all(s["sql"] for s in inv["steps"])
    # Une question simple ne déclenche PAS l'agent.
    simple = chat_svc.answer_question(db, conn, "Combien de clients ?")
    assert simple.investigation is None


def test_space_conversations_history(session_with_conn, monkeypatch):
    """Historique de chat rattaché à l'espace : conversation + tour (source
    choisie, gouvernance appliquée), rejouable à l'identique."""
    db, conn, _ = session_with_conn
    scanner.scan_and_persist(db, conn, conn_svc.get_source_adapter(conn))
    client = _client_for(db, monkeypatch)
    H = {"X-Tenant": "itest"}
    try:
        sid = client.post("/spaces", json={"name": "Achat"}, headers=H).json()["id"]
        client.post(f"/spaces/{sid}/connections", json={"connection_id": conn.id}, headers=H)
        base = f"/spaces/{sid}/conversations"

        conv = client.post(base, json={}, headers=H).json()
        cid = conv["id"]
        r = client.post(f"{base}/{cid}/turns",
                        json={"connection_id": conn.id, "question": "Combien de clients ?",
                              "deep_analysis": False}, headers=H)
        assert r.status_code == 200
        body = r.json()
        assert body["turn"]["response"]["rows"][0][0] == 500
        assert body["turn"]["connection_id"] == conn.id
        assert body["conversation"]["title"].startswith("Combien de clients")

        # Rechargement (multi-appareils).
        full = client.get(f"{base}/{cid}", headers=H).json()
        assert len(full["turns"]) == 1

        # Dossier + archivage propres à l'espace.
        folder = client.post(f"{base}/folders", json={"name": "Fournisseurs"}, headers=H).json()
        client.patch(f"{base}/{cid}", json={"folder_id": folder["id"], "archived": True}, headers=H)
        assert client.get(base, headers=H).json() == []
        arch = client.get(f"{base}?archived=true", headers=H).json()
        assert any(c["id"] == cid for c in arch)
    finally:
        from app.main import app
        app.dependency_overrides.clear()


def test_reports_generate_edit_export(session_with_conn, monkeypatch):
    """Studio de rapports : générer depuis une source (analyse chiffrée), ajouter
    et éditer un bloc, exporter en Markdown / Word / PDF."""
    db, conn, _ = session_with_conn
    scanner.scan_and_persist(db, conn, conn_svc.get_source_adapter(conn))
    client = _client_for(db, monkeypatch)
    H = {"X-Tenant": "itest"}
    try:
        rep = client.post("/reports", json={}, headers=H).json()
        rid = rep["id"]

        # Génération IA à partir d'une source réelle → blocs argumentés.
        gen = client.post(f"/reports/{rid}/generate", json={
            "prompt": "Montant total des commandes par mois",
            "connection_id": conn.id, "deep_analysis": True,
        }, headers=H)
        assert gen.status_code == 200
        body = gen.json()
        assert body["title"].startswith("Montant total")
        kinds = [b["kind"] for b in body["blocks"]]
        assert "markdown" in kinds and "table" in kinds  # narratif + données

        # Ajout + édition d'un bloc de texte (modifiable directement).
        client.post(f"/reports/{rid}/blocks",
                    json={"kind": "markdown", "content": {"text": "Note manuelle."}}, headers=H)
        full = client.get(f"/reports/{rid}", headers=H).json()
        last = full["blocks"][-1]
        client.put(f"/reports/{rid}/blocks/{last['id']}",
                   json={"content": {"text": "Note corrigée."}}, headers=H)
        again = client.get(f"/reports/{rid}", headers=H).json()
        assert again["blocks"][-1]["content"]["text"] == "Note corrigée."

        # Exports.
        md = client.get(f"/reports/{rid}/export?format=md", headers=H)
        assert md.status_code == 200 and b"#" in md.content
        docx = client.get(f"/reports/{rid}/export?format=docx", headers=H)
        assert docx.status_code == 200 and docx.content[:2] == b"PK"
        pdf = client.get(f"/reports/{rid}/export?format=pdf", headers=H)
        assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    finally:
        from app.main import app
        app.dependency_overrides.clear()


def test_alert_threshold_evaluation(session_with_conn):
    from app.models.alert import Alert
    from app.services import alerts as alerts_svc

    db, conn, _ = session_with_conn
    scanner.scan_and_persist(db, conn, conn_svc.get_source_adapter(conn))

    # Il y a 500 clients ; un seuil > 100 doit se déclencher.
    alert = Alert(
        tenant_id=conn.tenant_id, connection_id=conn.id, name="Trop de clients",
        table_name="customers", expression="count(*)", comparison="gt", threshold=100,
    )
    db.add(alert)
    db.flush()
    event = alerts_svc.evaluate(db, alert, conn)
    assert event.status == "triggered"
    assert alert.last_value == 500

    # Un seuil > 100000 ne se déclenche pas.
    alert.threshold = 100000
    event2 = alerts_svc.evaluate(db, alert, conn)
    assert event2.status == "ok"


def test_alert_pct_drop(session_with_conn):
    from app.models.alert import Alert
    from app.services import alerts as alerts_svc

    db, conn, _ = session_with_conn
    scanner.scan_and_persist(db, conn, conn_svc.get_source_adapter(conn))

    alert = Alert(
        tenant_id=conn.tenant_id, connection_id=conn.id, name="Chute",
        table_name="customers", expression="count(*)", comparison="pct_drop", threshold=20,
    )
    db.add(alert)
    db.flush()
    # 1re évaluation : référence (500), pas de déclenchement.
    e1 = alerts_svc.evaluate(db, alert, conn)
    assert e1.status == "ok"
    # On simule une chute en forçant last_value élevé.
    alert.last_value = 1000
    e2 = alerts_svc.evaluate(db, alert, conn)  # 500 vs 1000 → -50%
    assert e2.status == "triggered"
    assert "Chute" in e2.message


def test_alert_via_definition(session_with_conn):
    from app.models.alert import Alert
    from app.models.definitions import BusinessDefinition
    from app.services import alerts as alerts_svc

    db, conn, _ = session_with_conn
    scanner.scan_and_persist(db, conn, conn_svc.get_source_adapter(conn))

    d = BusinessDefinition(
        tenant_id=conn.tenant_id, name="CA", kind="measure",
        table_name="orders", expression="sum(amount_ttc)",
    )
    db.add(d)
    db.flush()
    alert = Alert(
        tenant_id=conn.tenant_id, connection_id=conn.id, name="CA mini",
        definition_id=d.id, comparison="lt", threshold=1_000_000_000,
    )
    db.add(alert)
    db.flush()
    event = alerts_svc.evaluate(db, alert, conn)
    # Le CA total de la démo est < 1 milliard → déclenché.
    assert event.status == "triggered"
    assert alert.last_value and alert.last_value > 0
