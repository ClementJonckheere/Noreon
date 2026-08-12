"""Plan d'action — les décisions RETENUES depuis les analyses, suivies dans le
temps : retenue → mise en œuvre → (mesure) ; ou abandonnée.

C'est le pendant « on décide de faire » de la Conversation « on comprend ». Une
décision entre ici quand un décideur la retient depuis une réponse d'analyse.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Principal, current_principal
from app.core.db import get_db
from app.models.connection import Connection
from app.models.decision import DecisionRecord
from app.schemas import PlanItemUpdate

router = APIRouter(prefix="/plan", tags=["plan"])

# Cycle de vie d'une action (l'humain qualifie ; « successful » viendra de la
# MESURE, pas d'un clic arbitraire — cf. protocole de mesure).
_ACTIVE = ("retained", "implemented")
_ALLOWED = {"retained", "implemented", "successful", "abandoned"}


def _dict(d: DecisionRecord, conn_name: str | None) -> dict:
    # Libellé d'analyse MÉTIER (« Ventes ») — jamais le nom physique de la source
    # (« quicktest-retail-14568 »), qui n'a pas sa place dans cette couche.
    from app.services.concepts import subject_domain
    return {
        "id": d.id, "role": d.role,
        "recommendation": d.recommendation, "status": d.status, "note": d.note,
        "connection_id": d.connection_id,
        "analysis_label": subject_domain(d.subject or ""),
        "created_at": d.created_at.isoformat() if d.created_at else None,
    }


@router.get("")
def list_plan(
    include_closed: bool = False,
    db: Session = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> list[dict]:
    """Les actions du plan (tenant). Par défaut, seulement les actions ACTIVES
    (retenues / en cours) ; `include_closed` ajoute réussies et abandonnées."""
    stmt = (
        select(DecisionRecord, Connection.name)
        .join(Connection, Connection.id == DecisionRecord.connection_id, isouter=True)
        .where(DecisionRecord.tenant_id == principal.tenant_id)
        .order_by(DecisionRecord.created_at.desc())
    )
    rows = db.execute(stmt).all()
    items = [_dict(d, name) for d, name in rows]
    if not include_closed:
        items = [it for it in items if it["status"] in _ACTIVE]
    return items


@router.patch("/{item_id}")
def update_plan_item(
    item_id: int, payload: PlanItemUpdate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> dict:
    """Fait avancer une action (retenue → mise en œuvre → abandonnée). Le passage
    en « réussie » relève de la MESURE, pas d'une déclaration manuelle."""
    d = db.execute(
        select(DecisionRecord).where(
            DecisionRecord.id == item_id, DecisionRecord.tenant_id == principal.tenant_id
        )
    ).scalar_one_or_none()
    if d is None:
        raise HTTPException(status_code=404, detail="Action introuvable.")
    if payload.status is not None:
        if payload.status not in _ALLOWED:
            raise HTTPException(status_code=422, detail="Statut invalide.")
        if payload.status == "successful":
            raise HTTPException(
                status_code=422,
                detail="« Réussie » est posé par la mesure du résultat, pas manuellement.",
            )
        d.status = payload.status
    if payload.note is not None:
        d.note = payload.note
    db.commit()
    conn = db.get(Connection, d.connection_id)
    return _dict(d, conn.name if conn else None)
