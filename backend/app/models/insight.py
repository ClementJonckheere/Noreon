from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class InsightBaseline(Base):
    """Dernier relevé d'Insights connu pour une connexion (rapports comparables).

    Stocke l'ensemble des « clés » d'insights du dernier calcul, pour dire au
    calcul suivant ce qui est NOUVEAU, CORRIGÉ ou CONFIRMÉ depuis. Une seule ligne
    par connexion (mise à jour à chaque nouveau relevé).
    """

    __tablename__ = "insight_baselines"

    connection_id: Mapped[int] = mapped_column(
        ForeignKey("connections.id", ondelete="CASCADE"), primary_key=True
    )
    keys: Mapped[list] = mapped_column(JSON, default=list)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
