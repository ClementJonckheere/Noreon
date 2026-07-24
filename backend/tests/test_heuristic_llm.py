from __future__ import annotations

from app.llm.heuristic import HeuristicProvider, parse_schema_context

SCHEMA = """Table public.customers (rows~39000)
  - id integer PK
  - email varchar
  - loyalty_points integer
Table public.orders (rows~120000)
  - id integer PK
  - customer_id integer
  - amount numeric
"""


def test_parse_schema_context():
    tables, syns = parse_schema_context(SCHEMA)
    assert {t.name for t in tables} == {"customers", "orders"}
    customers = next(t for t in tables if t.name == "customers")
    assert any(c.name == "email" for c in customers.columns)
    assert syns == {}


def test_parse_validated_concepts():
    ctx = SCHEMA + "\nDictionnaire métier validé :\n  Concept Acheteur = customers.id, customers.full_name\n"
    _, syns = parse_schema_context(ctx)
    assert "acheteur" in syns["customers"]


def test_validated_concept_drives_table_choice():
    # « acheteurs » n'est pas un synonyme du lexique statique : seul le
    # dictionnaire métier validé permet de router vers customers.
    ctx = SCHEMA + "\nDictionnaire métier validé :\n  Concept Acheteur = customers.id\n"
    p = HeuristicProvider()
    r = p.generate_sql("Combien d'acheteurs ?", ctx)
    assert "public.customers" in r.sql
    # Sans le dictionnaire : clarification demandée (pas de devinette).
    r2 = p.generate_sql("Combien d'acheteurs ?", SCHEMA)
    assert r2.clarification_needed is not None


def test_count_question():
    p = HeuristicProvider()
    r = p.generate_sql("Combien de clients ?", SCHEMA)
    assert "count(*)" in r.sql.lower()
    assert "public.customers" in r.sql
    assert r.clarification_needed is None


def test_average_question():
    p = HeuristicProvider()
    r = p.generate_sql("Quel est le montant moyen des commandes ?", SCHEMA)
    assert "avg(amount)" in r.sql.lower()
    assert "public.orders" in r.sql


def test_average_picks_named_column_not_pk():
    schema = """Table public.orders (rows~100)
  - id integer PK
  - customer_id integer
  - amount_ttc numeric
"""
    p = HeuristicProvider()
    r = p.generate_sql("montant moyen des commandes", schema)
    assert "avg(amount_ttc)" in r.sql.lower()
    assert "avg(id)" not in r.sql.lower()


def test_list_question_has_limit_context():
    p = HeuristicProvider()
    r = p.generate_sql("Montre les commandes", SCHEMA)
    assert "public.orders" in r.sql
    assert "limit" in r.sql.lower()


def test_top_n_question():
    p = HeuristicProvider()
    r = p.generate_sql("top 5 clients par loyalty_points", SCHEMA)
    assert "order by" in r.sql.lower()
    assert "limit 5" in r.sql.lower()


def test_unknown_table_asks_clarification():
    p = HeuristicProvider()
    r = p.generate_sql("Quel est le taux de churn des abonnements SaaS ?", SCHEMA)
    assert r.clarification_needed is not None
    assert r.sql == ""


def test_synonym_matching_client_to_customers():
    p = HeuristicProvider()
    r = p.generate_sql("nombre de clients", SCHEMA)
    assert "public.customers" in r.sql


# Schéma avec TROIS montants dans une même table (piège HT / TTC / ambigu).
MONEY_SCHEMA = """Table public.orders (rows~3000)
  - id integer PK
  - customer_id integer
  - amount numeric
  - amount_ttc numeric
  - net_price numeric
"""


def test_measure_arbitration_recommends_ttc():
    """Mesures contradictoires : le moteur RECOMMANDE le TTC, présente les trois
    options et documente le choix — sans fusionner en silence."""
    p = HeuristicProvider()
    r = p.generate_sql("Montant total des commandes", MONEY_SCHEMA)
    assert "sum(amount_ttc)" in r.sql.lower()
    mo = r.measure_options
    assert mo is not None
    assert mo["chosen"] == "amount_ttc" and mo["chosen_kind"] == "TTC"
    cols = {o["column"]: o for o in mo["options"]}
    assert {"amount", "amount_ttc", "net_price"} <= set(cols)
    assert cols["amount_ttc"]["recommended"] and cols["amount_ttc"]["kind"] == "TTC"
    assert cols["net_price"]["kind"] == "HT"
    assert cols["amount"]["kind"] is None  # ambigu
    assert "TTC" in mo["reason"]


def test_measure_arbitration_respects_explicit_ht():
    """Une demande explicite de HT est suivie, mais l'existence du TTC est signalée."""
    p = HeuristicProvider()
    r = p.generate_sql("Montant total HT des commandes", MONEY_SCHEMA)
    assert "sum(net_price)" in r.sql.lower()
    assert r.measure_options["chosen"] == "net_price"


def test_measure_arbitration_explicit_ttc_token():
    p = HeuristicProvider()
    r = p.generate_sql("CA TTC des commandes", MONEY_SCHEMA)
    assert "sum(amount_ttc)" in r.sql.lower()
    assert r.measure_options["chosen"] == "amount_ttc"


def test_single_measure_no_arbitration():
    """Une seule mesure monétaire → pas d'arbitrage (rien à départager)."""
    p = HeuristicProvider()
    r = p.generate_sql("montant moyen des commandes", SCHEMA)  # orders n'a qu'« amount »
    assert r.measure_options is None


def test_company_context_amount_basis_drives_default():
    """Contexte d'entreprise (D) : sans mention explicite, la convention « HT »
    de l'entreprise oriente le choix par défaut (au lieu du TTC)."""
    p = HeuristicProvider()
    ctx_ht = MONEY_SCHEMA + "\nContexte entreprise (conventions à respecter) :\n  - Montants : HT\n"
    r = p.generate_sql("Montant total des commandes", ctx_ht)
    assert "sum(net_price)" in r.sql.lower()  # HT par convention d'entreprise
    assert r.measure_options["chosen"] == "net_price"
    # Une demande explicite de TTC prime sur la convention.
    r2 = p.generate_sql("Montant total TTC des commandes", ctx_ht)
    assert r2.measure_options["chosen"] == "amount_ttc"
