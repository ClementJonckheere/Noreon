"""Relation candidate entre deux champs — primitive GÉNÉRIQUE, comme ConceptDefinition.

Une relation n'est jamais « order.product_id → product.id » en dur : c'est un lien
entre deux `FieldReference` arbitraires, évalué sur des faits (couverture, unicité
de la cible, compatibilité de type, cardinalité, exceptions) et daté (fenêtre
vérifiée). Le moteur ne connaît aucun domaine — il fonctionne à l'identique pour
« sales.article_reference → articles.reference » (Retail) ou
« subscriptions.account_id → accounts.id » (SaaS).

ORIGINE (statut épistémique, comme inferred | declared | validated) :
  constraint — une vraie FK/contrainte déclarée par la base (preuve la plus forte),
  inferred   — inférée par les valeurs (couverture, unicité…),
  declared   — déclarée par l'utilisateur.
STATUTS : candidate → needs_validation → validated | archived | rejected.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class RelationCandidate(Base):
    __tablename__ = "relation_candidates"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    connection_id: Mapped[int] = mapped_column(Integer, index=True)

    # FieldReference (aplati) — schéma optionnel, table + colonne des deux côtés.
    left_schema: Mapped[str] = mapped_column(String(255), default="public")
    left_table: Mapped[str] = mapped_column(String(255))
    left_column: Mapped[str] = mapped_column(String(255))
    right_schema: Mapped[str] = mapped_column(String(255), default="public")
    right_table: Mapped[str] = mapped_column(String(255))
    right_column: Mapped[str] = mapped_column(String(255))

    direction: Mapped[str] = mapped_column(String(16), default="left_to_right")
    cardinality: Mapped[str | None] = mapped_column(String(16), default=None)   # n-1 | 1-1 | 1-n | n-n

    # Faits mesurés (jamais la seule couverture).
    coverage: Mapped[float | None] = mapped_column(Float, default=None)          # part de gauche rattachée
    target_uniqueness: Mapped[float | None] = mapped_column(Float, default=None) # unicité de la clé cible
    type_compatibility: Mapped[str | None] = mapped_column(String(24), default=None)  # conforme|partielle|incompatible
    exceptions_count: Mapped[int | None] = mapped_column(Integer, default=None)
    exceptions_note: Mapped[str | None] = mapped_column(String, default=None)    # « toutes antérieures à… »

    # « Pourquoi cette colonne et pas une autre ? » : candidats alternatifs évalués.
    alternatives: Mapped[list | None] = mapped_column(JSON, default=None)        # [{table,column,coverage}]

    origin: Mapped[str] = mapped_column(String(16), default="inferred")          # constraint|inferred|declared

    # Fraîcheur + temporalité (une relation évolue avec le SI).
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    snapshot_id: Mapped[str | None] = mapped_column(String(128), default=None)
    source_ids: Mapped[list | None] = mapped_column(JSON, default=None)
    valid_from: Mapped[date | None] = mapped_column(Date, default=None)          # « vérifiée depuis… »
    valid_to: Mapped[date | None] = mapped_column(Date, default=None)

    status: Mapped[str] = mapped_column(String(20), default="candidate", index=True)
    # candidate | needs_validation | validated | archived | rejected
    validated_by: Mapped[str | None] = mapped_column(String(255), default=None)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    validation_window: Mapped[dict | None] = mapped_column(JSON, default=None)   # {from,to} figée à la validation
    evidence: Mapped[dict | None] = mapped_column(JSON, default=None)            # faits figés à la validation

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
