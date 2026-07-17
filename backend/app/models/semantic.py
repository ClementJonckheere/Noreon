from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class BusinessConcept(Base):
    """Concept métier du dictionnaire d'entreprise (Module 5).

    Propre à chaque tenant : c'est la « mémoire entreprise » qui s'enrichit
    des validations et corrections humaines. Exportable (CSV/JSON), il
    constitue un livrable de documentation en soi.
    """

    __tablename__ = "business_concepts"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_concept_tenant_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)

    name: Mapped[str] = mapped_column(String(128))  # ex. « Client », « Montant »
    description: Mapped[str] = mapped_column(String, default="")
    # Synonymes/variantes reconnus (défauts du lexique + ajouts manuels)
    synonyms: Mapped[list] = mapped_column(JSON, default=list)
    # system = issu du lexique Noreon ; user = créé/renommé par l'utilisateur
    origin: Mapped[str] = mapped_column(String(16), default="system")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    mappings: Mapped[list["ConceptMapping"]] = relationship(
        back_populates="concept", cascade="all, delete-orphan"
    )


class ConceptMapping(Base):
    """Proposition de rattachement concept ↔ colonne, avec boucle de validation.

    Statuts (cahier des charges) : proposed / validated / corrected / rejected.
    Une proposition ne devient une vérité métier qu'après validation humaine.
    `needs_arbitration` signale les variantes sémantiques piégeuses (ex.
    net_price HT vs amount TTC) : Noreon demande l'arbitrage au lieu de
    fusionner silencieusement.
    """

    __tablename__ = "concept_mappings"
    __table_args__ = (
        UniqueConstraint(
            "connection_id", "schema_name", "table_name", "column_name", "concept_id",
            name="uq_mapping_column_concept",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    connection_id: Mapped[int] = mapped_column(ForeignKey("connections.id", ondelete="CASCADE"), index=True)
    concept_id: Mapped[int] = mapped_column(ForeignKey("business_concepts.id", ondelete="CASCADE"), index=True)

    schema_name: Mapped[str] = mapped_column(String(255))
    table_name: Mapped[str] = mapped_column(String(255))
    column_name: Mapped[str] = mapped_column(String(255))

    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    # Justification auditable de la proposition (règles déclenchées)
    rationale: Mapped[str] = mapped_column(String, default="")

    status: Mapped[str] = mapped_column(String(16), default="proposed", index=True)
    # proposed | validated | corrected | rejected
    needs_arbitration: Mapped[bool] = mapped_column(Boolean, default=False)
    arbitration_note: Mapped[str | None] = mapped_column(String, default=None)

    reviewed_by: Mapped[str | None] = mapped_column(String(255), default=None)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    review_note: Mapped[str | None] = mapped_column(String, default=None)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    concept: Mapped[BusinessConcept] = relationship(back_populates="mappings")
