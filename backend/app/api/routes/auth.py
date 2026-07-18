from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import Principal, current_principal, get_or_create_tenant
from app.core.auth import (
    create_access_token,
    generate_totp_secret,
    hash_password,
    totp_provisioning_uri,
    verify_password,
    verify_totp,
)
from app.core.db import get_db
from app.models.user import ROLE_ADMIN, User
from app.schemas import (
    LoginIn,
    MeOut,
    MfaEnrollOut,
    MfaVerifyIn,
    RegisterIn,
    TokenOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenOut, status_code=201)
def register(payload: RegisterIn, db: Session = Depends(get_db)) -> TokenOut:
    """Crée le PREMIER utilisateur d'un tenant (administrateur).

    Les utilisateurs suivants sont créés par un administrateur via /users.
    """
    tenant = get_or_create_tenant(db, payload.tenant_slug)
    count = db.execute(
        select(func.count()).select_from(User).where(User.tenant_id == tenant.id)
    ).scalar_one()
    if count > 0:
        raise HTTPException(
            status_code=409,
            detail="Cet espace a déjà un administrateur. Demandez-lui de créer votre compte.",
        )
    user = User(
        tenant_id=tenant.id, email=payload.email.lower(), full_name=payload.full_name,
        password_hash=hash_password(payload.password), role=ROLE_ADMIN, is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(user_id=user.id, tenant_id=tenant.id, role=user.role)
    return TokenOut(access_token=token, role=user.role, email=user.email)


@router.post("/login", response_model=TokenOut)
def login(payload: LoginIn, db: Session = Depends(get_db)) -> TokenOut:
    from app.models.tenant import Tenant

    t = db.execute(select(Tenant).where(Tenant.slug == payload.tenant_slug)).scalar_one_or_none()
    if t is None:
        raise HTTPException(status_code=401, detail="Identifiants invalides.")
    user = db.execute(
        select(User).where(User.tenant_id == t.id, User.email == payload.email.lower())
    ).scalar_one_or_none()
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Identifiants invalides.")

    if user.mfa_enabled:
        if not payload.mfa_code:
            # Mot de passe correct mais code MFA requis.
            return TokenOut(access_token="", role=user.role, email=user.email, mfa_required=True)
        if not verify_totp(user.mfa_secret or "", payload.mfa_code):
            raise HTTPException(status_code=401, detail="Code MFA invalide.")

    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    token = create_access_token(user_id=user.id, tenant_id=t.id, role=user.role)
    return TokenOut(access_token=token, role=user.role, email=user.email)


@router.get("/me", response_model=MeOut)
def me(principal: Principal = Depends(current_principal)) -> MeOut:
    return MeOut(
        user_id=principal.user_id, email=principal.email,
        role=principal.role, tenant_id=principal.tenant_id,
    )


@router.post("/mfa/enroll", response_model=MfaEnrollOut)
def mfa_enroll(
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
) -> MfaEnrollOut:
    if principal.user_id is None:
        raise HTTPException(status_code=400, detail="MFA indisponible en mode dev (sans utilisateur).")
    user = db.get(User, principal.user_id)
    secret = generate_totp_secret()
    user.mfa_secret = secret
    user.mfa_enabled = False  # activé seulement après vérification d'un code
    db.commit()
    return MfaEnrollOut(secret=secret, otpauth_uri=totp_provisioning_uri(secret, user.email))


@router.post("/mfa/verify", status_code=204)
def mfa_verify(
    payload: MfaVerifyIn,
    principal: Principal = Depends(current_principal),
    db: Session = Depends(get_db),
) -> None:
    if principal.user_id is None:
        raise HTTPException(status_code=400, detail="MFA indisponible en mode dev.")
    user = db.get(User, principal.user_id)
    if not user.mfa_secret or not verify_totp(user.mfa_secret, payload.code):
        raise HTTPException(status_code=400, detail="Code invalide — MFA non activée.")
    user.mfa_enabled = True
    db.commit()
