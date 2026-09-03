"""Substrat GÉNÉRIQUE de la propagation (E1) et de l'audit d'arbitrage.

Aucun domaine ici : un `ConceptReference` dit seulement qu'un artefact (réponse,
découverte, rapport) s'appuie sur un concept ; un `ConceptArbitration` trace une
décision d'arbitrage et ses effets. Valable à l'identique pour « Magasin actif »
(Démo Retail) ou « Client actif » (SaaS).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ConceptReference(Base):
    """Un artefact qui S'APPUIE sur un concept — le registre que la propagation
    (E1) parcourt. `kind` est générique : answer | discovery | report."""

    __tablename__ = "concept_references"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    concept_id: Mapped[int] = mapped_column(ForeignKey("business_concepts.id", ondelete="CASCADE"), index=True)

    kind: Mapped[str] = mapped_column(String(24))          # answer | discovery | report
    ref_label: Mapped[str] = mapped_column(String(255), default="")
    ref_id: Mapped[str | None] = mapped_column(String(64), default=None)
    connection_id: Mapped[int | None] = mapped_column(Integer, default=None)
    # Un artefact IMMUABLE (rapport validé/figé) n'est jamais réécrit : il est
    # CONSERVÉ tel quel, avec une mention. Les autres sont recalculés / à revérifier.
    immutable: Mapped[bool] = mapped_column(Boolean, default=False)
    # active → (stale | en_reverification | preserved) après propagation.
    status: Mapped[str] = mapped_column(String(24), default="active", index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ConceptArbitration(Base):
    """Entrée d'AUDIT d'un arbitrage : quelle définition est devenue référence, à
    quelle version, par qui, et les effets de propagation constatés."""

    __tablename__ = "concept_arbitrations"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    concept_id: Mapped[int] = mapped_column(ForeignKey("business_concepts.id", ondelete="CASCADE"), index=True)
    chosen_definition_id: Mapped[int] = mapped_column(Integer)
    definition_version: Mapped[int] = mapped_column(Integer)
    actor: Mapped[str | None] = mapped_column(String(255), default=None)
    propagation: Mapped[dict] = mapped_column(JSON, default=dict)   # effets E1 constatés

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
