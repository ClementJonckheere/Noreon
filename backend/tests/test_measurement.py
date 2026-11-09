"""Invariants VERROUILLÉS du protocole de mesure (approche C).

Ces tests figent les garanties méthodologiques : une mesure ne réécrit jamais le
passé, le protocole est immuable une fois l'observation lancée, et le résultat est
classé par le SEUIL prévu — jamais par le simple signe positif de la cible.

Ils tournent sans base : un adaptateur factice interprète le SQL réel produit par
le service (les fenêtres semi-ouvertes restent donc testées), et une session
factice attribue des identifiants sans persistance.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.models.measurement import MeasurementPlan
from app.services import measurement as meas

IMPL = datetime(2025, 7, 1, tzinfo=timezone.utc)


class FakeAdapter:
    """Interprète le SQL `SELECT sum(col) FROM t WHERE dim IN (...) AND d >= a AND d < b`
    contre des séries journalières en mémoire — semi-ouvert [a, b) comme le vrai SQL."""

    def __init__(self, series: dict):
        self.series = series  # store -> callable(date) -> float

    def run_query(self, sql: str, connection_id=None):
        in_list = re.search(r"IN \(([^)]*)\)", sql)
        stores = re.findall(r"'([^']*)'", in_list.group(1)) if in_list else []
        # La borne peut porter un suffixe horaire ('2025-06-01T00:00:00+00:00') :
        # on ne capture que la partie date.
        lo = re.search(r">=\s*'(\d{4}-\d{2}-\d{2})", sql)
        hi = re.search(r"<\s*'(\d{4}-\d{2}-\d{2})", sql)
        total = 0.0
        if lo and hi and stores:
            start = date.fromisoformat(lo.group(1)); end = date.fromisoformat(hi.group(1))
            d = start
            while d < end:
                for s in stores:
                    fn = self.series.get(s)
                    if fn is not None:
                        total += fn(d)
                d += timedelta(days=1)
        return SimpleNamespace(rows=[[total]], guarded_sql=sql)


class FakeDB:
    """Session factice : attribue des id au flush, sans persistance."""

    def __init__(self):
        self._id = 0
        self.added = []

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        self._id += 1
        for o in self.added:
            if getattr(o, "id", None) is None:
                o.id = self._id
                self._id += 1


def _flat(base: float, obs: float):
    return lambda d: (obs if d >= IMPL.date() else base)


def _plan(series_ctrl_values, **over):
    scope = {"table": "action_impact", "dim_col": "store", "metric_col": "revenue",
             "date_col": "day", "values": ["T1", "T2"]}
    kw = dict(decision_id=1, tenant_id=1, connection_id=1, measure_type="impact",
              metric_concept_id="revenue", metric_label="Chiffre d'affaires",
              scope=scope, control_scope={"values": series_ctrl_values},
              comparison="matched_control", threshold=0.02,
              baseline_window_days=30, observation_window_days=30, protocol_version=1)
    kw.update(over)
    return MeasurementPlan(**kw)


def _adapter(t_obs: float, c_obs: float):
    # cibles et témoins : baseline plate 1000 ; observation paramétrable.
    return FakeAdapter({
        "T1": _flat(1000, t_obs), "T2": _flat(1000, t_obs),
        "C1": _flat(1000, c_obs), "C2": _flat(1000, c_obs),
    })


def test_new_measure_appends_run_same_protocol():
    """« Nouvelle mesure » crée TOUJOURS un nouveau run sur le même protocole."""
    db = FakeDB()
    plan = _plan(["C1", "C2"])
    meas.freeze_baseline(db, plan, _adapter(1030, 1045), implemented_at=IMPL)
    r30 = meas.run_measurement(db, plan, _adapter(1030, 1045), horizon_days=30)
    r90 = meas.run_measurement(db, plan, _adapter(1030, 1045), horizon_days=90)
    assert r30 is not r90
    assert r30.plan_id == plan.id and r90.plan_id == plan.id
    assert r30.horizon_days == 30 and r90.horizon_days == 90


def test_baseline_and_controls_immutable_between_runs():
    """baseline, implemented_at et témoins restent immuables entre J+30 et J+90."""
    db = FakeDB()
    plan = _plan(["C1", "C2"])
    meas.freeze_baseline(db, plan, _adapter(1030, 1045), implemented_at=IMPL)
    snap = (plan.baseline_target, plan.baseline_control, plan.implemented_at,
            tuple(plan.control_selection["control_ids"]), plan.control_selection["selection_at"])
    meas.run_measurement(db, plan, _adapter(1030, 1045), horizon_days=30)
    meas.run_measurement(db, plan, _adapter(1030, 1045), horizon_days=90)
    after = (plan.baseline_target, plan.baseline_control, plan.implemented_at,
             tuple(plan.control_selection["control_ids"]), plan.control_selection["selection_at"])
    assert snap == after


def test_measure_never_rewrites_previous_run():
    """Un résultat mesuré ne modifie JAMAIS rétroactivement un run précédent."""
    db = FakeDB()
    plan = _plan(["C1", "C2"])
    meas.freeze_baseline(db, plan, _adapter(1030, 1045), implemented_at=IMPL)
    r1 = meas.run_measurement(db, plan, _adapter(1030, 1045), horizon_days=30)
    frozen = (r1.raw_delta, r1.control_delta, r1.adjusted_delta, r1.result)
    # Un second run avec des données différentes ne doit rien changer au premier.
    meas.run_measurement(db, plan, _adapter(1200, 1000), horizon_days=90)
    assert (r1.raw_delta, r1.control_delta, r1.adjusted_delta, r1.result) == frozen


def test_objectif_depends_on_threshold_not_positive_sign():
    """objectif_atteint dépend du SEUIL contrôlé, jamais du simple signe + de la cible."""
    db = FakeDB()
    plan = _plan(["C1", "C2"])
    meas.freeze_baseline(db, plan, _adapter(1030, 1045), implemented_at=IMPL)
    # Cible +3 % (signe positif) MAIS témoins +4,5 % → écart contrôlé −1,5 pt < seuil.
    r = meas.run_measurement(db, plan, _adapter(1030, 1045), horizon_days=30)
    assert r.raw_delta > 0                      # la cible progresse…
    assert r.result == "objectif_non_atteint"   # …mais l'objectif n'est pas atteint.

    # Cible +2,5 % positive, écart contrôlé +1,5 pt, toujours < seuil de 2 pts.
    db2 = FakeDB(); plan2 = _plan(["C1", "C2"])
    meas.freeze_baseline(db2, plan2, _adapter(1025, 1010), implemented_at=IMPL)
    r2 = meas.run_measurement(db2, plan2, _adapter(1025, 1010), horizon_days=30)
    assert r2.raw_delta > 0 and r2.adjusted_delta > 0
    assert r2.result == "objectif_non_atteint"

    # Écart contrôlé +4 pt ≥ seuil → atteint.
    db3 = FakeDB(); plan3 = _plan(["C1", "C2"])
    meas.freeze_baseline(db3, plan3, _adapter(1050, 1010), implemented_at=IMPL)
    r3 = meas.run_measurement(db3, plan3, _adapter(1050, 1010), horizon_days=30)
    assert r3.result == "objectif_atteint"


def test_protocol_immutable_reject_refreeze():
    """Le protocole figé est IMMUABLE : impossible de re-figer baseline/témoins."""
    db = FakeDB()
    plan = _plan(["C1", "C2"])
    meas.freeze_baseline(db, plan, _adapter(1030, 1045), implemented_at=IMPL)
    with pytest.raises(ValueError):
        meas.freeze_baseline(db, plan, _adapter(1030, 1045), implemented_at=IMPL)


def test_revise_controls_creates_new_version_old_intact():
    """Modifier les témoins après le début de l'observation crée une NOUVELLE version
    explicite (protocol_version + 1) ; l'ancien plan et ses runs restent intacts."""
    db = FakeDB()
    plan = _plan(["C1", "C2"])
    meas.freeze_baseline(db, plan, _adapter(1030, 1045), implemented_at=IMPL)
    r1 = meas.run_measurement(db, plan, _adapter(1030, 1045), horizon_days=30)
    old_ids = list(plan.control_selection["control_ids"])

    successor = meas.revise_plan(db, plan, _adapter(1030, 1045),
                                 control_values=["C1"], implemented_at=IMPL)
    assert successor.id != plan.id
    assert successor.protocol_version == plan.protocol_version + 1
    assert plan.superseded_by_id == successor.id           # l'ancien pointe le successeur
    assert successor.superseded_by_id is None              # le successeur est actif
    # L'ancien plan, sa sélection et son run n'ont pas bougé.
    assert plan.control_selection["control_ids"] == old_ids
    assert r1.plan_id == plan.id
    # La nouvelle version porte les nouveaux témoins.
    assert successor.control_selection["control_ids"] == ["C1"]


def test_candidate_selection_picks_most_comparable():
    """La sélection retient les k candidats les PLUS comparables avant action et
    conserve le motif d'écart des autres (auditable)."""
    db = FakeDB()
    plan = _plan([], control_scope={"candidates": [
        {"id": "C1", "region": "A"}, {"id": "C2", "region": "B"},
        {"id": "C3", "region": "C"}, {"id": "C4", "region": "D"}], "k": 2})
    adapter = FakeAdapter({
        "T1": _flat(1000, 1030), "T2": _flat(1000, 1030),
        "C1": _flat(1000, 1045), "C2": _flat(1010, 1045),   # proches du niveau cible
        "C3": _flat(1300, 1045), "C4": _flat(1400, 1045),   # niveau éloigné
    })
    meas.freeze_baseline(db, plan, adapter, implemented_at=IMPL)
    sel = plan.control_selection
    assert set(sel["control_ids"]) == {"C1", "C2"}
    dropped = [c for c in sel["considered"] if not c["retained"]]
    assert {c["id"] for c in dropped} == {"C3", "C4"}
    assert all(c.get("reason") for c in dropped)            # chaque écarté porte un motif
