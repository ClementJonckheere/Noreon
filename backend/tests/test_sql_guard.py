from __future__ import annotations

import pytest

from app.services.sql_guard import SQLGuardError, guard


def test_select_gets_limit_applied():
    g = guard("SELECT * FROM customers", row_limit=1000)
    assert "LIMIT 1000" in g.sql.upper()
    assert g.limit_applied == 1000


def test_existing_smaller_limit_preserved():
    g = guard("SELECT * FROM customers LIMIT 5", row_limit=1000)
    assert g.limit_applied == 5


def test_existing_larger_limit_capped():
    g = guard("SELECT * FROM customers LIMIT 999999", row_limit=1000)
    assert g.limit_applied == 1000


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO t VALUES (1)",
        "UPDATE t SET a = 1",
        "DELETE FROM t",
        "DROP TABLE t",
        "CREATE TABLE t (id int)",
        "ALTER TABLE t ADD COLUMN a int",
        "TRUNCATE t",
        "GRANT SELECT ON t TO x",
    ],
)
def test_ddl_dml_blocked(sql):
    with pytest.raises(SQLGuardError):
        guard(sql, row_limit=1000)


def test_multiple_statements_blocked():
    with pytest.raises(SQLGuardError):
        guard("SELECT 1; DROP TABLE t", row_limit=1000)


def test_cte_select_allowed():
    g = guard("WITH x AS (SELECT 1 AS n) SELECT * FROM x", row_limit=100)
    assert g.sql  # accepté


def test_aggregate_detected():
    g = guard("SELECT count(*) FROM customers", row_limit=100)
    assert g.is_aggregate is True


def test_write_hidden_in_cte_blocked():
    # Défense en profondeur : une écriture cachée dans une sous-partie est bloquée.
    with pytest.raises(SQLGuardError):
        guard("WITH x AS (DELETE FROM t RETURNING *) SELECT * FROM x", row_limit=100)


def test_empty_query_rejected():
    with pytest.raises(SQLGuardError):
        guard("   ", row_limit=100)
