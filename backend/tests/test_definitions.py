from __future__ import annotations

from app.llm.heuristic import HeuristicProvider, parse_definitions

SCHEMA = """Table public.orders (rows~3000)
  - id integer PK
  - customer_id integer
  - store_id integer
  - order_date date
  - amount_ttc numeric
Table public.customers (rows~500)
  - id integer PK
  - full_name varchar

Définitions métier réutilisables :
  Mesure CA = sum(amount_ttc) sur public.orders
  Segment client fidele sur public.customers filtre: id IN (SELECT customer_id FROM orders GROUP BY customer_id HAVING count(*) >= 3)
"""


def test_parse_definitions():
    defs = parse_definitions(SCHEMA)
    kinds = {d.raw_name: d.kind for d in defs}
    assert kinds["CA"] == "measure"
    assert kinds["client fidele"] == "segment"
    ca = next(d for d in defs if d.raw_name == "CA")
    assert ca.expression == "sum(amount_ttc)" and ca.fq == "public.orders"


def test_measure_resolved_in_question():
    p = HeuristicProvider()
    r = p.generate_sql("Quel est le CA ?", SCHEMA)
    assert r.sql == "SELECT sum(amount_ttc) AS ca FROM public.orders"
    assert r.tables_used == ["public.orders"]


def test_measure_with_group_by_month():
    p = HeuristicProvider()
    r = p.generate_sql("CA par mois", SCHEMA)
    assert "date_trunc('month', order_date)" in r.sql.lower()
    assert "sum(amount_ttc)" in r.sql.lower()
    assert "group by 1" in r.sql.lower()


def test_segment_count():
    p = HeuristicProvider()
    r = p.generate_sql("Combien de clients fideles ?", SCHEMA)
    assert "count(*)" in r.sql.lower()
    assert "public.customers" in r.sql
    assert "having count(*) >= 3" in r.sql.lower()


def test_measure_restricted_by_segment_same_table():
    schema = SCHEMA + "  Segment grosses commandes sur public.orders filtre: amount_ttc > 300\n"
    p = HeuristicProvider()
    r = p.generate_sql("CA des grosses commandes", schema)
    assert "sum(amount_ttc)" in r.sql.lower()
    assert "amount_ttc > 300" in r.sql
    assert "where" in r.sql.lower()


def test_definition_takes_priority_over_generic():
    # « CA » comme mesure définie doit être utilisé, pas l'agrégat générique.
    p = HeuristicProvider()
    r = p.generate_sql("CA", SCHEMA)
    assert "sum(amount_ttc)" in r.sql.lower()


def test_no_definitions_falls_back():
    schema_no_defs = "\n".join(SCHEMA.split("Définitions")[0].splitlines())
    p = HeuristicProvider()
    r = p.generate_sql("Combien de commandes ?", schema_no_defs)
    assert "count(*)" in r.sql.lower() and "public.orders" in r.sql
