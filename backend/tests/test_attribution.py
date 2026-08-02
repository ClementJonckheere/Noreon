"""Attribution de la variation (increment N) — le moteur explique d'où vient la
BAISSE (contribution au changement), pas seulement d'où vient le total.

Tests unitaires isolés (adaptateur factice) : pas de base de démo requise.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.services import agent
from app.services import decision_engine as de


def test_trailing_run_counts_recent_decline():
    rows = [["2024-11", 100], ["2024-12", 104], ["2025-01", 101],
            ["2025-02", 98], ["2025-03", 95], ["2025-04", 90]]
    # Pic en déc. 2024 ; les 4 dernières périodes baissent.
    assert agent._trailing_run(rows, "baisse") == 4
    assert agent._trailing_run(rows, "hausse") == 0


# --- Adaptateur factice : renvoie des fenêtres (récent, précédent) par axe ----
@dataclass
class _Res:
    rows: list
    guarded_sql: str = "SELECT ..."


@dataclass
class _Dim:
    label: str
    expr: str
    join_sql: str = ""
    kind: str = "categorical"
    bands: dict | None = None


@dataclass
class _Fact:
    name: str = "orders"
    schema: str = "public"
    columns: list = field(default_factory=list)


class _FakeAdapter:
    dialect = "postgresql"

    def __init__(self, by_expr):
        self._by_expr = by_expr

    def quote_ident(self, ident):
        return f'"{ident}"'

    def qualified(self, schema, name):
        return f'"{schema}"."{name}"'

    def run_query(self, sql, connection_id=None, **kwargs):
        for expr, rows in self._by_expr.items():
            if expr in sql:
                return _Res(rows=rows)
        return _Res(rows=[])


@dataclass
class _Col:
    name: str = "order_date"
    is_temporal: bool = True


def test_attribution_prefers_concentrated_region():
    """La région (baisse concentrée) l'emporte sur le genre (≈ 50/50) ; les
    tranches numériques sont écartées ; la contribution est bien celle du
    CHANGEMENT, pas du total."""
    by_expr = {
        # (segment, recent, prior)
        "d0.region": [("Provence-Alpes-Côte d'Azur", 37433, 51460),
                      ("Île-de-France", 69333, 68342),
                      ("Auvergne-Rhône-Alpes", 26617, 25698),
                      ("Hauts-de-France", 15697, 16138)],
        "f.gender": [("F", 41000, 48000), ("M", 40000, 46000)],   # baisse ≈ 50/50
        "band_loyalty": [("0", 10000, 20000), ("100", 9000, 10000)],
    }
    dims = [
        _Dim(label="region (stores)", expr="d0.region", join_sql=" JOIN stores d0 ON ..."),
        _Dim(label="gender", expr="f.gender"),
        _Dim(label="tranche de loyalty_points (customers)", expr="band_loyalty"),
    ]
    out = agent._attribute_variation(
        _FakeAdapter(by_expr), conn_id=1, guard_args={}, fact=_Fact(),
        dims=dims, measure_sql="f.amount_ttc", date_col=_Col(),
        recent_labels=["2025-03", "2025-04", "2025-05", "2025-06"],
        prior_labels=["2024-11", "2024-12", "2025-01", "2025-02"],
        trend_dir="baisse",
    )
    assert out is not None
    best = out["best"]
    assert best["dimension"] == "region (stores)"
    assert best["segment"] == "Provence-Alpes-Côte d'Azur"
    assert best["contribution_pct"] >= 90        # ~97 % de la baisse
    # Les tranches numériques ne figurent jamais dans l'attribution.
    assert all("tranche de" not in c["dimension"] for c in out["ranked"])


def test_attribution_none_when_diffuse():
    """Aucune cause dominante (baisse répartie) → pas d'attribution."""
    by_expr = {"f.gender": [("F", 41000, 45000), ("M", 40000, 44000)]}
    dims = [_Dim(label="gender", expr="f.gender")]
    out = agent._attribute_variation(
        _FakeAdapter(by_expr), conn_id=1, guard_args={}, fact=_Fact(), dims=dims,
        measure_sql="f.amount_ttc", date_col=_Col(),
        recent_labels=["2025-05", "2025-06"], prior_labels=["2025-03", "2025-04"],
        trend_dir="baisse",
    )
    assert out is None                            # F ~51 % < seuil de 55 %


def test_decide_primary_driver_leads():
    """La cause dominante de la variation (1er facteur) mène les recommandations,
    même face à une action à plus faible effort mais hors sujet."""
    d = de.decide(
        question="Pourquoi le CA baisse ?", metric_label="le CA",
        trend_direction="baisse", trend_pct=-12.0,
        drivers=[
            {"dimension": "region (stores)", "segment": "PACA", "share": 97.0},
            {"dimension": "segment (customers)", "segment": "Particulier", "share": 80.0},
        ],
    )
    assert d is not None
    reseau = next(x for x in d.decisions if x["role"] == "Directeur réseau")
    crm = next((x for x in d.decisions if x["role"] == "Responsable CRM"), None)
    # Le réseau (cause dominante) est rehaussé et passe devant.
    assert d.decisions[0]["role"] == "Directeur réseau"
    if crm is not None:
        assert reseau["stars"] >= crm["stars"]
