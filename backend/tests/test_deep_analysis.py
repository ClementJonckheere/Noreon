"""Tests de l'analyste approfondi (valeur métier).

Unitaires (hors-ligne) sur les briques de calcul : sélection de la mesure,
découpage en tranches, pouvoir explicatif. L'intégration bout-en-bout (requêtes
de suivi réelles + croisements) est couverte dans test_integration.py sur la
base de démo.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.services import deep_analysis as da


class _StubAdapter:
    dialect = "postgres"

    def quote_ident(self, name: str) -> str:
        return '"' + name + '"'

    def qualified(self, schema: str, table: str) -> str:
        return f'"{schema}"."{table}"'


def _col(name, dtype, *, pk=False, profile=None):
    return da._Col(name=name, data_type=dtype, is_pk=pk, profile=profile)


def _profile(**kw):
    base = dict(min_value=None, max_value=None, distinct_count=None,
                distinct_ratio=None, pii_type=None, detected_type=None)
    base.update(kw)
    return SimpleNamespace(**base)


# ---------------------------------------------------------------------------
# Sélection de la mesure : additive vs effectif
# ---------------------------------------------------------------------------
def test_measure_prefers_money_column():
    fact = da._Table("public", "orders", 3000, [
        _col("id", "integer", pk=True),
        _col("customer_id", "integer"),
        _col("amount_ttc", "numeric"),
    ])
    m = da._pick_measure(_StubAdapter(), fact, "montant total des commandes")
    assert m.sql is not None and "amount_ttc" in m.sql
    assert m.column == "amount_ttc"


def test_measure_falls_back_to_headcount_for_count_questions():
    # « Combien de clients » : on ne somme pas une mesure au hasard, on profile
    # la population → effectif.
    fact = da._Table("public", "customers", 500, [
        _col("id", "integer", pk=True),
        _col("age", "integer"),
        _col("loyalty_points", "integer"),
    ])
    m = da._pick_measure(_StubAdapter(), fact, "Combien de clients ?")
    assert m.sql is None
    assert m.column is None
    assert "effectif" in m.label


def test_age_is_never_summed_as_a_measure():
    # Une table sans colonne monétaire ne doit pas transformer « age » en mesure.
    fact = da._Table("public", "people", 100, [
        _col("id", "integer", pk=True),
        _col("age", "integer"),
    ])
    m = da._pick_measure(_StubAdapter(), fact, "répartition des gens")
    assert m.sql is None  # âge = dimension, pas mesure


# ---------------------------------------------------------------------------
# Découpage en tranches (le croisement démographique « qui achète »)
# ---------------------------------------------------------------------------
def test_numeric_band_expression_and_labels():
    col = _col("age", "integer", profile=_profile(min_value="18", max_value="72"))
    dim = da._numeric_band_expr(_StubAdapter(), col, "f")
    assert dim is not None and dim.kind == "numeric-band"
    assert dim.bands["lo"] == 18 and dim.bands["width"] == 11
    # L'indice 0 → « 18–28 », l'indice 4 → « 62–72 ».
    assert da._band_label(0, dim.bands) == "18–28"
    assert da._band_label(4, dim.bands) == "62–72"


def test_numeric_band_rejects_degenerate_range():
    col = _col("x", "integer", profile=_profile(min_value="5", max_value="5"))
    assert da._numeric_band_expr(_StubAdapter(), col, "f") is None


# ---------------------------------------------------------------------------
# Pouvoir explicatif : gradient de mesure moyenne vs concentration
# ---------------------------------------------------------------------------
def test_power_detects_measure_gradient():
    # La mesure MOYENNE croît fortement d'un segment à l'autre → dimension
    # structurante (cv_avg élevé).
    dim = da._Dimension(label="tranche d'âge", expr="band", kind="numeric-band")
    groups = [
        da._Group("18–28", n=100, total=10_000),   # avg 100
        da._Group("40–50", n=100, total=20_000),   # avg 200
        da._Group("62–72", n=100, total=40_000),   # avg 400
    ]
    seg = da._Segmentation(dim=dim, groups=groups, sql="", metric_is_measure=True)
    da._compute_stats(seg)
    assert seg.cv_avg > 0.3
    assert seg.power > 0


def test_power_detects_concentration_without_measure():
    dim = da._Dimension(label="ville", expr="city", kind="categorical")
    groups = [da._Group("Paris", n=800, total=None), da._Group("Lyon", n=100, total=None),
              da._Group("Lille", n=100, total=None)]
    seg = da._Segmentation(dim=dim, groups=groups, sql="", metric_is_measure=False)
    da._compute_stats(seg)
    assert seg.top_share > 0.7        # Paris domine
    assert seg.hhi > 1 / 3            # au-dessus de l'équirépartition
