"""Responsibility Engine — du CONCEPT métier au DÉCIDEUR, GÉNÉRIQUEMENT.

Ce composant ne connaît AUCUN domaine. Il reçoit un `BusinessContext` (qui peut
être vide) et tente d'associer un Finding — un axe d'analyse et ses valeurs — à
une `Responsibility` connue de ce contexte :

    Finding (axe + valeurs)
      → le BusinessContext connaît-il une Responsibility pour cet axe ?
        → oui : décideur + action-type (personnalisation)
        → non : aucun responsable connu → recommandation générique (côté moteur)

Détecter par la VALEUR d'abord (et non par le nom) rend le routage robuste aux
colonnes opaques — mais les ensembles de valeurs et les rôles vivent dans le
contexte déclaré, pas ici (P-01). Sans contexte, `resolve` renvoie toujours None.
"""
from __future__ import annotations

from app.services.business_context import BusinessContext, Responsibility


def resolve(context: BusinessContext, dimension_label: str, segment: str | None = None,
            samples: list[str] | None = None) -> Responsibility | None:
    """Responsabilité connue du contexte pour cet axe, sinon None (→ générique)."""
    return context.resolve_responsibility(dimension_label, segment, samples)
