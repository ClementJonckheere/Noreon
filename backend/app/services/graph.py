"""Knowledge Graph (Module 6).

Graphe des entités métier et de leurs relations, construit automatiquement
depuis le catalogue de schéma, enrichi par :
- le dictionnaire métier validé (une table couverte par un concept-entité
  validé porte le nom du concept) ;
- les scores qualité (Module 4) ;
- l'intégrité et la cardinalité réelles des relations.

Chaque relation est documentée : source (FK déclarée / inférée / validée par
l'utilisateur), cardinalité, taux d'intégrité. Le graphe est navigable côté
interface et sert déjà de contexte au moteur SQL (schema_context).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.connection import Connection
from app.models.schema_catalog import DbColumn, DbRelation, DbTable
from app.models.semantic import BusinessConcept, ConceptMapping
from app.services.quality import table_scores_map
from app.services.schema_context import current_snapshot


def build_graph(db: Session, conn: Connection) -> dict:
    snapshot = current_snapshot(db, conn.id)
    if snapshot is None:
        raise ValueError("Aucun schéma scanné — lancez un scan avant le graphe.")

    tables = db.execute(
        select(DbTable).where(DbTable.snapshot_id == snapshot.id)
    ).scalars().all()

    # Concepts-entités validés : nom métier de la table (mapping validé/corrigé
    # sur la clé primaire).
    concept_rows = db.execute(
        select(ConceptMapping, BusinessConcept)
        .join(BusinessConcept, ConceptMapping.concept_id == BusinessConcept.id)
        .where(
            ConceptMapping.connection_id == conn.id,
            ConceptMapping.status.in_(["validated", "corrected"]),
        )
    ).all()
    entity_by_table: dict[str, str] = {}
    concepts_by_table: dict[str, set[str]] = {}
    pk_cols: dict[str, set[str]] = {}
    for t in tables:
        cols = db.execute(select(DbColumn).where(DbColumn.table_id == t.id)).scalars().all()
        pk_cols[t.table_name] = {c.name for c in cols if c.is_primary_key}
    for m, c in concept_rows:
        concepts_by_table.setdefault(m.table_name, set()).add(c.name)
        if m.column_name in pk_cols.get(m.table_name, set()):
            entity_by_table[m.table_name] = c.name

    quality = table_scores_map(db, conn.id)

    nodes = []
    for t in tables:
        col_count = db.execute(
            select(DbColumn).where(DbColumn.table_id == t.id)
        ).scalars().all()
        nodes.append({
            "table": t.fqtn,
            "name": t.table_name,
            "entity": entity_by_table.get(t.table_name),
            "concepts": sorted(concepts_by_table.get(t.table_name, set())),
            "rows": t.estimated_rows,
            "columns": len(col_count),
            "quality": round(quality[t.table_name], 4) if t.table_name in quality else None,
            "table_type": t.table_type,
        })

    relations = db.execute(
        select(DbRelation).where(DbRelation.snapshot_id == snapshot.id)
    ).scalars().all()
    edges = []
    for r in relations:
        edges.append({
            "id": r.id,
            "from": f"{r.from_schema}.{r.from_table}",
            "to": f"{r.to_schema}.{r.to_table}",
            "from_column": r.from_column,
            "to_column": r.to_column,
            "kind": r.kind,               # declared | inferred | validated
            "status": r.status,           # proposed | validated | rejected
            "confidence": r.confidence,
            "cardinality": r.cardinality,
            "integrity_ratio": r.integrity_ratio,
        })

    return {"nodes": nodes, "edges": edges}
