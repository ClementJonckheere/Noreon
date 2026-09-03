from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class DecisionRecord(Base):
    """Mémoire métier des décisions (boucle d'amélioration continue).

    Journal des recommandations RETENUES, MISES EN ŒUVRE ou dont l'effet a été
    constaté (réussie / abandonnée) par les décideurs. Sert à annoter les
    recommandations futures : « déjà appliquée avec succès dans un contexte
    similaire ». Human-in-the-loop : c'est l'humain qui qualifie le résultat.
    """

    __tablename__ = "decision_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    connection_id: Mapped[int] = mapped_column(
        ForeignKey("connections.id", ondelete="CASCADE"), index=True
    )
    subject: Mapped[str] = mapped_column(String(255), index=True)   # table de faits
    role: Mapped[str] = mapped_column(String(128))
    recommendation: Mapped[str] = mapped_column(String)
    # retained | implemented | successful | abandoned
    status: Mapped[str] = mapped_column(String(16), default="retained")
    note: Mapped[str | None] = mapped_column(String, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
