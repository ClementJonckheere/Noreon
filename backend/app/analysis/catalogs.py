"""Phase 2 — C3b : catalogues sémantiques VERSIONNÉS (JSON), chargés par le CLI.

Plusieurs domaines (retail complet, retail partiel, CRM, générique, métadonnées
malveillantes) évitent le sur-apprentissage retail du prompt. En C6, le
CapabilityResolver produira EXACTEMENT ce format depuis les vraies connexions —
le benchmark n'a donc pas besoin d'attendre C6.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.analysis.interpreter import PlannerCatalog

_DIR = Path(__file__).resolve().parent / "catalogs"


def list_catalogs() -> list[str]:
    return sorted(p.stem for p in _DIR.glob("*.json"))


def _to_catalog(data: dict) -> PlannerCatalog:
    return PlannerCatalog(
        concepts=list(data.get("concepts") or []),
        metrics=list(data.get("metrics") or []),
        dimensions=list(data.get("dimensions") or []),
        relations=list(data.get("relations") or []),
        stats=dict(data.get("stats") or {}),
        domain=str(data.get("domain") or ""),
    )


def load_catalog(name_or_path: str) -> PlannerCatalog:
    """Charge un catalogue par NOM (fichier versionné) ou par CHEMIN JSON."""
    p = Path(name_or_path)
    if not p.exists():
        p = _DIR / f"{name_or_path}.json"
    if not p.exists():
        raise FileNotFoundError(
            f"Catalogue introuvable : {name_or_path!r}. Disponibles : {list_catalogs()}")
    return _to_catalog(json.loads(p.read_text(encoding="utf-8")))
