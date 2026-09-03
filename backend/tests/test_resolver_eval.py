"""Phase 2 — C6 : verrou du benchmark déterministe du CapabilityResolver.

Le corpus DOIT rester vert : aucune violation de sécurité analytique, tous les
comportements structurants conformes aux attentes, et les signatures identiques
aux snapshots de référence (détection de dérive du resolver).
"""
from __future__ import annotations

from app.analysis.capability import resolver_eval as E


def test_corpus_is_compact_and_multidomain():
    assert 12 <= len(E.CASES) <= 20
    assert {"retail", "saas", "solo"} <= {c.domain for c in E.CASES}


def test_no_analytical_safety_violation():
    rep = E.run_eval()
    assert not rep["eliminated"], f"violations : {rep['violations']}"


def test_all_dimension_rates_are_100pct():
    rep = E.run_eval()
    assert all(rate == 1.0 for rate in rep["dimension_rates"].values()), rep["dimension_rates"]


def test_signatures_match_reference_snapshots():
    rep = E.run_eval()
    assert not rep["snapshot"]["new"], f"cas sans snapshot (lancer --update) : {rep['snapshot']['new']}"
    assert not rep["snapshot"]["changed"], f"DÉRIVE du resolver : {rep['snapshot']['changed']}"


def test_safety_dimensions_are_covered():
    # les comportements dangereux sont bien tous représentés dans le corpus
    safeties = {c.safety for c in E.CASES}
    assert {"fanout", "count_fanout", "non_additive", "semi_additive",
            "unresolved", "invented", "access", "grain_unknown"} <= safeties
