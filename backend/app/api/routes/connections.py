from __future__ import annotations

import os
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings

from app.api.deps import Principal, current_tenant, get_owned_connection, require_analyst
from app.core.db import get_db
from app.models.connection import Connection
from app.models.tenant import Tenant
from app.schemas import (
    ConnectionCreate,
    ConnectionCreateResult,
    ConnectionOut,
    ProbeResult,
)
from app.services import connections as conn_svc

router = APIRouter(prefix="/connections", tags=["connections"])

_READ_ONLY_ALERT = (
    "ALERTE BLOQUANTE : le compte fourni n'est PAS en lecture seule. "
    "Noreon exige un utilisateur read-only. Créez un rôle dédié, par ex. :\n"
    "  CREATE ROLE noreon_ro LOGIN PASSWORD '...';\n"
    "  GRANT CONNECT ON DATABASE <db> TO noreon_ro;\n"
    "  GRANT USAGE ON SCHEMA public TO noreon_ro;\n"
    "  GRANT SELECT ON ALL TABLES IN SCHEMA public TO noreon_ro;\n"
    "  ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO noreon_ro;"
)


@router.post("", response_model=ConnectionCreateResult, status_code=201)
def create_connection(
    payload: ConnectionCreate,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(current_tenant),
    _: Principal = Depends(require_analyst),
) -> ConnectionCreateResult:
    existing = db.execute(
        select(Connection).where(
            Connection.tenant_id == tenant.id, Connection.name == payload.name
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="Une connexion porte déjà ce nom.")

    conn, probe = conn_svc.create_connection(
        db, tenant_id=tenant.id, name=payload.name, engine=payload.engine,
        host=payload.host, port=payload.port, database=payload.database,
        username=payload.username, password=payload.password, options=payload.options,
    )
    db.commit()
    db.refresh(conn)

    alert = None
    if probe["connection_ok"] and probe["read_only"] is False:
        alert = _READ_ONLY_ALERT
    return ConnectionCreateResult(
        connection=ConnectionOut.model_validate(conn),
        probe=ProbeResult(**probe),
        read_only_alert=alert,
    )


@router.post("/upload", response_model=ConnectionCreateResult, status_code=201)
async def upload_file_connection(
    name: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(current_tenant),
    _: Principal = Depends(require_analyst),
) -> ConnectionCreateResult:
    """Crée une connexion à partir d'un fichier CSV/Excel téléversé (V1.0)."""
    ext = os.path.splitext(file.filename or "")[1].lower()
    fmt = "excel" if ext in (".xlsx", ".xls", ".xlsm") else "csv"

    dest_dir = os.path.join(settings.data_dir, "uploads", tenant.slug)
    os.makedirs(dest_dir, exist_ok=True)
    safe = os.path.basename(file.filename or "source")
    dest = os.path.join(dest_dir, f"{uuid.uuid4().hex}_{safe}")
    with open(dest, "wb") as out:
        out.write(await file.read())

    existing = db.execute(
        select(Connection).where(Connection.tenant_id == tenant.id, Connection.name == name)
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="Une connexion porte déjà ce nom.")

    conn, probe = conn_svc.create_connection(
        db, tenant_id=tenant.id, name=name, engine=fmt,
        options={"file_path": dest, "format": fmt, "original_name": safe},
    )
    db.commit()
    db.refresh(conn)
    return ConnectionCreateResult(
        connection=ConnectionOut.model_validate(conn),
        probe=ProbeResult(**probe), read_only_alert=None,
    )


@router.get("", response_model=list[ConnectionOut])
def list_connections(
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(current_tenant),
) -> list[ConnectionOut]:
    rows = db.execute(
        select(Connection).where(Connection.tenant_id == tenant.id).order_by(Connection.created_at.desc())
    ).scalars().all()
    return [ConnectionOut.model_validate(r) for r in rows]


@router.get("/{connection_id}", response_model=ConnectionOut)
def get_connection(conn: Connection = Depends(get_owned_connection)) -> ConnectionOut:
    return ConnectionOut.model_validate(conn)


@router.post("/{connection_id}/test", response_model=ProbeResult)
def test_connection(
    conn: Connection = Depends(get_owned_connection),
    db: Session = Depends(get_db),
) -> ProbeResult:
    adapter = conn_svc.get_source_adapter(conn)
    probe = conn_svc.probe(adapter)
    conn_svc.persist_probe_result(conn, probe)
    db.commit()
    return ProbeResult(**probe)


@router.delete("/{connection_id}", status_code=204)
def delete_connection(
    conn: Connection = Depends(get_owned_connection),
    db: Session = Depends(get_db),
    _: Principal = Depends(require_analyst),
) -> None:
    db.delete(conn)
    db.commit()
