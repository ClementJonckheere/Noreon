from __future__ import annotations

from app.services import privacy


COLUMNS = ["full_name", "email", "amount"]
ROWS = [
    ["Client 1", "c1@ex.com", 100],
    ["Client 2", "c2@ex.com", 200],
    ["Client 1", "c1@ex.com", 50],  # même client → même jeton
]
PII = {"full_name": "name", "email": "email"}


def test_pii_never_reaches_llm_rows():
    res = privacy.protect(COLUMNS, ROWS, PII)
    flat = [str(v) for row in res.rows for v in row]
    assert "Client 1" not in flat and "c1@ex.com" not in flat
    # Les mesures restent intactes.
    assert res.rows[0][2] == 100


def test_pseudonymization_is_deterministic_within_result():
    res = privacy.protect(COLUMNS, ROWS, PII)
    # Client 1 apparaît deux fois → même jeton (regroupements préservés).
    assert res.rows[0][0] == res.rows[2][0]
    assert res.rows[0][0] != res.rows[1][0]
    assert res.rows[0][0].startswith("NOM-")
    assert res.rows[0][1].startswith("EMAIL-")


def test_reidentification_roundtrip():
    res = privacy.protect(COLUMNS, ROWS, PII)
    token = res.rows[1][0]  # jeton de « Client 2 »
    llm_text = f"Le client {token} concentre l'essentiel du volume."
    assert privacy.reidentify(llm_text, res.token_map) == (
        "Le client Client 2 concentre l'essentiel du volume."
    )


def test_reidentify_analysis_all_fields():
    res = privacy.protect(COLUMNS, ROWS, PII)
    t = res.rows[0][0]
    analysis = {
        "summary": f"{t} domine.",
        "observations": [f"voir {t}"],
        "anomalies": [],
        "recommendations": ["rien"],
    }
    out = privacy.reidentify_analysis(analysis, res.token_map)
    assert out["summary"] == "Client 1 domine."
    assert out["observations"] == ["voir Client 1"]


def test_no_pii_passthrough():
    res = privacy.protect(["month", "total"], [["2024-01", 5]], {})
    assert res.rows == [["2024-01", 5]]
    assert res.audit["method"].startswith("aucune")


def test_audit_content():
    res = privacy.protect(COLUMNS, ROWS, PII)
    audit = res.audit
    assert audit["method"] == "pseudonymisation"
    assert audit["protected_columns"] == PII
    assert audit["values_protected"] == 4  # 2 noms + 2 emails distincts


def test_nulls_untouched():
    rows = [[None, None, 10]]
    res = privacy.protect(COLUMNS, rows, PII)
    assert res.rows[0][0] is None and res.rows[0][1] is None
