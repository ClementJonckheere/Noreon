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
    from_table: str
    from_column: str
    to_table: str
    to_column: str
    kind: str
    status: str
    confidence: float


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


# ---- Chat ----
class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1)
    run_analysis: bool = True
