from __future__ import annotations

from app.services import pii


def test_detect_email_by_value():
    assert pii.detect("x", ["a@b.com", "c.d@e.fr", "foo@bar.io"]) == "email"


def test_detect_email_by_name():
    assert pii.detect_by_name("client_email") == "email"


def test_detect_iban():
    assert pii.detect("compte", ["FR7630006000011234567890189"]) == "iban"


def test_detect_siret():
    assert pii.detect_by_values(["12345678901234", "98765432109876"]) == "siret"


def test_non_pii_returns_none():
    assert pii.detect("amount", [1, 2, 3]) is None


def test_dates_not_flagged_as_phone():
    assert pii.detect("signup_date", ["2024-05-01", "2023-11-12", "2024-01-30"]) is None


def test_real_phone_detected():
    assert pii.detect("tel", ["+33600001234", "+33611112222", "0612345678"]) == "phone"


def test_name_hint_for_person_name():
    assert pii.detect_by_name("nom_client") == "name"
