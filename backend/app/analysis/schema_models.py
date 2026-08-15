"""Phase 2 — C2 : modèles Pydantic = SOURCE UNIQUE du contrat structurel.

Ces modèles définissent la structure de `interpretation_json` et génèrent le
**JSON Schema** transmis à OVHcloud (`response_format=json_schema`). Les
validateurs métier (`contracts.py`) s'appliquent APRÈS le parsing pour les
règles relationnelles (DAG, références sémantiques, invariants) et leurs codes
d'erreur précis — ce qu'un JSON Schema ne peut pas exprimer.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.analysis.contracts import GOAL_TYPES, UNRESOLVED_ROLES

_STRICT = ConfigDict(extra="forbid")

# Enums fermés — dérivés des vocabulaires de `contracts` (source unique).
GoalType = Literal[tuple(sorted(GOAL_TYPES))]          # type: ignore[valid-type]
UnresolvedRole = Literal[tuple(sorted(UNRESOLVED_ROLES))]  # type: ignore[valid-type]


class MetricIn(BaseModel):
    model_config = _STRICT
    ref: str
    of_ref: Optional[str] = None


class DimensionIn(BaseModel):
    model_config = _STRICT
    ref: str


class MethodIn(BaseModel):
    model_config = _STRICT
    name: str
    params: dict = Field(default_factory=dict)


class GoalIn(BaseModel):
    model_config = _STRICT
    id: str = Field(min_length=1)
    priority: int = Field(ge=1)
    type: GoalType
    intent_text: str = Field(min_length=1)
    entity_ref: Optional[str] = None
    entity_label: Optional[str] = None
    metrics: list[MetricIn] = Field(default_factory=list)
    dimensions: list[DimensionIn] = Field(default_factory=list)
    filters: list[dict] = Field(default_factory=list)
    method: Optional[MethodIn] = None
    depends_on: list[str] = Field(default_factory=list)
    ambiguities: list[dict] = Field(default_factory=list)
    binning_requested: bool = False


class UnresolvedTermIn(BaseModel):
    model_config = _STRICT
    goal_id: str
    term: str = Field(min_length=1)
    role: UnresolvedRole
    source_span: Optional[str] = None
    reason: Optional[str] = None


class InterpretationDoc(BaseModel):
    """Contrat structurel de la sortie LLM. `model_json_schema()` est le schéma
    envoyé au provider."""
    model_config = _STRICT
    plan_schema_version: Literal["1.0"]
    goals: list[GoalIn] = Field(min_length=1)
    unresolved_terms: list[UnresolvedTermIn] = Field(default_factory=list)


def interpretation_json_schema() -> dict:
    """JSON Schema (draft 2020-12) transmis à OVHcloud pour contraindre la sortie."""
    return InterpretationDoc.model_json_schema()
