"""P0-A — la couverture C6 reflète les termes non résolus de C4.

Les libellés métier ne servent que de corpus d'évaluation : le resolver reste
strictement générique et décide à partir de ``necessity`` et des références.
"""
from __future__ import annotations

import pytest

from app.analysis.capability.adapter import DictCatalogAdapter
from app.analysis.capability.model import S_RESERVE, S_UNRESOLVED
from app.analysis.capability.resolver import resolve
from app.analysis.contracts import ContractError, INTERPRETATION_SCHEMA_VERSION, validate_interpretation


def _context():
    return DictCatalogAdapter().to_context({
        "entities": [{"ref": "concept:subject", "grain_keys": ["subject_id"],
                      "physical": "subjects"}],
        "measures": [{"ref": "metric:value", "home_entity": "concept:subject",
                      "physical": "subjects.value", "data_type": "numeric"}],
        "dimensions": [{"ref": "dimension:group", "home_entity": "concept:subject",
                        "physical": "subjects.group_name", "data_type": "text"}],
        "relations": [],
    })


def _interpretation(term: str, role: str, *, necessity: str = "required", core: bool = True):
    goal = {
        "id": "g1",
        "priority": 1,
        "type": "aggregate",
        "intent_text": f"Analyser {term}",
        "entity_ref": "concept:subject" if core else None,
        "entity_label": None,
        "metrics": ([{"ref": "metric:value", "of_ref": None, "aggregation": "sum"}]
                    if core else []),
        "dimensions": [], "filters": [], "method": None, "depends_on": [],
        "ambiguities": [], "binning_requested": False, "sort": [],
        "limit": None, "temporal": None,
    }
    return validate_interpretation({
        "plan_schema_version": INTERPRETATION_SCHEMA_VERSION,
        "goals": [goal],
        "unresolved_terms": [{
            "goal_id": "g1",
            "term": term,
            "role": role,
            "necessity": necessity,
            "source_span": None,
            "reason": "absent du catalogue",
        }],
    })


@pytest.mark.parametrize(("term", "role"), [
    ("météo", "dimension"),
    ("prix des concurrents", "entity"),
    ("sentiment des avis", "metric"),
    ("prédiction de résiliation", "method"),
])
def test_required_unresolved_term_blocks_full_coverage(term, role):
    resolution, plan = resolve(_interpretation(term, role), _context())

    unresolved = [r for r in resolution.goals[0].requirements if r.kind == "unresolved_term"]
    assert len(unresolved) == 1
    assert unresolved[0].state == S_UNRESOLVED
    assert unresolved[0].necessity == "required"
    assert plan["resolution"][0]["status"] == "UNSUPPORTED"
    assert plan["resolution"][0]["coverage"] == {
        "status": "none",
        "required_unresolved": [{
            "role": role,
            "reason_code": "required_term_unresolved",
        }],
        "optional_unresolved": [],
    }
    assert plan["coherence"] == {
        "covers_question": False,
        "coverage_status": "none",
        "computed_by": "noreon",
        "required_unresolved_count": 1,
        "optional_unresolved_count": 0,
    }


def test_optional_missing_term_allows_explicit_partial_answer_with_resolved_core():
    resolution, plan = resolve(
        _interpretation("contexte externe secondaire", "dimension", necessity="optional"),
        _context(),
    )

    unresolved = [r for r in resolution.goals[0].requirements if r.kind == "unresolved_term"]
    assert unresolved[0].state == S_RESERVE
    assert unresolved[0].necessity == "optional"
    assert plan["resolution"][0]["status"] == "PARTIAL"
    assert plan["resolution"][0]["coverage"] == {
        "status": "partial",
        "required_unresolved": [],
        "optional_unresolved": [{
            "role": "dimension",
            "reason_code": "optional_term_unresolved",
        }],
    }
    assert plan["coherence"]["covers_question"] is False
    assert plan["coherence"]["coverage_status"] == "partial"
    assert plan["coherence"]["optional_unresolved_count"] == 1


def test_optional_cannot_disguise_a_goal_without_resolved_core():
    resolution, plan = resolve(
        _interpretation("contexte manquant", "dimension", necessity="optional", core=False),
        _context(),
    )

    unresolved = [r for r in resolution.goals[0].requirements if r.kind == "unresolved_term"]
    assert unresolved[0].state == S_UNRESOLVED
    assert unresolved[0].necessity == "required"
    assert unresolved[0].reason_code == "optional_term_without_resolved_core"
    assert plan["resolution"][0]["status"] == "UNSUPPORTED"
    assert plan["coherence"]["coverage_status"] == "none"


def test_missing_necessity_is_rejected_in_schema_13():
    payload = {
        "plan_schema_version": INTERPRETATION_SCHEMA_VERSION,
        "goals": [{
            "id": "g1", "priority": 1, "type": "aggregate",
            "intent_text": "Analyser la météo", "entity_ref": "concept:subject",
            "entity_label": None,
            "metrics": [{"ref": "metric:value", "of_ref": None, "aggregation": "sum"}],
            "dimensions": [], "filters": [], "method": None, "depends_on": [],
            "ambiguities": [], "binning_requested": False, "sort": [],
            "limit": None, "temporal": None,
        }],
        "unresolved_terms": [{
            "goal_id": "g1", "term": "météo", "role": "dimension",
            "source_span": None, "reason": None,
        }],
    }
    with pytest.raises(ContractError) as exc:
        validate_interpretation(payload)
    assert exc.value.code == "schema_invalid"
