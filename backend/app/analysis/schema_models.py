"""Phase 2 — C2 : modèles Pydantic = SOURCE UNIQUE du contrat structurel.

Ces modèles définissent la structure de `interpretation_json` et génèrent le
**JSON Schema** transmis à OVHcloud (`response_format=json_schema`). Les
validateurs métier (`contracts.py`) s'appliquent APRÈS le parsing pour les
règles relationnelles (DAG, références sémantiques, invariants) et leurs codes
d'erreur précis — ce qu'un JSON Schema ne peut pas exprimer.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.analysis.contracts import GOAL_TYPES, UNRESOLVED_ROLES

_STRICT = ConfigDict(extra="forbid")

# Enums fermés — dérivés des vocabulaires de `contracts` (source unique).
GoalType = Literal[tuple(sorted(GOAL_TYPES))]          # type: ignore[valid-type]
UnresolvedRole = Literal[tuple(sorted(UNRESOLVED_ROLES))]  # type: ignore[valid-type]
UnresolvedNecessity = Literal["required", "optional"]
Aggregation = Literal["sum", "avg", "min", "max", "count", "count_distinct", "none"]
FilterOperator = Literal[
    "eq", "ne", "gt", "gte", "lt", "lte", "in", "not_in", "between",
    "is_null", "is_not_null", "contains", "starts_with", "relative_last",
    "relative_next", "current_period",
]
ValueType = Literal["string", "integer", "number", "boolean", "date", "datetime", "null"]
SortDirection = Literal["asc", "desc"]
NullsOrder = Literal["first", "last"]
TemporalGrain = Literal["hour", "day", "week", "month", "quarter", "year"]


class MetricIn(BaseModel):
    model_config = _STRICT
    ref: str
    of_ref: Optional[str] = None
    aggregation: Aggregation = "sum"


class DimensionIn(BaseModel):
    model_config = _STRICT
    ref: str


class MethodIn(BaseModel):
    model_config = _STRICT
    name: str
    version: str = "1.0"
    params: dict = Field(default_factory=dict)


class FilterIn(BaseModel):
    model_config = _STRICT
    ref: str
    operator: FilterOperator
    value_type: ValueType
    value: Any
    conjunction: Literal["and", "or"] = "and"


class SortIn(BaseModel):
    model_config = _STRICT
    ref: str
    direction: SortDirection
    nulls: NullsOrder = "last"


class TemporalIn(BaseModel):
    model_config = _STRICT
    dimension_ref: str
    grain: TemporalGrain
    timezone: str = Field(default="UTC", min_length=1)


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
    filters: list[FilterIn] = Field(default_factory=list)
    method: Optional[MethodIn] = None
    depends_on: list[str] = Field(default_factory=list)
    ambiguities: list[dict] = Field(default_factory=list)
    binning_requested: bool = False
    sort: list[SortIn] = Field(default_factory=list)
    limit: Optional[int] = Field(default=None, ge=1, le=10000)
    temporal: Optional[TemporalIn] = None


class UnresolvedTermIn(BaseModel):
    model_config = _STRICT
    goal_id: str
    term: str = Field(min_length=1)
    role: UnresolvedRole
    necessity: UnresolvedNecessity = "required"
    source_span: Optional[str] = None
    reason: Optional[str] = None


class InterpretationDoc(BaseModel):
    """Contrat structurel de la sortie LLM. `model_json_schema()` est le schéma
    envoyé au provider."""
    model_config = _STRICT
    plan_schema_version: Literal["1.2"]
    goals: list[GoalIn] = Field(min_length=1)
    unresolved_terms: list[UnresolvedTermIn] = Field(default_factory=list)


def interpretation_json_schema() -> dict:
    """JSON Schema (draft 2020-12) transmis à OVHcloud pour contraindre la sortie.

    Estampillé des DEUX versions (structure + vocabulaire) pour la traçabilité."""
    from app.analysis.contracts import GOAL_TYPES_VERSION, INTERPRETATION_SCHEMA_VERSION
    schema = InterpretationDoc.model_json_schema()
    schema["title"] = (f"interpretation_json v{INTERPRETATION_SCHEMA_VERSION} "
                       f"(types v{GOAL_TYPES_VERSION})")
    schema["x-noreon-schema-version"] = INTERPRETATION_SCHEMA_VERSION
    schema["x-noreon-goal-types-version"] = GOAL_TYPES_VERSION
    return schema
