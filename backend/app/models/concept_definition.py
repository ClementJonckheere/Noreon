"""Définitions concurrentes d'un concept métier — substrat GÉNÉRIQUE d'arbitrage.

Un même concept métier (« Client actif », « Magasin actif », « Commande valide »…)
peut avoir plusieurs définitions plausibles. L'objet arbitré est un CONCEPT, jamais
un magasin/client/produit : ce modèle ne connaît aucun domaine. Une définition
porte une requête de COMPTAGE auditable (`count_sql`) que le moteur exécute pour
mesurer l'impact — sans interpréter la moindre sémantique métier.

    Concept « Client actif »
      Définition A  — a acheté au cours des 12 derniers mois   → 4 218 entités
      Définition B  — s'est connecté dans les 90 derniers jours → 6 032 entités
      Définition C  — possède un abonnement en cours            → …

Statuts : candidate → validated (référence) | needs_arbitration | archived.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class ConceptDefinition(Base):
    __tablename__ = "concept_definitions"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    concept_id: Mapped[int] = mapped_column(ForeignKey("business_concepts.id", ondelete="CASCADE"), index=True)

    # Portée : tout l'univers (tenant) ou un espace précis. Générique.
    scope: Mapped[str] = mapped_column(String(16), default="universe")   # universe | space
    space_id: Mapped[int | None] = mapped_column(Integer, default=None)

    label: Mapped[str] = mapped_column(String(255))          # « A », « acheté 12 mois »…
    definition_text: Mapped[str] = mapped_column(String, default="")   # définition humaine
    # Requête de COMPTAGE d'entités (auditable). Le moteur l'exécute telle quelle.
    count_sql: Mapped[str | None] = mapped_column(String, default=None)
    # Libellé d'entité, POUR L'AFFICHAGE seulement (issu des données : « clients »,
    # « magasins »…). Jamais une primitive de logique.
    entity_label: Mapped[str] = mapped_column(String(64), default="entités")

    definition_version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(24), default="candidate", index=True)
    # candidate | validated | needs_arbitration | archived
    is_reference: Mapped[bool] = mapped_column(Boolean, default=False)
    impact_count: Mapped[int | None] = mapped_column(Integer, default=None)  # dernier comptage
    # Fraîcheur du comptage : QUAND il a été calculé, sur QUEL snapshot et QUELLES
    # sources. Permet d'afficher « calculé il y a 22 h » et de bloquer un arbitrage
    # sur un impact devenu obsolète (les données ont changé depuis le preview).
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    snapshot_id: Mapped[str | None] = mapped_column(String(128), default=None)
    source_ids: Mapped[list | None] = mapped_column(JSON, default=None)   # connexions sources

    rationale: Mapped[str] = mapped_column(String, default="")
    owner_ref: Mapped[str | None] = mapped_column(String(255), default=None)  # ActorReference (libre)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    concept: Mapped["BusinessConcept"] = relationship()  # noqa: F821
