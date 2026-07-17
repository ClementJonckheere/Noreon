from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class QualityScore(Base):
    """Score qualité auditable (Module 4).

    Un enregistrement par entité notée (colonne, table, relation, base). Le
    détail chiffré de chaque dimension est stocké dans `dimensions` pour être
    toujours vérifiable — jamais de justification générique.
    """

    __tablename__ = "quality_scores"

    id: Mapped[int] = mapped_column(primary_key=True)
    connection_id: Mapped[int] = mapped_column(
        ForeignKey("connections.id", ondelete="CASCADE"), index=True
    )
    level: Mapped[str] = mapped_column(String(16))  # column | table | relation | base

    schema_name: Mapped[str | None] = mapped_column(String(255), default=None)
    table_name: Mapped[str | None] = mapped_column(String(255), default=None)
    column_name: Mapped[str | None] = mapped_column(String(255), default=None)
    relation_ref: Mapped[str | None] = mapped_column(String(512), default=None)

    score: Mapped[float] = mapped_column(Float)  # 0..1

    # Liste de dimensions : {name, applicable, score, weight, detail}
    dimensions: Mapped[list] = mapped_column(JSON, default=list)
    # Résumé chiffré lisible ("Complétude 99,2% (312 NULL sur 39 000)…")
    detail: Mapped[str] = mapped_column(String, default="")

    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
