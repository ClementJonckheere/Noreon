from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import current_tenant, require_admin, require_analyst
from app.core.db import get_db
from app.models.tenant import Tenant, TenantSettings
from app.schemas import AnalysisContextIn, PreferencesIn
from app.services import company_context as company_ctx

router = APIRouter(prefix="/settings", tags=["settings"])

_DEFAULT_PREFS = {
    "preferred_chart_type": None,
    "auto_learn": True,
    "auto_save_definitions": True,
}


def _prefs(ts: TenantSettings) -> dict:
    prefs = dict(_DEFAULT_PREFS)
    if isinstance(ts.preferences, dict):
        prefs.update(ts.preferences)
    return prefs


@router.get("/preferences")
def get_preferences(
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(current_tenant),
) -> dict:
    ts = db.get(TenantSettings, tenant.id)
    return _prefs(ts)


@router.put("/preferences", dependencies=[Depends(require_analyst)])
def update_preferences(
    payload: PreferencesIn,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(current_tenant),
) -> dict:
    ts = db.get(TenantSettings, tenant.id)
    prefs = _prefs(ts)
    # exclude_unset : on n'applique que les clés réellement envoyées, MAIS on
    # accepte les valeurs nulles explicites (ex. remettre le graphique en auto).
    for key, value in payload.model_dump(exclude_unset=True).items():
        prefs[key] = value
    ts.preferences = prefs
    db.commit()
    return prefs


@router.get("/analysis-context")
def get_analysis_context(
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(current_tenant),
) -> dict:
    """Conventions d'analyse de l'entreprise (contexte D)."""
    ts = db.get(TenantSettings, tenant.id)
    return company_ctx.get_context(ts)


@router.put("/analysis-context", dependencies=[Depends(require_admin)])
def update_analysis_context(
    payload: AnalysisContextIn,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(current_tenant),
) -> dict:
    """Le paramétrage du contexte d'entreprise est réservé à l'administrateur."""
    ts = db.get(TenantSettings, tenant.id)
    ctx = company_ctx.get_context(ts)
    for key, value in payload.model_dump(exclude_unset=True).items():
        ctx[key] = value
    if not isinstance(ctx.get("conventions"), list):
        ctx["conventions"] = []
    # JSON muté en place : forcer la détection de changement.
    ts.analysis_context = dict(ctx)
    db.commit()
    return ctx
