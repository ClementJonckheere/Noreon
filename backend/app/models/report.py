"""Rapports (documents) — génération assistée par l'IA, édition, export.

Un rapport est une suite de BLOCS ordonnés (kind : markdown | table | chart).
On peut : demander à l'IA de générer un rapport sur un sujet, ajouter une
réponse de chat (texte, tableau, graphique) comme bloc, éditer chaque bloc
directement, et exporter en Word (.docx), PDF ou Markdown.

Portée : univers (tenant) + auteur ; optionnellement rattaché à un espace.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    space_id: Mapped[int | None] = mapped_column(
        ForeignKey("spaces.id", ondelete="SET NULL"), default=None, index=True
    )
    user_ref: Mapped[str] = mapped_column(String(255), default="", index=True)
    title: Mapped[str] = mapped_column(String(255), default="Nouveau rapport")
    # Source + tables sur lesquelles le rapport s'appuie — pour signaler un
    # « incident postérieur » (réserve qualité apparue après validation) sans
    # jamais réécrire l'instantané publié.
    source_connection_id: Mapped[int | None] = mapped_column(Integer, default=None)
    source_tables: Mapped[list | None] = mapped_column(JSON, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    blocks: Mapped[list["ReportBlock"]] = relationship(
        back_populates="report", cascade="all, delete-orphan",
        order_by="ReportBlock.ordinal",
    )


class ReportBlock(Base):
    __tablename__ = "report_blocks"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer, default=0)
    kind: Mapped[str] = mapped_column(String(16), default="markdown")  # markdown|table|chart
    content: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    report: Mapped[Report] = relationship(back_populates="blocks")


class ReportVersion(Base):
    """Version VALIDÉE d'un rapport — un instantané immuable. Le rapport de
    travail reste éditable ; valider fige une copie (blocs + source + date) qu'on
    peut relire, comparer et sur laquelle se calcule l'« incident postérieur ».
    """

    __tablename__ = "report_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)          # 1, 2, 3…
    title: Mapped[str] = mapped_column(String(255), default="")
    label: Mapped[str | None] = mapped_column(String(255), default=None)  # note de validation
    blocks: Mapped[list] = mapped_column(JSON, default=list)   # copie figée des blocs
    source_connection_id: Mapped[int | None] = mapped_column(Integer, default=None)
    source_tables: Mapped[list | None] = mapped_column(JSON, default=None)
    validated_by: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
