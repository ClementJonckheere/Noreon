from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class SchemaSnapshot(Base):
    """Version des métadonnées d'une connexion (Module 2 : versionnement).

    Chaque scan produit un snapshot avec une signature. Le scan incrémental
    compare les signatures pour ne créer un nouveau snapshot que si le schéma
    a changé.
    """

    __tablename__ = "schema_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    connection_id: Mapped[int] = mapped_column(ForeignKey("connections.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    signature: Mapped[str] = mapped_column(String(64))  # sha256 du schéma
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    table_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    tables: Mapped[list["DbTable"]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan"
    )
    relations: Mapped[list["DbRelation"]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan"
    )


class DbTable(Base):
    __tablename__ = "db_tables"

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("schema_snapshots.id", ondelete="CASCADE"), index=True)
    schema_name: Mapped[str] = mapped_column(String(255))
    table_name: Mapped[str] = mapped_column(String(255))
    table_type: Mapped[str] = mapped_column(String(32), default="table")  # table|view
    estimated_rows: Mapped[int | None] = mapped_column(default=None)
    comment: Mapped[str | None] = mapped_column(String, default=None)

    snapshot: Mapped[SchemaSnapshot] = relationship(back_populates="tables")
    columns: Mapped[list["DbColumn"]] = relationship(
        back_populates="table", cascade="all, delete-orphan"
    )

    @property
    def fqtn(self) -> str:
        return f"{self.schema_name}.{self.table_name}"


class DbColumn(Base):
    __tablename__ = "db_columns"

    id: Mapped[int] = mapped_column(primary_key=True)
    table_id: Mapped[int] = mapped_column(ForeignKey("db_tables.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    ordinal: Mapped[int] = mapped_column(Integer)
    data_type: Mapped[str] = mapped_column(String(128))
    is_nullable: Mapped[bool] = mapped_column(Boolean, default=True)
    default_value: Mapped[str | None] = mapped_column(String, default=None)
    is_primary_key: Mapped[bool] = mapped_column(Boolean, default=False)
    comment: Mapped[str | None] = mapped_column(String, default=None)

    table: Mapped[DbTable] = relationship(back_populates="columns")


class DbRelation(Base):
    """Relation entre tables (Module 2 + Knowledge Graph).

    `kind` : declared (FK déclarée) | inferred (convention xxx_id) | validated
    (confirmée par l'utilisateur — boucle human-in-the-loop, V0.2).
    """

    __tablename__ = "db_relations"

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("schema_snapshots.id", ondelete="CASCADE"), index=True)
    from_schema: Mapped[str] = mapped_column(String(255))
    from_table: Mapped[str] = mapped_column(String(255))
    from_column: Mapped[str] = mapped_column(String(255))
    to_schema: Mapped[str] = mapped_column(String(255))
    to_table: Mapped[str] = mapped_column(String(255))
    to_column: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(16), default="declared")
    status: Mapped[str] = mapped_column(String(16), default="proposed")  # proposed|validated|rejected
    confidence: Mapped[float] = mapped_column(default=1.0)
    cardinality: Mapped[str | None] = mapped_column(String(16), default=None)  # 1-1|1-n|n-n
    integrity_ratio: Mapped[float | None] = mapped_column(default=None)  # 1 - taux d'orphelins
    details: Mapped[dict] = mapped_column(JSON, default=dict)

    snapshot: Mapped[SchemaSnapshot] = relationship(back_populates="relations")
