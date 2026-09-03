"""Challenge de l'analyste humain — mesurer la VALEUR de Noreon, pas sa justesse.

Vérifie que, face à une ligne de base humaine, Noreon apporte bien ses avantages
distinctifs (auto-critique, traçabilité, reproductibilité) et répond en quelques
secondes — là où l'humain met ~45 min.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "demo"))

import _runner  # noqa: E402
import human_challenge as hc  # noqa: E402


def test_retail_value_over_human_baseline():
    sc = "retail"
    if not _runner.db_available(sc):
        pytest.skip("base noreon_demo_retail injoignable")
    human = json.loads((ROOT / "demo" / sc / "human_baseline.json").read_text(encoding="utf-8"))
    r, _ = _runner.analyze(sc, human["question"])
    noreon = hc._noreon_profile(r, r.investigation or {}, seconds=1.0)

    # Noreon trouve la cause et recommande, comme l'analyste.
    assert noreon["main_cause"] and noreon["recommendations"]
    # Et il APPORTE ce que l'humain saute en 45 min : rigueur + reproductibilité.
    assert noreon["self_critique"] and noreon["evidence_trail"] and noreon["reproducible"]
    # L'avantage « contexte métier » reste à l'humain (Noreon reste prudent).
    assert human["business_context"] and not noreon["business_context"]
