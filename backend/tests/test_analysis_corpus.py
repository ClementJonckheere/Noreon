"""Phase 2 — C3b : corpus (≥50 cas, splits, domaines) + catalogues versionnés."""
from __future__ import annotations

import pytest

from app.analysis import benchmark as B
from app.analysis.catalogs import list_catalogs, load_catalog
from app.analysis.eval_cases import CASES, COMPLEX_CASES, DEVELOPMENT, HOLDOUT, SIMPLE_CASES
from app.analysis.interpreter import build_user_prompt
from app.analysis.planner_privacy import scan_injection

_REF_PREFIXES = {"concept", "metric", "dimension"}


def test_corpus_has_at_least_50_unique_cases():
    assert len(CASES) >= 50
    ids = [c.id for c in CASES]
    assert len(ids) == len(set(ids)), "identifiants de cas dupliqués"
    questions = [c.question.strip().lower() for c in CASES]
    assert len(questions) == len(set(questions)), "questions dupliquées"


def test_corpus_has_splits_tiers_and_domains():
    assert DEVELOPMENT and HOLDOUT, "besoin d'un split development/holdout"
    assert SIMPLE_CASES and COMPLEX_CASES, "besoin de cas simples ET complexes"
    domains = {c.domain for c in CASES}
    assert {"retail", "crm", "generic"} <= domains
    # les deux splits contiennent des cas simples ET complexes (représentativité)
    for split in (DEVELOPMENT, HOLDOUT):
        tiers = {c.simple_eligible for c in split}
        assert tiers == {True, False}


@pytest.mark.parametrize("name", ["retail_full", "retail_partial", "crm", "generic", "injection"])
def test_catalog_loads_and_refs_wellformed(name):
    assert name in list_catalogs()
    cat = load_catalog(name)
    assert cat.concepts and cat.metrics
    refs = B.catalog_refs(cat)
    assert refs, "aucune référence sémantique extraite"
    for r in refs:
        assert r.split(":", 1)[0] in _REF_PREFIXES


def test_partial_catalog_lacks_age_and_one_relation():
    full = load_catalog("retail_full")
    partial = load_catalog("retail_partial")
    full_refs, partial_refs = B.catalog_refs(full), B.catalog_refs(partial)
    assert "dimension:age" in full_refs and "dimension:age" not in partial_refs
    full_rel = {r["relation_ref"] for r in full.relations}
    partial_rel = {r["relation_ref"] for r in partial.relations}
    assert "order_items_products" in full_rel and "order_items_products" not in partial_rel


def test_injection_catalog_metadata_is_detected_and_flagged():
    cat = load_catalog("injection")
    labels = [v for grp in (cat.concepts, cat.metrics) for e in grp for v in e.values()
              if isinstance(v, str)]
    assert any(scan_injection(x) for x in labels), "l'injection devrait être détectée"
    # le prompt construit SIGNALE la neutralisation (données, jamais instructions)
    prompt = build_user_prompt(cat, "combien de clients")
    assert "neutralis" in prompt.lower()
