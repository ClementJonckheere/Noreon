from __future__ import annotations

from app.services.analyst import analyze


def test_empty_result():
    r = analyze("q", ["total"], [])
    assert "aucune ligne" in r.summary
    assert r.recommendations


def test_single_aggregate():
    r = analyze("q", ["total"], [[42]])
    assert "total = 42" in r.summary


def test_temporal_trend_and_rupture():
    rows = [
        ["2024-01-01", 100],
        ["2024-02-01", 110],
        ["2024-03-01", 105],
        ["2024-04-01", 30],  # chute > 30 % → anomalie
    ]
    r = analyze("évolution", ["month", "total"], rows)
    assert "baisse" in r.summary.lower()
    assert any("2024-04-01" in a for a in r.anomalies)
    assert r.recommendations  # vérification suggérée


def test_categorical_concentration():
    rows = [["Paris", 800], ["Lyon", 100], ["Lille", 50]]
    r = analyze("répartition", ["city", "total"], rows)
    assert "Paris" in r.summary
    assert any("concentration" in o.lower() for o in r.observations)


def test_outlier_detection():
    rows = [["c" + str(i), 100 + i] for i in range(10)] + [["c99", 10_000]]
    r = analyze("valeurs", ["name", "amount"], rows)
    assert any("atypique" in a for a in r.anomalies)


def test_no_anomaly_on_stable_series():
    rows = [[f"2024-0{i}-01", 100 + i] for i in range(1, 8)]
    r = analyze("évolution", ["month", "total"], rows)
    assert r.anomalies == []


def test_unsorted_raw_list_not_treated_as_time_series():
    # Dump brut : dates NON ordonnées (tri par id). Aucune analyse de rupture
    # « entre périodes » ne doit être produite — ce serait décoratif et faux.
    rows = [
        [1, "2023-05-01", 10],
        [2, "2023-01-01", 500],
        [3, "2023-09-01", 3],
        [4, "2023-02-01", 250],
        [5, "2023-11-01", 40],
    ]
    r = analyze("liste", ["id", "signup_date", "loyalty_points"], rows)
    assert not any("Variation brutale" in a for a in r.anomalies)
    assert "hausse" not in r.summary.lower() and "baisse" not in r.summary.lower()
