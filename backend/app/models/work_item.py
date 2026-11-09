"""Notifications — deux primitives GÉNÉRIQUES du produit, jamais un système par métier.

`WorkItem`  : quelque chose qui EXIGE une action (arbitrer un concept, valider une
              relation, valider un rapport…). Sa résolution est un état MÉTIER,
              indépendant de la lecture (`read_at` ≠ `status`).
`ActivityEvent` : quelque chose qui INFORME (mesure terminée, incident résolu…) et
              ne demande aucune décision.

Les `kind` sont des primitives de Noreon (concept_arbitration, relation_validation…),
pas des notions Retail — c'est conforme à la règle domain-agnostic. L'assignation
dépend d'une CAPABILITY, jamais d'un rôle codé en dur : elle marche pour un
entrepreneur seul (qui possède les capacités) comme pour une organisation.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class WorkItem(Base):
    __tablename__ = "work_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)

    # Primitives produit — pas de notion métier.
    kind: Mapped[str] = mapped_column(String(32), index=True)
    # concept_arbitration | relation_validation | quality_review |
    # access_approval | measurement_due | report_validation
    object_type: Mapped[str] = mapped_column(String(32))
    object_id: Mapped[str] = mapped_column(String(64))

    space_id: Mapped[int | None] = mapped_column(Integer, default=None)      # None = niveau Univers
    assignee_id: Mapped[int | None] = mapped_column(Integer, default=None)
    # Assignation par CAPABILITY (jamais par rôle codé en dur).
    required_capability: Mapped[str | None] = mapped_column(String(48), default=None)

    status: Mapped[str] = mapped_column(String(16), default="a_traiter", index=True)
    # a_traiter | reporte | traite | clos
    title: Mapped[str] = mapped_column(String(255), default="")
    reason: Mapped[str] = mapped_column(String, default="")

    # LECTURE ≠ RÉSOLUTION : lire ne vide jamais « À traiter ».
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ActivityEvent(Base):
    __tablename__ = "activity_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)

    kind: Mapped[str] = mapped_column(String(32), index=True)
    object_type: Mapped[str] = mapped_column(String(32))
    object_id: Mapped[str] = mapped_column(String(64))
    space_id: Mapped[int | None] = mapped_column(Integer, default=None)

    title: Mapped[str] = mapped_column(String(255), default="")
    detail: Mapped[str] = mapped_column(String, default="")

    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
