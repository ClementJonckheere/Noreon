from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_owned_connection
from app.core.db import get_db
from app.models.connection import Connection
from app.models.schema_catalog import DbColumn, DbRelation, DbTable
from app.schemas import ColumnOut, RelationOut, RelationReviewIn, ScanOut, TableOut
from app.services import connections as conn_svc
from app.services import scanner
from app.services.schema_context import current_snapshot

router = APIRouter(prefix="/connections/{connection_id}", tags=["schema"])


@router.post("/scan", response_model=ScanOut)
def scan(
    conn: Connection = Depends(get_owned_connection),
    db: Session = Depends(get_db),
) -> ScanOut:
    if conn.is_read_only is False:
        raise HTTPException(
            status_code=409,
            detail="Connexion non read-only : scan refusé. Corrigez les droits d'abord.",
        )
    adapter = conn_svc.get_source_adapter(conn)
    snapshot, changed = scanner.scan_and_persist(db, conn, adapter)
    db.commit()
    return ScanOut(
        snapshot_id=snapshot.id, version=snapshot.version, signature=snapshot.signature,
        table_count=snapshot.table_count, changed=changed,
        message="Nouveau schéma détecté et versionné." if changed
        else "Aucun changement de schéma (scan incrémental).",
    )


@router.get("/schema", response_model=list[TableOut])
def get_schema(
    conn: Connection = Depends(get_owned_connection),
    db: Session = Depends(get_db),
) -> list[TableOut]:
    snapshot = current_snapshot(db, conn.id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Aucun schéma scanné. Lancez un scan.")
    tables = db.execute(
        select(DbTable).where(DbTable.snapshot_id == snapshot.id).order_by(DbTable.table_name)
    ).scalars().all()
    out: list[TableOut] = []
    for t in tables:
        cols = db.execute(
            select(DbColumn).where(DbColumn.table_id == t.id).order_by(DbColumn.ordinal)
        ).scalars().all()
        out.append(TableOut(
            id=t.id, schema_name=t.schema_name, table_name=t.table_name,
            table_type=t.table_type, estimated_rows=t.estimated_rows,
            columns=[ColumnOut.model_validate(c) for c in cols],
        ))
    return out


@router.get("/relations", response_model=list[RelationOut])
def get_relations(
    conn: Connection = Depends(get_owned_connection),
    db: Session = Depends(get_db),
) -> list[RelationOut]:
    snapshot = current_snapshot(db, conn.id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Aucun schéma scanné. Lancez un scan.")
    rels = db.execute(
        select(DbRelation).where(DbRelation.snapshot_id == snapshot.id)
    ).scalars().all()
    return [_relation_out(r) for r in rels]


def _relation_out(r: DbRelation) -> RelationOut:
    return RelationOut(
        id=r.id,
        from_table=f"{r.from_schema}.{r.from_table}", from_column=r.from_column,
        to_table=f"{r.to_schema}.{r.to_table}", to_column=r.to_column,
        kind=r.kind, status=r.status, confidence=r.confidence,
        cardinality=r.cardinality, integrity_ratio=r.integrity_ratio,
    )


@router.get("/graph")
def get_graph(
    conn: Connection = Depends(get_owned_connection),
    db: Session = Depends(get_db),
) -> dict:
    """Knowledge Graph (Module 6) : entités métier + relations documentées."""
    from app.services.graph import build_graph

    try:
        return build_graph(db, conn)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/relations/{relation_id}/review", response_model=RelationOut)
def review_relation(
    relation_id: int,
    payload: RelationReviewIn,
    conn: Connection = Depends(get_owned_connection),
    db: Session = Depends(get_db),
) -> RelationOut:
    """Boucle de validation des relations inférées (Module 6) — même
    mécanique que le dictionnaire métier : l'humain valide ou rejette."""
    snapshot = current_snapshot(db, conn.id)
    rel = db.get(DbRelation, relation_id)
    if rel is None or snapshot is None or rel.snapshot_id != snapshot.id:
        raise HTTPException(status_code=404, detail="Relation introuvable.")
    if rel.kind == "declared":
        raise HTTPException(
            status_code=409,
            detail="Relation déclarée en base (FK) : elle n'est pas soumise à validation.",
        )
    if payload.action == "validate":
        rel.status = "validated"
        rel.kind = "validated"
    else:
        rel.status = "rejected"
    db.commit()
    db.refresh(rel)
    return _relation_out(rel)
