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
