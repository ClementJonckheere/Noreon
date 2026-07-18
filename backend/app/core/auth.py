"""Primitives d'authentification (Module 11) — sans dépendance externe.

- Mots de passe : PBKDF2-HMAC-SHA256 (salt aléatoire, 200 000 itérations).
- Jetons : JWT HS256 signés avec la clé maîtresse.
- MFA : TOTP (RFC 6238) + URI d'enrôlement (otpauth://) pour applications
  d'authentification (Google Authenticator, etc.).

Tout est implémenté avec la bibliothèque standard pour éviter toute dépendance
sensible supplémentaire dans un composant de sécurité.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import struct
import time

from app.core.config import settings

# ---------------------------------------------------------------------------
# Mots de passe
# ---------------------------------------------------------------------------
_PBKDF2_ROUNDS = 200_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${_PBKDF2_ROUNDS}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, rounds, b64salt, b64hash = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        salt = base64.b64decode(b64salt)
        expected = base64.b64decode(b64hash)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(rounds))
        return hmac.compare_digest(dk, expected)
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------------------
# JWT HS256
# ---------------------------------------------------------------------------
def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


ACCESS_TTL_SECONDS = 12 * 3600


def create_access_token(*, user_id: int, tenant_id: int, role: str, ttl: int = ACCESS_TTL_SECONDS) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    payload = {"sub": user_id, "tenant": tenant_id, "role": role, "iat": now, "exp": now + ttl}
    segments = [
        _b64url(json.dumps(header, separators=(",", ":")).encode()),
        _b64url(json.dumps(payload, separators=(",", ":")).encode()),
    ]
    signing_input = ".".join(segments).encode()
    sig = hmac.new(settings.secret_key.encode(), signing_input, hashlib.sha256).digest()
    segments.append(_b64url(sig))
    return ".".join(segments)


def decode_access_token(token: str) -> dict | None:
    try:
        h, p, s = token.split(".")
        signing_input = f"{h}.{p}".encode()
        expected = hmac.new(settings.secret_key.encode(), signing_input, hashlib.sha256).digest()
        if not hmac.compare_digest(_b64url_decode(s), expected):
            return None
        payload = json.loads(_b64url_decode(p))
        if payload.get("exp", 0) < int(time.time()):
            return None
        return payload
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# MFA / TOTP (RFC 6238)
# ---------------------------------------------------------------------------
def generate_totp_secret() -> str:
    # Secret base32 de 20 octets.
    return base64.b32encode(os.urandom(20)).decode("ascii").rstrip("=")


def _totp(secret_b32: str, for_time: int, step: int = 30, digits: int = 6) -> str:
    key = base64.b32decode(secret_b32 + "=" * (-len(secret_b32) % 8), casefold=True)
    counter = struct.pack(">Q", for_time // step)
    digest = hmac.new(key, counter, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % (10 ** digits)
    return str(code).zfill(digits)


def verify_totp(secret_b32: str, code: str, window: int = 1) -> bool:
    if not code or not code.strip().isdigit():
        return False
    code = code.strip()
    now = int(time.time())
    for drift in range(-window, window + 1):
        if hmac.compare_digest(_totp(secret_b32, now + drift * 30), code):
            return True
    return False


def totp_provisioning_uri(secret_b32: str, email: str, issuer: str = "Noreon") -> str:
    label = f"{issuer}:{email}"
    return (
        f"otpauth://totp/{label}?secret={secret_b32}&issuer={issuer}&algorithm=SHA1&digits=6&period=30"
    )
