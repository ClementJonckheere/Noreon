"""Tests d'authentification & rôles (Module 11)."""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.core.auth import _totp
from app.core.db import SessionLocal
from app.main import app

client = TestClient(app)


@pytest.fixture
def tenant_slug():
    return "authtest_" + uuid.uuid4().hex[:8]


def _register_admin(slug, email="admin@ex.io", pwd="motdepasse1"):
    return client.post("/auth/register", json={
        "tenant_slug": slug, "email": email, "password": pwd, "full_name": "Admin",
    })


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_register_first_admin_and_login(tenant_slug):
    r = _register_admin(tenant_slug)
    assert r.status_code == 201
    assert r.json()["role"] == "admin"

    # Second register sur le même tenant → refusé.
    r2 = _register_admin(tenant_slug, email="autre@ex.io")
    assert r2.status_code == 409

    # Login OK.
    r3 = client.post("/auth/login", json={
        "tenant_slug": tenant_slug, "email": "admin@ex.io", "password": "motdepasse1",
    })
    assert r3.status_code == 200
    token = r3.json()["access_token"]
    me = client.get("/auth/me", headers=_auth(token))
    assert me.json()["role"] == "admin"
    assert me.json()["email"] == "admin@ex.io"


def test_wrong_password_rejected(tenant_slug):
    _register_admin(tenant_slug)
    r = client.post("/auth/login", json={
        "tenant_slug": tenant_slug, "email": "admin@ex.io", "password": "faux",
    })
    assert r.status_code == 401


def test_role_enforcement_reader_cannot_create_connection(tenant_slug):
    admin_token = _register_admin(tenant_slug).json()["access_token"]
    # L'admin crée un lecteur.
    r = client.post("/users", headers=_auth(admin_token), json={
        "email": "lecteur@ex.io", "password": "lecteur12345", "role": "reader",
    })
    assert r.status_code == 201
    reader_token = client.post("/auth/login", json={
        "tenant_slug": tenant_slug, "email": "lecteur@ex.io", "password": "lecteur12345",
    }).json()["access_token"]

    # Le lecteur ne peut PAS créer de connexion.
    r2 = client.post("/connections", headers=_auth(reader_token), json={
        "name": "x", "engine": "postgresql", "host": "localhost",
        "database": "d", "username": "u", "password": "p",
    })
    assert r2.status_code == 403
    # Mais il peut lister (lecture).
    assert client.get("/connections", headers=_auth(reader_token)).status_code == 200


def test_per_connection_access(tenant_slug):
    from app.models.connection import Connection
    from app.models.tenant import Tenant

    admin_token = _register_admin(tenant_slug).json()["access_token"]
    reader_id_token = client.post("/users", headers=_auth(admin_token), json={
        "email": "r2@ex.io", "password": "reader123456", "role": "reader",
    })
    assert reader_id_token.status_code == 201
    reader_uid = reader_id_token.json()["id"]
    reader_token = client.post("/auth/login", json={
        "tenant_slug": tenant_slug, "email": "r2@ex.io", "password": "reader123456",
    }).json()["access_token"]

    # On insère une connexion directement (sans source réelle).
    db = SessionLocal()
    tenant = db.query(Tenant).filter(Tenant.slug == tenant_slug).one()
    conn = Connection(
        tenant_id=tenant.id, name="src", engine="postgresql", host="h", port=5432,
        database="d", username="u", secret_encrypted="", is_read_only=True, status="ok",
    )
    db.add(conn)
    db.commit()
    cid = conn.id
    db.close()

    # Sans droit : accès refusé (403), pas 404.
    r = client.get(f"/connections/{cid}/schema", headers=_auth(reader_token))
    assert r.status_code == 403

    # L'admin octroie l'accès.
    g = client.post(f"/users/{reader_uid}/connections", headers=_auth(admin_token),
                    json={"connection_id": cid})
    assert g.status_code == 204

    # Avec droit : le garde d'accès passe (404 car pas de schéma scanné, mais plus 403).
    r2 = client.get(f"/connections/{cid}/schema", headers=_auth(reader_token))
    assert r2.status_code == 404


def test_mfa_enroll_and_login(tenant_slug):
    admin_token = _register_admin(tenant_slug).json()["access_token"]
    enroll = client.post("/auth/mfa/enroll", headers=_auth(admin_token))
    assert enroll.status_code == 200
    secret = enroll.json()["secret"]
    assert enroll.json()["otpauth_uri"].startswith("otpauth://totp/")

    import time
    code = _totp(secret, int(time.time()))
    v = client.post("/auth/mfa/verify", headers=_auth(admin_token), json={"code": code})
    assert v.status_code == 204

    # Login sans code → mfa_required, sans jeton.
    r = client.post("/auth/login", json={
        "tenant_slug": tenant_slug, "email": "admin@ex.io", "password": "motdepasse1",
    })
    assert r.json()["mfa_required"] is True
    assert r.json()["access_token"] == ""

    # Login avec code → jeton délivré.
    code2 = _totp(secret, int(time.time()))
    r2 = client.post("/auth/login", json={
        "tenant_slug": tenant_slug, "email": "admin@ex.io", "password": "motdepasse1",
        "mfa_code": code2,
    })
    assert r2.status_code == 200 and r2.json()["access_token"]
