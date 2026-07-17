from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


# ---- Connexions ----
class ConnectionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    host: str
    port: int = 5432
    database: str
    username: str
    password: str
    options: dict = Field(default_factory=dict)


class ProbeResult(BaseModel):
    connection_ok: bool
    server_version: str | None = None
    read_only: bool | None = None
    read_only_detail: str | None = None
    error: str | None = None


class ConnectionOut(BaseModel):
    id: int
    name: str
    engine: str
    host: str
    port: int
    database: str
    username: str
    status: str
    is_read_only: bool | None
    read_only_detail: str | None
    last_error: str | None
    last_tested_at: datetime | None
    last_scanned_at: datetime | None
    created_at: datetime

    class Config:
        from_attributes = True


class ConnectionCreateResult(BaseModel):
    connection: ConnectionOut
    probe: ProbeResult
    read_only_alert: str | None = None


# ---- Scan ----
class ScanOut(BaseModel):
    snapshot_id: int
    version: int
    signature: str
    table_count: int
    changed: bool
    message: str


class ColumnOut(BaseModel):
    name: str
    data_type: str
    is_nullable: bool
    is_primary_key: bool

    class Config:
        from_attributes = True


class TableOut(BaseModel):
    id: int
    schema_name: str
    table_name: str
    table_type: str
    estimated_rows: int | None
    columns: list[ColumnOut] = []


class RelationOut(BaseModel):
    id: int
    from_table: str
    from_column: str
    to_table: str
    to_column: str
    kind: str
    status: str
    confidence: float
    cardinality: str | None = None
    integrity_ratio: float | None = None


class RelationReviewIn(BaseModel):
    action: str = Field(..., pattern="^(validate|reject)$")


# ---- Profilage ----
class ProfilingJobOut(BaseModel):
    id: int
    connection_id: int
    scope: str
    status: str
    tables_total: int
    tables_done: int
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    class Config:
        from_attributes = True


class ColumnProfileOut(BaseModel):
    schema_name: str
    table_name: str
    column_name: str
    declared_type: str | None
    detected_type: str | None
    pii_type: str | None
    sampled: bool
    sample_size: int
    null_rate: float | None
    distinct_count: int | None
    min_value: str | None
    max_value: str | None
    mean_value: float | None
    top_values: list = []
    sample_values: list = []

    class Config:
        from_attributes = True


# ---- Qualité ----
class QualityRunOut(BaseModel):
    base_score: float
    tables_scored: int
    columns_scored: int
    relations_scored: int
    computed_at: str


class QualityScoreOut(BaseModel):
    level: str
    schema_name: str | None
    table_name: str | None
    column_name: str | None
    relation_ref: str | None
    score: float
    detail: str
    dimensions: list = []

    class Config:
        from_attributes = True


# ---- Compréhension métier (Module 5) ----
class SemanticProposeOut(BaseModel):
    proposed: int
    updated: int
    kept_human_decisions: int
    arbitrations_needed: int


class ConceptMappingOut(BaseModel):
    id: int
    concept_name: str
    concept_description: str
    schema_name: str
    table_name: str
    column_name: str
    confidence: float
    rationale: str
    status: str
    needs_arbitration: bool
    arbitration_note: str | None
    review_note: str | None
    reviewed_at: datetime | None


class MappingReviewIn(BaseModel):
    action: str = Field(..., pattern="^(validate|reject|correct)$")
    concept_name: str | None = None  # requis pour correct
    note: str | None = None


class ConceptCreateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: str = ""
    synonyms: list[str] = Field(default_factory=list)


class ConceptOut(BaseModel):
    id: int
    name: str
    description: str
    synonyms: list
    origin: str

    class Config:
        from_attributes = True


# ---- Définitions métier réutilisables (V0.4) ----
class DefinitionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    kind: str = Field(..., pattern="^(measure|segment)$")
    schema_name: str = "public"
    table_name: str
    expression: str | None = None  # requis pour measure
    filter_sql: str | None = None  # requis pour segment
    description: str = ""
    source_question: str | None = None


class DefinitionOut(BaseModel):
    id: int
    name: str
    kind: str
    schema_name: str
    table_name: str
    expression: str | None
    filter_sql: str | None
    description: str
    source_question: str | None

    class Config:
        from_attributes = True


# ---- Alertes simples (V0.4) ----
class AlertCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str = ""
    definition_id: int | None = None
    schema_name: str = "public"
    table_name: str | None = None
    expression: str | None = None
    filter_sql: str | None = None
    comparison: str = Field(..., pattern="^(gt|lt|pct_drop|pct_change)$")
    threshold: float


class AlertOut(BaseModel):
    id: int
    name: str
    description: str
    definition_id: int | None
    schema_name: str
    table_name: str | None
    expression: str | None
    filter_sql: str | None
    comparison: str
    threshold: float
    last_value: float | None
    previous_value: float | None
    last_status: str
    last_message: str | None
    last_checked_at: datetime | None

    class Config:
        from_attributes = True


class AlertEventOut(BaseModel):
    id: int
    value: float | None
    status: str
    message: str
    created_at: datetime

    class Config:
        from_attributes = True


# ---- Préférences tenant (V0.4) ----
class PreferencesIn(BaseModel):
    preferred_chart_type: str | None = None
    auto_learn: bool | None = None
    auto_save_definitions: bool | None = None


# ---- Chat ----
class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1)
    run_analysis: bool = True
