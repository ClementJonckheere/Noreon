from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ReasoningMemory(Base):
    """Mémoire du moteur de raisonnement : efficacité passée d'une dimension /
    chaîne de jointures pour un sujet donné.

    L'agent apprend quelles stratégies (« orders → customers → stores », « par
    ville »…) portent le plus de signal, et les teste EN PRIORITÉ la fois
    suivante. `effectiveness` est une moyenne mobile exponentielle du « power »
    observé lors des segmentations.
    """

    __tablename__ = "reasoning_memory"

    connection_id: Mapped[int] = mapped_column(
        ForeignKey("connections.id", ondelete="CASCADE"), primary_key=True
    )
    subject_table: Mapped[str] = mapped_column(String(255), primary_key=True)
    dimension_label: Mapped[str] = mapped_column(String(255), primary_key=True)

    effectiveness: Mapped[float] = mapped_column(Float, default=0.0)
    observations: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
