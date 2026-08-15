"""Phase 2 — C1 : confidentialité des ENTRÉES du planificateur (Δ6).

Rien de sensible ne doit atteindre le provider :
- la QUESTION utilisateur est pseudonymisée (elle peut contenir email/téléphone/
  IBAN/identifiant) — jetons ré-identifiables localement (compatibles Privacy Engine) ;
- les libellés de métadonnées (noms de tables/colonnes/commentaires issus des
  bases) sont traités comme DONNÉES NON FIABLES : longueur plafonnée, caractères
  de contrôle retirés, tentative d'injection signalée ;
- les agrégats trop petits (k-anonymat) sont supprimés avant affichage/renvoi.
"""
from __future__ import annotations

import re

# Jetons alignés sur le Privacy Engine (`app/services/privacy._TOKEN_RE`).
_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b")
# Téléphone : international « + » ou format national 0X XX XX XX XX (10 chiffres).
# Volontairement strict pour ne pas confondre avec une date (2024-05-31).
_PHONE = re.compile(r"\+\d[\d .\-]{7,}\d|\b0\d(?:[ .\-]?\d\d){4}\b")
_LONGNUM = re.compile(r"\b\d{6,}\b")  # identifiants clients bruts

# Marqueurs d'INJECTION dans une métadonnée issue de la base (jamais une instruction).
_INJECTION = re.compile(
    r"(ignore\s+(all|previous|above)|disregard|system\s*:|assistant\s*:|"
    r"tu es |you are |new instructions|```|</?\s*(system|instruction)|\bprompt\b)",
    re.IGNORECASE,
)

DEFAULT_MIN_GROUP = 5           # k-anonymat par défaut
MAX_LABEL_LEN = 80

# Métadonnées AUTORISÉES à sortir vers le provider (allowlist stricte).
CATALOG_ALLOWLIST = frozenset({
    "entity_ref", "entity_label", "metric_ref", "metric_label",
    "dimension_ref", "dimension_label", "data_type", "unit",
    "relation_ref", "cardinality", "row_count_bucket",
})


def sanitize_question(question: str) -> tuple[str, dict[str, str]]:
    """Remplace les PII de la question par des jetons ré-identifiables localement.
    Retourne (question_sûre, token_map). Ordre : email → IBAN → téléphone → id."""
    token_map: dict[str, str] = {}
    counters = {"EMAIL": 0, "IBAN": 0, "TEL": 0, "PII": 0}

    def _sub(pattern: re.Pattern, prefix: str, text: str) -> str:
        def repl(m: re.Match) -> str:
            counters[prefix] += 1
            tok = f"{prefix}-{counters[prefix]:03d}"
            token_map[tok] = m.group(0)
            return tok
        return pattern.sub(repl, text)

    # Ordre : email → IBAN → téléphone formaté → identifiants bruts (chiffres).
    # Le téléphone (séparateurs) passe avant les runs bruts ; un identifiant nu
    # « 100482173 » tombe donc dans PII, pas dans TEL.
    safe = question or ""
    safe = _sub(_EMAIL, "EMAIL", safe)
    safe = _sub(_IBAN, "IBAN", safe)
    safe = _sub(_PHONE, "TEL", safe)
    safe = _sub(_LONGNUM, "PII", safe)
    return safe, token_map


def scan_injection(text: str) -> bool:
    """Vrai si une métadonnée ressemble à une tentative d'injection d'instructions."""
    return bool(text) and bool(_INJECTION.search(text))


def sanitize_label(name: str, max_len: int = MAX_LABEL_LEN) -> str:
    """Neutralise un libellé issu de la base : retire les caractères de contrôle
    et les sauts de ligne, plafonne la longueur. Reste une DONNÉE, jamais une
    instruction."""
    if not name:
        return ""
    cleaned = re.sub(r"[\x00-\x1f\x7f]+", " ", str(name)).strip()
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rstrip() + "…"
    return cleaned


def suppress_small_groups(rows: list[dict], count_key: str = "n",
                          k: int = DEFAULT_MIN_GROUP) -> list[dict]:
    """k-anonymat : retire les groupes agrégés dont l'effectif est < k (un
    agrégat de 2 clients reste ré-identifiable même sans nom)."""
    return [r for r in rows if isinstance(r.get(count_key), int) and r[count_key] >= k]
