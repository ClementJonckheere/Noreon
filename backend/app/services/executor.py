"""Compat : l'exécution avec garde-fous vit désormais dans SourceAdapter.run_query
(app/services/sources/base.py), commune à tous les moteurs. Ce module ré-exporte
les symboles pour les imports existants."""
from __future__ import annotations

from app.services.sources.base import CostThresholdExceeded, ExecutionResult

__all__ = ["CostThresholdExceeded", "ExecutionResult"]
