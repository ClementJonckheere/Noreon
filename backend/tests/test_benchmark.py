"""Non-régression de la bibliothèque de démonstration (Étape 3).

Rejoue chaque scénario et vérifie que le moteur reste au niveau du Gold Standard
(score ≥ seuil). Ignoré scénario par scénario si sa base source est injoignable
(les bases `noreon_demo_<scenario>` se créent via demo/setup_scenario.sh).

C'est le filet de sécurité : si une évolution du moteur dégrade une démonstration,
ce test tombe.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "demo"))

import _runner  # noqa: E402
import benchmark  # noqa: E402

SCENARIOS = list(_runner.SCENARIO_QUESTIONS)


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_scenario_meets_gold_standard(scenario):
    if not _runner.db_available(scenario):
        pytest.skip(f"base noreon_demo_{scenario} injoignable (demo/setup_scenario.sh)")
    exp = json.loads((ROOT / "demo" / scenario / "expected.json").read_text(encoding="utf-8"))
    r, _ = _runner.analyze(scenario, exp["question"])
    rows = benchmark._score(benchmark._extract(r), exp)
    score = sum(w for _, _, w, ok, _ in rows if ok)
    failed = [lbl for _, lbl, _, ok, _ in rows if not ok]
    assert score >= benchmark.PASS_THRESHOLD, (
        f"{scenario} : {score}/100 (seuil {benchmark.PASS_THRESHOLD}) — échecs : {failed}"
    )


def test_challenge_cause_diffuse_is_learned():
    """Challenge « cause diffuse » : le moteur doit reconnaître une baisse
    généralisée (aucun segment disproportionné) et ne PAS produire de tautologie."""
    sc = "challenge/cause_diffuse"
    if not _runner.db_available(sc):
        pytest.skip("base du challenge injoignable")
    exp = json.loads((ROOT / "demo" / sc / "expected.json").read_text(encoding="utf-8"))
    r, _ = _runner.analyze(sc, exp["question"])
    inv = r.investigation or {}
    assert inv.get("broad_based") is True
    assert inv.get("attribution") is None
    assert not inv.get("drivers_struct")  # aucune cause tautologique émise


def test_challenge_opaque_columns_is_robust():
    """Challenge « colonnes opaques » : la mesure est retrouvée PAR LES DONNÉES
    (pas par le nom) et la cause PAR LA VALEUR du segment — preuve que Noreon
    comprend les données, pas seulement le schéma."""
    sc = "challenge/colonnes_opaques_n1"
    if not _runner.db_available(sc):
        pytest.skip("base du challenge injoignable")
    exp = json.loads((ROOT / "demo" / sc / "expected.json").read_text(encoding="utf-8"))
    r, _ = _runner.analyze(sc, exp["question"])
    inv = r.investigation or {}
    attr = inv.get("attribution") or {}
    # Mesure trouvée sans indice de nom (colonnes opaques col_003).
    assert "effectif" not in (inv.get("metric_label") or "").lower()
    # Cause identifiée par la VALEUR du segment, pas par le nom de l'axe.
    assert "provence" in (attr.get("segment") or "").lower()
    assert attr.get("contribution_pct", 0) >= 85


def test_challenge_seasonality_is_recognized():
    """Challenge « saisonnalité » : la baisse récente est un creux annuel. Le moteur
    doit la reconnaître comme SAISONNIÈRE (glissement annuel comparable) et ne
    recommander AUCUNE action corrective."""
    sc = "challenge/saisonnalite"
    if not _runner.db_available(sc):
        pytest.skip("base du challenge injoignable")
    exp = json.loads((ROOT / "demo" / sc / "expected.json").read_text(encoding="utf-8"))
    r, _ = _runner.analyze(sc, exp["question"])
    inv = r.investigation or {}
    assert inv.get("seasonal") is True
    assert "saisonn" in (inv.get("conclusion") or "").lower()
    # Pas d'anomalie → aucune décision corrective.
    assert (r.decisions is None) or not (r.decisions or {}).get("decisions")


def test_challenge_catastrophic_quality_abstains():
    """Challenge « qualité catastrophique » : données trop trouées. Le moteur doit
    S'ABSTENIR (« je ne peux pas conclure ») et ne produire aucune décision."""
    sc = "challenge/qualite_catastrophique"
    if not _runner.db_available(sc):
        pytest.skip("base du challenge injoignable")
    exp = json.loads((ROOT / "demo" / sc / "expected.json").read_text(encoding="utf-8"))
    r, _ = _runner.analyze(sc, exp["question"])
    inv = r.investigation or {}
    assert inv.get("low_quality") is True
    assert "conclure" in (inv.get("conclusion") or "").lower()
    assert (r.decisions is None) or not (r.decisions or {}).get("decisions")


def test_challenge_opaque_columns_n2_infers_relations_by_value():
    """Challenge « colonnes opaques N2 » : colonnes opaques ET aucune FK déclarée.
    La relation vers les régions est inférée par recouvrement de valeurs (P-05),
    et la cause reste identifiée par la valeur du segment."""
    sc = "challenge/colonnes_opaques_n2"
    if not _runner.db_available(sc):
        pytest.skip("base du challenge injoignable")
    exp = json.loads((ROOT / "demo" / sc / "expected.json").read_text(encoding="utf-8"))
    r, _ = _runner.analyze(sc, exp["question"])
    inv = r.investigation or {}
    attr = inv.get("attribution") or {}
    assert "provence" in (attr.get("segment") or "").lower()   # région atteinte SANS FK déclarée
    assert attr.get("contribution_pct", 0) >= 85
