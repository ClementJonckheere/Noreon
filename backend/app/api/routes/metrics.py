from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import Principal, current_principal, require_analyst
from app.core.db import get_db
from app.services import metrics as metrics_svc

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("", dependencies=[Depends(require_analyst)])
def get_metrics(
    days: int = 30,
    connection_id: int | None = None,
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
) -> dict:
    """Tableau de bord d'observabilité (qualité produit + coûts).

    Toujours borné au tenant du principal — Noreon mesure son propre travail,
    sans exposer aucune donnée métier brute."""
    days = max(1, min(days, 365))
    return metrics_svc.product_metrics(
        db, tenant_id=principal.tenant_id, connection_id=connection_id, days=days
    )
