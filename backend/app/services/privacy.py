"""Privacy Engine (cahier des charges §5.1).

Pipeline garantissant qu'aucune donnée identifiante brute n'atteint le LLM :

    Résultat SQL → détection PII (profilage) → PSEUDONYMISATION (jetons
    déterministes EMAIL-001, NAME-002…) → LLM (analyse sur données
    pseudonymisées) → RÉ-IDENTIFICATION LOCALE dans le texte produit →
    réponse utilisateur.

- La table de correspondance jeton ↔ valeur réelle ne quitte JAMAIS le
  processus local : le LLM ne voit que les jetons.
- La pseudonymisation (plutôt qu'un simple masquage) préserve la capacité
  d'analyse du LLM : il peut compter, regrouper et référencer les entités
  sans connaître leur identité.
- Chaque réponse expose un audit : colonnes protégées, méthode, volume.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_TOKEN_PREFIX = {
    "email": "EMAIL",
    "phone": "TEL",
    "iban": "IBAN",
    "siret": "SIRET",
    "name": "NOM",
    "address": "ADR",
    "ipv4": "IP",
}

_TOKEN_RE = re.compile(r"\b(?:EMAIL|TEL|IBAN|SIRET|NOM|ADR|IP|PII)-\d{3,}\b")


@dataclass
class PrivacyResult:
    """Résultat du pipeline de protection, avec audit."""

    rows: list[list]                       # lignes sûres pour le LLM
    protected_columns: dict[str, str]      # colonne -> type de PII
    token_map: dict[str, str] = field(default_factory=dict)  # jeton -> valeur réelle (LOCAL)
    values_protected: int = 0

    @property
    def audit(self) -> dict:
        return {
            "engine": "privacy-engine",
            "method": "pseudonymisation" if self.protected_columns else "aucune (pas de PII)",
            "protected_columns": self.protected_columns,
            "values_protected": self.values_protected,
        }


def protect(
    columns: list[str],
    rows: list[list],
    pii_columns: dict[str, str],
) -> PrivacyResult:
    """Pseudonymise les colonnes PII avant tout envoi au LLM.

    Déterministe au sein d'un même résultat : une même valeur reçoit toujours
    le même jeton, ce qui préserve les regroupements pour l'analyse.
    """
    protected = {c: t for c, t in pii_columns.items() if c in columns}
    if not protected:
        return PrivacyResult(rows=rows, protected_columns={})

    col_idx = {c: i for i, c in enumerate(columns)}
    token_map: dict[str, str] = {}       # jeton -> valeur réelle
    value_tokens: dict[tuple[str, str], str] = {}  # (colonne, valeur) -> jeton
    counters: dict[str, int] = {}

    safe_rows: list[list] = []
    for row in rows:
        new_row = list(row)
        for col, pii_type in protected.items():
            i = col_idx[col]
            v = new_row[i]
            if v is None:
                continue
            key = (col, str(v))
            token = value_tokens.get(key)
            if token is None:
                prefix = _TOKEN_PREFIX.get(pii_type, "PII")
                counters[prefix] = counters.get(prefix, 0) + 1
                token = f"{prefix}-{counters[prefix]:03d}"
                value_tokens[key] = token
                token_map[token] = str(v)
            new_row[i] = token
        safe_rows.append(new_row)

    return PrivacyResult(
        rows=safe_rows,
        protected_columns=protected,
        token_map=token_map,
        values_protected=len(token_map),
    )


def reidentify(text: str, token_map: dict[str, str]) -> str:
    """Ré-identification LOCALE : replace les jetons cités par le LLM par les
    valeurs réelles, sans que celles-ci n'aient jamais quitté le processus."""
    if not text or not token_map:
        return text
    return _TOKEN_RE.sub(lambda m: token_map.get(m.group(0), m.group(0)), text)


def reidentify_analysis(analysis: dict | None, token_map: dict[str, str]) -> dict | None:
    """Applique la ré-identification à tous les champs texte d'un rapport."""
    if analysis is None or not token_map:
        return analysis
    out: dict = {}
    for k, v in analysis.items():
        if isinstance(v, str):
            out[k] = reidentify(v, token_map)
        elif isinstance(v, list):
            out[k] = [reidentify(x, token_map) if isinstance(x, str) else x for x in v]
        else:
            out[k] = v
    return out
