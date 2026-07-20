"""Studio de rapports : génération IA, édition par blocs, export DOCX/PDF/MD."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import Principal, current_principal
from app.core.db import get_db
from app.models.connection import Connection
from app.models.report import Report, ReportBlock
from app.schemas import (
    BlockCreate,
    BlockMove,
    BlockUpdate,
    ReportAddAnswer,
    ReportCreate,
    ReportGenerate,
    ReportUpdate,
)
from app.services import chat as chat_svc
from app.services import reports as reports_svc
from app.services import spaces as spaces_svc

router = APIRouter(prefix="/reports", tags=["reports"])


def _user_ref(p: Principal) -> str:
    if p.email:
        return p.email
    if p.user_id is not None:
        return f"user:{p.user_id}"
    return "dev-admin"


def _block_dict(b: ReportBlock) -> dict:
    return {"id": b.id, "ordinal": b.ordinal, "kind": b.kind, "content": b.content}


def _summary(db: Session, r: Report) -> dict:
    count = db.execute(
        select(func.count(ReportBlock.id)).where(ReportBlock.report_id == r.id)
    ).scalar_one()
    return {
        "id": r.id, "title": r.title, "space_id": r.space_id, "block_count": count,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }


def _get_report(db: Session, p: Principal, rid: int) -> Report:
    r = db.execute(
        select(Report).where(
            Report.id == rid, Report.tenant_id == p.tenant_id, Report.user_ref == _user_ref(p)
        )
    ).scalar_one_or_none()
    if r is None:
        raise HTTPException(status_code=404, detail="Rapport introuvable.")
    return r


def _next_ordinal(db: Session, report_id: int) -> int:
    return db.execute(
        select(func.count(ReportBlock.id)).where(ReportBlock.report_id == report_id)
    ).scalar_one()


def _append_blocks(db: Session, report: Report, blocks: list[dict]) -> None:
    start = _next_ordinal(db, report.id)
    for i, b in enumerate(blocks):
        db.add(ReportBlock(
            report_id=report.id, ordinal=start + i,
            kind=b.get("kind", "markdown"), content=jsonable_encoder(b.get("content") or {}),
        ))
    report.updated_at = func.now()


# --------------------------------------------------------------------------
# CRUD rapports
# --------------------------------------------------------------------------
@router.get("")
def list_reports(
    db: Session = Depends(get_db),
    principal: Principal = Depends(current_principal),
    space_id: int | None = Query(default=None),
) -> list[dict]:
    q = select(Report).where(
        Report.tenant_id == principal.tenant_id, Report.user_ref == _user_ref(principal)
    )
    if space_id is not None:
        q = q.where(Report.space_id == space_id)
    reports = db.execute(q.order_by(Report.updated_at.desc())).scalars().all()
    return [_summary(db, r) for r in reports]


@router.post("")
def create_report(
    payload: ReportCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> dict:
    r = Report(
        tenant_id=principal.tenant_id, user_ref=_user_ref(principal),
        title=(payload.title or "Nouveau rapport").strip() or "Nouveau rapport",
        space_id=payload.space_id,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return {**_summary(db, r), "blocks": []}


@router.get("/{report_id}")
def get_report(
    report_id: int,
    db: Session = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> dict:
    r = _get_report(db, principal, report_id)
    return {**_summary(db, r), "blocks": [_block_dict(b) for b in r.blocks]}


@router.patch("/{report_id}")
def rename_report(
    report_id: int, payload: ReportUpdate,
    db: Session = Depends(get_db), principal: Principal = Depends(current_principal),
) -> dict:
    r = _get_report(db, principal, report_id)
    r.title = payload.title.strip() or r.title
    db.commit()
    return _summary(db, r)


@router.delete("/{report_id}")
def delete_report(
    report_id: int,
    db: Session = Depends(get_db), principal: Principal = Depends(current_principal),
) -> dict:
    r = _get_report(db, principal, report_id)
    db.delete(r)
    db.commit()
    return {"deleted": report_id}


# --------------------------------------------------------------------------
# Blocs
# --------------------------------------------------------------------------
@router.post("/{report_id}/blocks")
def add_block(
    report_id: int, payload: BlockCreate,
    db: Session = Depends(get_db), principal: Principal = Depends(current_principal),
) -> dict:
    r = _get_report(db, principal, report_id)
    _append_blocks(db, r, [{"kind": payload.kind, "content": payload.content}])
    db.commit()
    return get_report(report_id, db, principal)


@router.put("/{report_id}/blocks/{block_id}")
def update_block(
    report_id: int, block_id: int, payload: BlockUpdate,
    db: Session = Depends(get_db), principal: Principal = Depends(current_principal),
) -> dict:
    r = _get_report(db, principal, report_id)
    b = db.get(ReportBlock, block_id)
    if b is None or b.report_id != r.id:
        raise HTTPException(status_code=404, detail="Bloc introuvable.")
    b.content = jsonable_encoder(payload.content)
    r.updated_at = func.now()
    db.commit()
    return _block_dict(b)


@router.delete("/{report_id}/blocks/{block_id}")
def delete_block(
    report_id: int, block_id: int,
    db: Session = Depends(get_db), principal: Principal = Depends(current_principal),
) -> dict:
    r = _get_report(db, principal, report_id)
    b = db.get(ReportBlock, block_id)
    if b is None or b.report_id != r.id:
        raise HTTPException(status_code=404, detail="Bloc introuvable.")
    db.delete(b)
    db.flush()
    for i, blk in enumerate(r.blocks):  # recompacte les ordinaux
        blk.ordinal = i
    r.updated_at = func.now()
    db.commit()
    return get_report(report_id, db, principal)


@router.post("/{report_id}/blocks/{block_id}/move")
def move_block(
    report_id: int, block_id: int, payload: BlockMove,
    db: Session = Depends(get_db), principal: Principal = Depends(current_principal),
) -> dict:
    r = _get_report(db, principal, report_id)
    blocks = list(r.blocks)
    idx = next((i for i, b in enumerate(blocks) if b.id == block_id), None)
    if idx is None:
        raise HTTPException(status_code=404, detail="Bloc introuvable.")
    swap = idx - 1 if payload.direction == "up" else idx + 1
    if 0 <= swap < len(blocks):
        blocks[idx].ordinal, blocks[swap].ordinal = blocks[swap].ordinal, blocks[idx].ordinal
        r.updated_at = func.now()
        db.commit()
    return get_report(report_id, db, principal)


# --------------------------------------------------------------------------
# Génération / intervention IA (ajoute des blocs argumentés)
# --------------------------------------------------------------------------
@router.post("/{report_id}/generate")
def generate(
    report_id: int, payload: ReportGenerate,
    db: Session = Depends(get_db), principal: Principal = Depends(current_principal),
) -> dict:
    r = _get_report(db, principal, report_id)

    if payload.connection_id is not None:
        conn = db.execute(
            select(Connection).where(
                Connection.id == payload.connection_id,
                Connection.tenant_id == principal.tenant_id,
            )
        ).scalar_one_or_none()
        if conn is None:
            raise HTTPException(status_code=404, detail="Source introuvable.")
        hidden_t = hidden_c = None
        if r.space_id is not None and spaces_svc.is_connection_in_space(db, r.space_id, conn.id):
            hidden_t = spaces_svc.hidden_tables(db, r.space_id, conn.id)
            hidden_c = spaces_svc.hidden_columns(db, r.space_id, conn.id)
        resp = chat_svc.answer_question(
            db, conn, payload.prompt, deep_analysis=payload.deep_analysis,
            hidden_tables=hidden_t, hidden_columns=hidden_c,
        )
        blocks = reports_svc.response_to_blocks(
            reports_svc.default_title(payload.prompt), resp.as_dict()
        )
    else:
        blocks = reports_svc.skeleton_blocks(payload.prompt)

    # Un rapport vierge prend le titre du 1er prompt.
    if _next_ordinal(db, r.id) == 0 and r.title in ("", "Nouveau rapport"):
        r.title = reports_svc.default_title(payload.prompt)
    _append_blocks(db, r, blocks)
    db.commit()
    return get_report(report_id, db, principal)


@router.post("/{report_id}/add-answer")
def add_answer(
    report_id: int, payload: ReportAddAnswer,
    db: Session = Depends(get_db), principal: Principal = Depends(current_principal),
) -> dict:
    """Ajoute une réponse de chat (narratif + graphique + tableau) au rapport."""
    r = _get_report(db, principal, report_id)
    blocks = reports_svc.response_to_blocks(payload.title, payload.response)
    _append_blocks(db, r, blocks)
    db.commit()
    return get_report(report_id, db, principal)


# --------------------------------------------------------------------------
# Export
# --------------------------------------------------------------------------
@router.get("/{report_id}/export")
def export_report(
    report_id: int, format: str = Query(default="md"),
    db: Session = Depends(get_db), principal: Principal = Depends(current_principal),
) -> Response:
    r = _get_report(db, principal, report_id)
    blocks = [_block_dict(b) for b in r.blocks]
    safe = "".join(ch for ch in r.title if ch.isalnum() or ch in " -_").strip() or "rapport"

    if format == "docx":
        data = reports_svc.to_docx(r.title, blocks)
        media = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ext = "docx"
    elif format == "pdf":
        data = reports_svc.to_pdf(r.title, blocks)
        media = "application/pdf"
        ext = "pdf"
    else:
        data = reports_svc.to_markdown(r.title, blocks).encode("utf-8")
        media = "text/markdown; charset=utf-8"
        ext = "md"

    return Response(
        content=data, media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{safe}.{ext}"'},
    )
