"""API Notifications — une file « À traiter » (WorkItem) et un fil « Suivi »
(ActivityEvent), dérivés de l'état réel du produit. Générique : aucune notion métier.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import Principal, current_principal
from app.core.db import get_db
from app.services import worklist

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("")
def get_notifications(
    db: Session = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> dict:
    """Réconcilie avec l'état réel, puis renvoie « pour vous » (À traiter filtré par
    capacité) + « suivi ». La lecture n'affecte pas le nombre à traiter."""
    worklist.reconcile(db, principal.tenant_id)
    db.commit()
    return worklist.for_user(db, principal.tenant_id, principal.role)


@router.post("/read")
def mark_all_read(
    db: Session = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> dict:
    """Marque tout comme lu — SANS résoudre : « À traiter » n'est jamais vidé par la lecture."""
    worklist.mark_read(db, principal.tenant_id)
    db.commit()
    return worklist.for_user(db, principal.tenant_id, principal.role)
