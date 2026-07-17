from __future__ import annotations

from app.llm.heuristic import HeuristicProvider
from app.services.charting import suggest_chart

SCHEMA = """Table public.orders (rows~3000)
  - id integer PK
  - customer_id integer
  - store_id integer
  - order_date date
  - amount_ttc numeric
"""


# ---- suggestion de type ----
def test_temporal_series_suggests_line():
    s = suggest_chart(
        ["month", "sum_amount"],
        [["2024-01-01", 100], ["2024-02-01", 130], ["2024-03-01", 90]],
    )
    assert s.type == "line" and s.x == "month" and s.y == ["sum_amount"]


def test_postgres_native_types_decimal_and_date():
    # Les résultats bruts psycopg contiennent des Decimal et des date.
    from datetime import date
    from decimal import Decimal

    s = suggest_chart(
        ["month", "sum_amount_ttc"],
        [
            [date(2024, 1, 1), Decimal("100.5")],
            [date(2024, 2, 1), Decimal("130.2")],
            [date(2024, 3, 1), Decimal("90.0")],
        ],
    )
    assert s.type == "line"


def test_categorical_suggests_bar_with_pie_alternative():
    s = suggest_chart(
        ["store", "total"],
        [["Paris", 120], ["Lyon", 80], ["Lille", 60]],
    )
    assert s.type == "bar"
    assert "pie" in s.alternatives


def test_id_column_is_categorical_not_scatter():
    # store_id est un identifiant : barres, jamais un nuage de points.
    s = suggest_chart(
        ["store_id", "total"],
        [[4, 750], [2, 750], [1, 729], [3, 729]],
    )
    assert s.type == "bar" and s.x == "store_id"


def test_two_numerics_suggest_scatter():
    s = suggest_chart(
        ["price", "quantity"],
        [[10, 2], [20, 5], [15, 3], [30, 8]],
    )
    assert s.type == "scatter"


def test_single_row_falls_back_to_table():
    s = suggest_chart(["total"], [[42]])
    assert s.type == "table"


def test_distribution_suggests_histogram():
    rows = [[float(i % 17)] for i in range(50)]
    s = suggest_chart(["amount"], rows)
    assert s.type == "histogram"


# ---- GROUP BY « par X » dans l'heuristique ----
def test_group_by_column():
    p = HeuristicProvider()
    r = p.generate_sql("montant total des commandes par magasin", SCHEMA)
    assert "group by 1" in r.sql.lower()
    assert "store_id" in r.sql
    assert "sum(amount_ttc)" in r.sql.lower()


def test_group_by_month_uses_date_trunc():
    p = HeuristicProvider()
    r = p.generate_sql("total des commandes par mois", SCHEMA)
    assert "date_trunc('month', order_date)" in r.sql.lower()
    assert "group by 1" in r.sql.lower()


def test_count_group_by():
    p = HeuristicProvider()
    r = p.generate_sql("nombre de commandes par mois", SCHEMA)
    assert "count(*)" in r.sql.lower()
    assert "date_trunc('month'" in r.sql.lower()


def test_no_group_still_simple_agg():
    p = HeuristicProvider()
    r = p.generate_sql("montant moyen des commandes", SCHEMA)
    assert "group by" not in r.sql.lower()
    assert "avg(amount_ttc)" in r.sql.lower()
