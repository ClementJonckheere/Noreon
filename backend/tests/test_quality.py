from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.models.profile import ColumnProfile
from app.services.quality import (
    DEFAULT_WEIGHTS,
    _weighted,
    column_quality,
)


def make_profile(**kw) -> ColumnProfile:
    p = ColumnProfile(
        connection_id=1, schema_name="public", table_name="t", column_name="c",
        sampled=False, sample_size=kw.get("sample_size", 1000),
    )
    for k, v in kw.items():
        setattr(p, k, v)
    return p


def test_completeness_exact_detail():
    p = make_profile(null_count=312, non_null_count=39000 - 312, format_checked=None)
    q = column_quality(p, DEFAULT_WEIGHTS, is_pk=False, integrity=None)
    comp = next(d for d in q.dimensions if d.name == "Complétude")
    assert comp.applicable
    assert abs(comp.score - (38688 / 39000)) < 1e-9
    assert "312 NULL sur 39000" in comp.detail


def test_validity_counts_invalid():
    p = make_profile(
        null_count=0, non_null_count=1000, format_checked="email", invalid_count=29,
    )
    q = column_quality(p, DEFAULT_WEIGHTS, is_pk=False, integrity=None)
    val = next(d for d in q.dimensions if d.name == "Validité")
    assert val.applicable
    assert abs(val.score - (1 - 29 / 1000)) < 1e-9
    assert "29 valeur(s) au format email invalide sur 1000" in val.detail


def test_validity_not_applicable_without_format():
    p = make_profile(null_count=0, non_null_count=1000, format_checked=None)
    q = column_quality(p, DEFAULT_WEIGHTS, is_pk=False, integrity=None)
    val = next(d for d in q.dimensions if d.name == "Validité")
    assert val.applicable is False and val.score is None


def test_uniqueness_pk():
    p = make_profile(null_count=0, non_null_count=500, distinct_count=500)
    q = column_quality(p, DEFAULT_WEIGHTS, is_pk=True, integrity=None)
    uni = next(d for d in q.dimensions if d.name == "Unicité")
    assert uni.applicable and uni.score == 1.0
    assert "0 doublon" in uni.detail


def test_uniqueness_not_expected_for_plain_column():
    p = make_profile(null_count=0, non_null_count=500, distinct_count=4, distinct_ratio=0.008)
    q = column_quality(p, DEFAULT_WEIGHTS, is_pk=False, integrity=None)
    uni = next(d for d in q.dimensions if d.name == "Unicité")
    assert uni.applicable is False


def test_consistency_from_integrity():
    p = make_profile(null_count=0, non_null_count=500)
    integ = {"ratio": 0.98, "orphans": 10, "total": 500, "to_table": "public.stores"}
    q = column_quality(p, DEFAULT_WEIGHTS, is_pk=False, integrity=integ)
    coh = next(d for d in q.dimensions if d.name == "Cohérence")
    assert coh.applicable and abs(coh.score - 0.98) < 1e-9
    assert "10 valeur(s) orpheline(s) sur 500 vers public.stores" in coh.detail


def test_freshness_recent_is_full():
    recent = (datetime.now(timezone.utc) - timedelta(days=10)).date().isoformat()
    p = make_profile(null_count=0, non_null_count=500, declared_type="date",
                     detected_type="datetime", max_value=recent)
    q = column_quality(p, DEFAULT_WEIGHTS, is_pk=False, integrity=None)
    fr = next(d for d in q.dimensions if d.name == "Fraîcheur")
    assert fr.applicable and fr.score == 1.0


def test_freshness_old_degrades():
    old = (datetime.now(timezone.utc) - timedelta(days=800)).date().isoformat()
    p = make_profile(null_count=0, non_null_count=500, declared_type="timestamp",
                     detected_type="datetime", max_value=old)
    q = column_quality(p, DEFAULT_WEIGHTS, is_pk=False, integrity=None)
    fr = next(d for d in q.dimensions if d.name == "Fraîcheur")
    assert fr.applicable and fr.score == 0.0


def test_weights_renormalized_over_applicable():
    # Colonne texte libre : seule la Complétude est applicable → score == complétude.
    p = make_profile(null_count=100, non_null_count=900, format_checked=None)
    q = column_quality(p, DEFAULT_WEIGHTS, is_pk=False, integrity=None)
    assert abs(q.score - 0.9) < 1e-9


def test_weighted_helper_handles_all_na():
    from app.services.quality import Dimension

    dims = [Dimension("x", False, None, 0.3, "")]
    assert _weighted(dims) == 1.0
