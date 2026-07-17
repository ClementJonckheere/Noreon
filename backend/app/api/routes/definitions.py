from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_tenant
from app.core.db import get_db
from app.models.definitions import BusinessDefinition
from app.models.tenant import Tenant
from app.schemas import DefinitionCreate, DefinitionOut

router = APIRouter(prefix="/definitions", tags=["definitions"])


@router.get("", response_model=list[DefinitionOut])
def list_definitions(
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(current_tenant),
) -> list[DefinitionOut]:
    rows = db.execute(
        select(BusinessDefinition).where(BusinessDefinition.tenant_id == tenant.id)
        .order_by(BusinessDefinition.kind, BusinessDefinition.name)
    ).scalars().all()
    return [DefinitionOut.model_validate(r) for r in rows]


@router.post("", response_model=DefinitionOut, status_code=201)
def create_definition(
    payload: DefinitionCreate,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(current_tenant),
) -> DefinitionOut:
    if payload.kind == "measure" and not payload.expression:
        raise HTTPException(status_code=422, detail="Une mesure requiert une expression d'agrégat.")
    if payload.kind == "segment" and not payload.filter_sql:
        raise HTTPException(status_code=422, detail="Un segment requiert un filtre SQL.")

    existing = db.execute(
        select(BusinessDefinition).where(
            BusinessDefinition.tenant_id == tenant.id, BusinessDefinition.name == payload.name
        )
    ).scalar_one_or_none()
    if existing is not None:
        # Mise à jour (upsert par nom) — une définition évolue.
        for field in ("kind", "schema_name", "table_name", "expression", "filter_sql", "description"):
            setattr(existing, field, getattr(payload, field))
        db.commit()
        db.refresh(existing)
        return DefinitionOut.model_validate(existing)

    d = BusinessDefinition(
        tenant_id=tenant.id, name=payload.name, kind=payload.kind,
        schema_name=payload.schema_name, table_name=payload.table_name,
        expression=payload.expression, filter_sql=payload.filter_sql,
        description=payload.description, source_question=payload.source_question,
    )
    db.add(d)
    db.commit()
    db.refresh(d)
    return DefinitionOut.model_validate(d)


@router.delete("/{definition_id}", status_code=204)
def delete_definition(
    definition_id: int,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(current_tenant),
) -> None:
    d = db.get(BusinessDefinition, definition_id)
    if d is None or d.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Définition introuvable.")
    db.delete(d)
    db.commit()
