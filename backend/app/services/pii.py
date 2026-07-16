"""Détection de PII (amorce du Privacy Engine — cahier des charges §5.1).

En V0.1, la détection PII est utilisée par le profilage pour marquer les
colonnes sensibles (email, téléphone, IBAN…). L'anonymisation/agrégation
complète avant appel LLM sera formalisée en V0.3 ; l'infrastructure de
détection est posée dès maintenant.
"""
from __future__ import annotations

import re

# Ordre = priorité : les motifs les plus spécifiques passent avant les plus
# larges (ex. SIRET « 14 chiffres exacts » avant le motif téléphone).
_PATTERNS = {
    "email": re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$"),
    "iban": re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9]{10,30}$"),
    "siret": re.compile(r"^\d{14}$"),
    "ipv4": re.compile(r"^(\d{1,3}\.){3}\d{1,3}$"),
    "phone": re.compile(r"^\+?[\d\s().-]{8,20}$"),
    "credit_card": re.compile(r"^\d{13,19}$"),
}

# Indices par nom de colonne (renforce la détection par contenu).
_NAME_HINTS = {
    "email": ("email", "mail", "courriel"),
    "phone": ("phone", "tel", "telephone", "mobile", "gsm"),
    "iban": ("iban", "rib"),
    "siret": ("siret", "siren"),
    "name": ("nom", "name", "prenom", "firstname", "lastname", "surname"),
    "address": ("adresse", "address", "rue", "street"),
}


def detect_by_name(column_name: str) -> str | None:
    low = column_name.lower()
    for pii_type, hints in _NAME_HINTS.items():
        if any(h in low for h in hints):
            return pii_type
    return None


_DATE_LIKE = re.compile(r"^\d{4}-\d{2}-\d{2}([ T].*)?$")


def _is_phone(s: str) -> bool:
    """Un téléphone : format autorisé ET 10 à 15 chiffres (exclut les dates)."""
    if _DATE_LIKE.match(s) or not _PATTERNS["phone"].match(s):
        return False
    digits = re.sub(r"\D", "", s)
    return 10 <= len(digits) <= 15


def detect_by_values(values: list) -> str | None:
    """Retourne le type PII si une majorité des valeurs non nulles correspond."""
    samples = [str(v).strip() for v in values if v is not None and str(v).strip()]
    if not samples:
        return None
    for pii_type, pattern in _PATTERNS.items():
        if pii_type == "credit_card":  # trop ambigu seul, ignoré en heuristique large
            continue
        if pii_type == "phone":
            hits = sum(1 for s in samples if _is_phone(s))
        else:
            hits = sum(1 for s in samples if pattern.match(s) and not _DATE_LIKE.match(s))
        if hits / len(samples) >= 0.8:
            return pii_type
    return None


def detect(column_name: str, values: list) -> str | None:
    return detect_by_values(values) or detect_by_name(column_name)
