"""Définitions métier réutilisables (Module 7, V0.4).

Une définition nomme un calcul (mesure) ou une population (segment) une fois,
puis est réutilisée dans toutes les analyses. Elle est injectée dans le
contexte du moteur SQL, qui sait alors résoudre « CA par mois » ou
« combien de clients fidèles ».
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.definitions import BusinessDefinition


def list_definitions(db: Session, tenant_id: int) -> list[BusinessDefinition]:
    return db.execute(
        select(BusinessDefinition).where(BusinessDefinition.tenant_id == tenant_id)
        .order_by(BusinessDefinition.kind, BusinessDefinition.name)
    ).scalars().all()


def definitions_context(db: Session, tenant_id: int) -> str:
    """Bloc texte des définitions, lisible par le LLM et le moteur heuristique.

    Format (parsé par app/llm/heuristic._parse_definitions) :

        Définitions métier réutilisables :
          Mesure CA = sum(amount_ttc) sur public.orders
          Segment client fidèle sur public.customers filtre: id IN (…)
    """
    defs = list_definitions(db, tenant_id)
    if not defs:
        return ""
    lines = ["", "Définitions métier réutilisables :"]
    for d in defs:
        if d.kind == "measure":
            base = f"  Mesure {d.name} = {d.expression} sur {d.schema_name}.{d.table_name}"
            if d.filter_sql:
                base += f" filtre: {d.filter_sql}"
            lines.append(base)
        else:
            lines.append(
                f"  Segment {d.name} sur {d.schema_name}.{d.table_name} filtre: {d.filter_sql}"
            )
    return "\n".join(lines)
