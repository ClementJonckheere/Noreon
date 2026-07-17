from __future__ import annotations

from app.models.profile import ColumnProfile
from app.services.semantic import generate_proposals


def make_profile(table: str, column: str, **kw) -> ColumnProfile:
    p = ColumnProfile(
        connection_id=1, schema_name="public", table_name=table, column_name=column,
        sampled=False, sample_size=100,
    )
    for k, v in kw.items():
        setattr(p, k, v)
    return p


def _by_col(proposals, table, col):
    return next((p for p in proposals if p.table_name == table and p.column_name == col), None)


def test_email_concept_from_content():
    # Le contenu réel (PII email) prime sur le nom : colonne au nom opaque.
    props = generate_proposals([
        make_profile("customers", "contact_info", pii_type="email", detected_type="text"),
    ])
    p = _by_col(props, "customers", "contact_info")
    assert p is not None and p.concept_name == "Email"
    assert p.confidence >= 0.9
    assert "contenu réel" in p.rationale


def test_client_concept_from_table_pk():
    props = generate_proposals([
        make_profile("customers", "id", detected_type="integer"),
    ])
    p = _by_col(props, "customers", "id")
    assert p is not None and p.concept_name == "Client"


def test_amount_requires_numeric_content():
    # « amount » stocké en texte non numérique → pas de concept Montant.
    props = generate_proposals([
        make_profile("orders", "amount_note", detected_type="text"),
    ])
    p = _by_col(props, "orders", "amount_note")
    assert p is None or p.concept_name != "Montant"


def test_ht_ttc_variants_require_arbitration():
    # net_price (HT) et amount_ttc (TTC) coexistent → arbitrage, pas de fusion.
    props = generate_proposals([
        make_profile("products", "net_price", detected_type="numeric"),
        make_profile("orders", "amount_ttc", detected_type="numeric"),
    ])
    net = _by_col(props, "products", "net_price")
    ttc = _by_col(props, "orders", "amount_ttc")
    assert net is not None and ttc is not None
    assert net.concept_name == "Montant" and ttc.concept_name == "Montant"
    assert net.needs_arbitration and ttc.needs_arbitration
    assert "HT" in net.arbitration_note and "TTC" in net.arbitration_note


def test_single_variant_no_arbitration():
    props = generate_proposals([
        make_profile("orders", "amount_ttc", detected_type="numeric"),
    ])
    p = _by_col(props, "orders", "amount_ttc")
    assert p is not None and p.needs_arbitration is False


def test_date_concept_from_detected_type():
    props = generate_proposals([
        make_profile("orders", "order_date", detected_type="datetime"),
    ])
    p = _by_col(props, "orders", "order_date")
    assert p is not None and p.concept_name == "Date"


def test_never_auto_validated():
    props = generate_proposals([
        make_profile("customers", "email", pii_type="email", detected_type="text"),
    ])
    # Le moteur produit des propositions : le statut validé n'existe qu'après
    # revue humaine (vérifié au niveau persistance, ici aucune notion de statut).
    assert all(0 < p.confidence <= 1 for p in props)
