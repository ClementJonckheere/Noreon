"""Routes de la compréhension métier (Module 5) : boucle de validation humaine.

Noreon propose, l'humain valide/corrige/rejette. Les décisions alimentent la
mémoire entreprise et sont réutilisées dans toutes les analyses suivantes.
Le dictionnaire est exportable (CSV/JSON) : livrable de documentation.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_tenant, get_owned_connection, require_analyst
from app.core.db import get_db
from app.models.connection import Connection
from app.models.semantic import BusinessConcept, ConceptMapping
from app.models.tenant import Tenant
from app.schemas import (
    ConceptCreateIn,
    ConceptMappingOut,
    ConceptOut,
    MappingReviewIn,
    SemanticProposeOut,
)
from app.services import semantic as semantic_svc

router = APIRouter(prefix="/connections/{connection_id}/semantic", tags=["semantic"])
concepts_router = APIRouter(prefix="/concepts", tags=["semantic"])


@router.post("/propose", response_model=SemanticProposeOut,
             dependencies=[Depends(require_analyst)])
def propose(
    conn: Connection = Depends(get_owned_connection),
    db: Session = Depends(get_db),
) -> SemanticProposeOut:
    try:
        summary = semantic_svc.propose_and_persist(db, conn)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return SemanticProposeOut(**summary)


def _mapping_out(m: ConceptMapping, c: BusinessConcept) -> ConceptMappingOut:
    return ConceptMappingOut(
        id=m.id, concept_name=c.name, concept_description=c.description,
        schema_name=m.schema_name, table_name=m.table_name, column_name=m.column_name,
        confidence=m.confidence, rationale=m.rationale, status=m.status,
        needs_arbitration=m.needs_arbitration, arbitration_note=m.arbitration_note,
        review_note=m.review_note, reviewed_at=m.reviewed_at,
    )


@router.get("", response_model=list[ConceptMappingOut])
def list_mappings(
    conn: Connection = Depends(get_owned_connection),
    db: Session = Depends(get_db),
    status: str | None = Query(None),
) -> list[ConceptMappingOut]:
    stmt = (
        select(ConceptMapping, BusinessConcept)
        .join(BusinessConcept, ConceptMapping.concept_id == BusinessConcept.id)
        .where(ConceptMapping.connection_id == conn.id)
    )
    if status:
        stmt = stmt.where(ConceptMapping.status == status)
    rows = db.execute(
        stmt.order_by(ConceptMapping.table_name, ConceptMapping.column_name)
    ).all()
    return [_mapping_out(m, c) for m, c in rows]


@router.post("/{mapping_id}/review", response_model=ConceptMappingOut,
             dependencies=[Depends(require_analyst)])
def review_mapping(
    mapping_id: int,
    payload: MappingReviewIn,
    conn: Connection = Depends(get_owned_connection),
    db: Session = Depends(get_db),
) -> ConceptMappingOut:
    """Boucle de validation humaine : valider / corriger / rejeter."""
    mapping = db.get(ConceptMapping, mapping_id)
    if mapping is None or mapping.connection_id != conn.id:
        raise HTTPException(status_code=404, detail="Proposition introuvable.")

    now = datetime.now(timezone.utc)
    if payload.action == "validate":
        mapping.status = "validated"
        mapping.needs_arbitration = False
    elif payload.action == "reject":
        mapping.status = "rejected"
    elif payload.action == "correct":
        if not payload.concept_name:
            raise HTTPException(status_code=422, detail="concept_name requis pour une correction.")
        concept = semantic_svc._get_or_create_concept(db, conn.tenant_id, payload.concept_name)
        # Mémoire entreprise : la correction enrichit les synonymes du concept
        # (le nom de la colonne corrigée devient un indice réutilisable).
        syns = set(concept.synonyms or [])
        syns.add(mapping.column_name.lower())
        concept.synonyms = sorted(syns)
        mapping.concept_id = concept.id
        mapping.status = "corrected"
        mapping.needs_arbitration = False

    mapping.reviewed_at = now
    mapping.reviewed_by = "user"
    mapping.review_note = payload.note
    db.commit()
    db.refresh(mapping)
    concept = db.get(BusinessConcept, mapping.concept_id)
    return _mapping_out(mapping, concept)


@router.get("/export")
def export_dictionary(
    conn: Connection = Depends(get_owned_connection),
    db: Session = Depends(get_db),
    format: str = Query("json", pattern="^(json|csv)$"),
):
    """Export du dictionnaire métier (CSV/JSON) — livrable de documentation."""
    rows = db.execute(
        select(ConceptMapping, BusinessConcept)
        .join(BusinessConcept, ConceptMapping.concept_id == BusinessConcept.id)
        .where(
            ConceptMapping.connection_id == conn.id,
            ConceptMapping.status != "rejected",
        )
        .order_by(BusinessConcept.name, ConceptMapping.table_name)
    ).all()
    data = [
        {
            "concept": c.name,
            "description": c.description,
            "synonymes": ";".join(c.synonyms or []),
            "schema": m.schema_name,
            "table": m.table_name,
            "colonne": m.column_name,
            "statut": m.status,
            "confiance": m.confidence,
            "justification": m.rationale,
        }
        for m, c in rows
    ]
    if format == "json":
        return data
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(data[0].keys()) if data else ["concept"])
    writer.writeheader()
    writer.writerows(data)
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=dictionnaire_metier.csv"},
    )


# ---- Concepts (tenant) : création manuelle + synonymes propres à l'entreprise ----
@concepts_router.get("", response_model=list[ConceptOut])
def list_concepts(
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(current_tenant),
) -> list[ConceptOut]:
    rows = db.execute(
        select(BusinessConcept).where(BusinessConcept.tenant_id == tenant.id)
        .order_by(BusinessConcept.name)
    ).scalars().all()
    return [ConceptOut.model_validate(r) for r in rows]


@concepts_router.post("", response_model=ConceptOut, status_code=201,
             dependencies=[Depends(require_analyst)])
def create_concept(
    payload: ConceptCreateIn,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(current_tenant),
) -> ConceptOut:
    existing = db.execute(
        select(BusinessConcept).where(
            BusinessConcept.tenant_id == tenant.id, BusinessConcept.name == payload.name
        )
    ).scalar_one_or_none()
    if existing is not None:
        # Fusion des synonymes plutôt que doublon.
        existing.synonyms = sorted(set(existing.synonyms or []) | {s.lower() for s in payload.synonyms})
        if payload.description:
            existing.description = payload.description
        db.commit()
        db.refresh(existing)
        return ConceptOut.model_validate(existing)
    concept = BusinessConcept(
        tenant_id=tenant.id, name=payload.name, description=payload.description,
        synonyms=[s.lower() for s in payload.synonyms], origin="user",
    )
    db.add(concept)
    db.commit()
    db.refresh(concept)
    return ConceptOut.model_validate(concept)
