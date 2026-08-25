"""Phase 2 — C4 : fixtures de contrat FIGÉES (non-régression multi-domaine).

Ces `interpretation_json` de référence (retail, crm, generic) sont le contrat
stable entre le LLM et le reste de Noreon. Elles DOIVENT valider tant que
`INTERPRETATION_SCHEMA_VERSION` ne change pas. Toute rupture de contrat casse ce
test — c'est voulu : un changement de structure exige un bump de version explicite.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.analysis.contracts import (
    GOAL_TYPES,
    INTERPRETATION_SCHEMA_VERSION,
    validate_interpretation,
)

_DIR = Path(__file__).parent / "fixtures" / "interpretations"
_FILES = sorted(_DIR.glob("*.json"))


def _load(path: Path) -> tuple[str, dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    domain = data.pop("domain", "")           # métadonnée de fixture, hors contrat
    return domain, data


def test_fixtures_present():
    assert _FILES, "aucune fixture de contrat trouvée"


@pytest.mark.parametrize("path", _FILES, ids=[p.stem for p in _FILES])
def test_fixture_validates_against_contract(path):
    _domain, payload = _load(path)
    assert payload.get("plan_schema_version") == INTERPRETATION_SCHEMA_VERSION
    interp = validate_interpretation(payload)          # lève si le contrat casse
    assert interp.goals
    for g in interp.goals:
        assert g.type in GOAL_TYPES


def test_fixtures_cover_multiple_domains():
    domains = {_load(p)[0] for p in _FILES}
    assert {"retail", "crm", "generic"} <= domains, f"couverture domaine insuffisante : {domains}"


def test_fixtures_exercise_dependencies_and_unresolved():
    """Au moins une fixture porte un DAG à dépendances ET un terme non résolu."""
    payloads = [_load(p)[1] for p in _FILES]
    assert any(any(g.get("depends_on") for g in pl["goals"]) for pl in payloads)
    assert any(pl.get("unresolved_terms") for pl in payloads)
