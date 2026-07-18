from __future__ import annotations

from app.models.profile import ColumnProfile
from app.services.semantic import Proposal, _apply_learning


def _profile(table, column):
    return ColumnProfile(
        connection_id=2, schema_name="public", table_name=table, column_name=column,
        sampled=False, sample_size=1,
    )


def test_learning_overrides_divergent_proposal():
    # L'analyse locale propose « Client » pour 'ref', mais le tenant a validé
    # ailleurs que 'ref' = « Contrat ». La mémoire prime.
    profiles = [_profile("deals", "ref")]
    proposals = [Proposal("Client", "public", "deals", "ref", 0.7, "nom évocateur")]
    learned = {"ref": ("Contrat", 3)}
    out = _apply_learning(proposals, profiles, learned)
    p = next(x for x in out if x.column_name == "ref")
    assert p.concept_name == "Contrat"
    assert "appris de 3" in p.rationale


def test_learning_reinforces_matching_proposal():
    profiles = [_profile("customers", "email")]
    proposals = [Proposal("Email", "public", "customers", "email", 0.8, "pii email")]
    learned = {"email": ("Email", 2)}
    out = _apply_learning(proposals, profiles, learned)
    p = next(x for x in out if x.column_name == "email")
    assert p.concept_name == "Email"
    assert p.confidence > 0.8
    assert "renforcé" in p.rationale


def test_learning_creates_missing_proposal():
    # Colonne sans proposition locale mais connue de la mémoire tenant.
    profiles = [_profile("invoices", "siret_client")]
    proposals: list[Proposal] = []
    learned = {"siret_client": ("SIRET", 1)}
    out = _apply_learning(proposals, profiles, learned)
    assert any(p.column_name == "siret_client" and p.concept_name == "SIRET" for p in out)


def test_no_learning_leaves_proposals_untouched():
    profiles = [_profile("customers", "email")]
    proposals = [Proposal("Email", "public", "customers", "email", 0.8, "pii email")]
    out = _apply_learning(proposals, profiles, {})
    assert out[0].confidence == 0.8
