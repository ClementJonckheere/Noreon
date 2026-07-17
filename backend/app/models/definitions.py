from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class BusinessDefinition(Base):
    """Définition métier réutilisable (Module 7, V0.4).

    Deux natures :
    - **mesure** (measure) : une expression d'agrégat nommée, ex.
      « CA » = sum(amount_ttc) sur la table orders. Réutilisable dans les
      questions (« CA par mois », « CA par magasin »).
    - **segment** : une population définie par un filtre, ex.
      « client fidèle » = clients ayant ≥ 3 commandes sur 12 mois
      (filtre appliqué à la table de référence).

    Ces définitions constituent la mémoire métier réutilisable de l'entreprise
    et peuvent être capturées depuis une clarification du chat.
    """

    __tablename__ = "business_definitions"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_definition_tenant_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)

    name: Mapped[str] = mapped_column(String(128))          # « CA », « client fidèle »
    kind: Mapped[str] = mapped_column(String(16))           # measure | segment
    schema_name: Mapped[str] = mapped_column(String(255), default="public")
    table_name: Mapped[str] = mapped_column(String(255))    # table de référence

    # mesure : expression d'agrégat SQL (ex. "sum(amount_ttc)")
    expression: Mapped[str | None] = mapped_column(String, default=None)
    # segment (et filtre optionnel d'une mesure) : condition SQL (clause WHERE)
    filter_sql: Mapped[str | None] = mapped_column(String, default=None)

    description: Mapped[str] = mapped_column(String, default="")
    source_question: Mapped[str | None] = mapped_column(String, default=None)
    created_by: Mapped[str] = mapped_column(String(255), default="user")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
