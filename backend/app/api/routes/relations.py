"""API des RELATIONS candidates — générique (aucune fixture métier dans l'API).

Endpoints sur /relations : lister, détailler, prévisualiser la valeur métier,
valider (autoriser Noreon à l'utiliser) ou rejeter. « sales.article_reference →
articles.reference » et « subscriptions.account_id → accounts.id » sont traités
par le même code.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import current_tenant, require_analyst
from app.core.db import get_db
from app.models.relation_candidate import RelationCandidate
from app.models.tenant import Tenant
from app.services import relations as rel_svc

router = APIRouter(prefix="/relations", tags=["relations"])


def _field(schema: str, table: str, column: str) -> dict:
    return {"schema": schema, "table": table, "column": column,
            "label": f"{table}.{column}"}


def _rel_dict(db: Session, r: RelationCandidate) -> dict:
    return {
        "id": r.id, "connection_id": r.connection_id,
        "left": _field(r.left_schema, r.left_table, r.left_column),
        "right": _field(r.right_schema, r.right_table, r.right_column),
        "direction": r.direction, "cardinality": r.cardinality,
        "coverage": r.coverage, "target_uniqueness": r.target_uniqueness,
        "type_compatibility": r.type_compatibility,
        "exceptions_count": r.exceptions_count, "exceptions_note": r.exceptions_note,
        "alternatives": r.alternatives or [], "origin": r.origin,
        "valid_from": r.valid_from.isoformat() if r.valid_from else None,
        "valid_to": r.valid_to.isoformat() if r.valid_to else None,
        "status": r.status, "validated_by": r.validated_by,
        "validated_at": r.validated_at.isoformat() if r.validated_at else None,
        "validation_window": r.validation_window, "evidence": r.evidence,
        **rel_svc.freshness(db, r),
    }


def _owned(db: Session, relation_id: int, tenant: Tenant) -> RelationCandidate:
    r = db.get(RelationCandidate, relation_id)
    if r is None or r.tenant_id != tenant.id:
        raise HTTPException(status_code=404, detail="Relation introuvable.")
    return r


@router.get("")
def list_relations(
    connection_id: int | None = Query(default=None),
    space_id: int | None = Query(default=None),
    include_archived: bool = Query(default=False),
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(current_tenant),
) -> list[dict]:
    """Relations du tenant, cloisonnées par espace au niveau PHYSIQUE : une relation
    n'apparaît dans un espace que si sa source y est rattachée. Contrairement aux
    concepts (héritage Univers→Espace), un lien physique ne fuit pas d'un périmètre
    de données à un autre."""
    rows = rel_svc.list_candidates(db, tenant.id, connection_id=connection_id,
                                   include_archived=include_archived)
    if space_id is not None:
        from app.services.spaces import space_connection_ids
        allowed = set(space_connection_ids(db, space_id))
        rows = [r for r in rows if r.connection_id in allowed]
    return [_rel_dict(db, r) for r in rows]


@router.get("/{relation_id}")
def relation_detail(
    relation_id: int,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(current_tenant),
) -> dict:
    return _rel_dict(db, _owned(db, relation_id, tenant))


@router.get("/{relation_id}/preview")
def relation_preview(
    relation_id: int,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(current_tenant),
) -> dict:
    """Ce que la relation REND POSSIBLE — dérivé des concepts réels, jamais codé."""
    return rel_svc.preview(db, _owned(db, relation_id, tenant))


@router.get("/{relation_id}/exceptions")
def relation_exceptions(
    relation_id: int,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(current_tenant),
) -> dict:
    """Contre-exemples : combien, et la nuance temporelle (« toutes antérieures à… »)."""
    r = _owned(db, relation_id, tenant)
    return {"count": r.exceptions_count, "note": r.exceptions_note,
            "left": _field(r.left_schema, r.left_table, r.left_column),
            "right": _field(r.right_schema, r.right_table, r.right_column)}


@router.post("/{relation_id}/validate", dependencies=[Depends(require_analyst)])
def validate_relation(
    relation_id: int,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(current_tenant),
) -> dict:
    """Autorise Noreon à utiliser la relation. Fige fenêtre + snapshot + evidence.
    Refuse si les faits sont obsolètes (à recalculer d'abord)."""
    r = _owned(db, relation_id, tenant)
    if rel_svc.is_stale(db, r):
        raise HTTPException(status_code=409,
                            detail="Les faits ont changé depuis l'évaluation. Recalculez avant de valider.")
    rel_svc.validate(db, r, actor=tenant.name)
    db.commit()
    return _rel_dict(db, r)


@router.post("/{relation_id}/reject", dependencies=[Depends(require_analyst)])
def reject_relation(
    relation_id: int,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(current_tenant),
) -> dict:
    r = _owned(db, relation_id, tenant)
    rel_svc.reject(db, r, actor=tenant.name)
    db.commit()
    return _rel_dict(db, r)
