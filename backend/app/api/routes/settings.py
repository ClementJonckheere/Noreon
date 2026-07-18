from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import current_tenant, require_analyst
from app.core.db import get_db
from app.models.tenant import Tenant, TenantSettings
from app.schemas import PreferencesIn

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
    for key, value in payload.model_dump(exclude_none=True).items():
        prefs[key] = value
    ts.preferences = prefs
    db.commit()
    return prefs
