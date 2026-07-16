"""Chiffrement au repos des credentials des connexions sources.

Cahier des charges, Module 1 :
« Credentials chiffrés au repos (AES-256, coffre de secrets), jamais loggés,
jamais transmis au LLM. »

Implémentation : AES-256-GCM (confidentialité + authentification). La clé
maîtresse provient de `settings.secret_key` (en production : coffre/KMS).
Le format stocké est : base64( nonce[12] || ciphertext || tag ), self-décrivant.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings

_NONCE_BYTES = 12


def _derive_key(master: str) -> bytes:
    """Dérive une clé AES-256 (32 octets) déterministe depuis la clé maîtresse.

    On accepte une clé maîtresse en base64 urlsafe (32 octets) ou n'importe
    quelle chaîne : dans ce dernier cas on la hache en SHA-256 pour obtenir
    exactement 256 bits.
    """
    try:
        raw = base64.urlsafe_b64decode(master)
        if len(raw) == 32:
            return raw
    except Exception:
        pass
    return hashlib.sha256(master.encode("utf-8")).digest()


class SecretBox:
    """Chiffre/déchiffre des secrets (chaînes ou dicts JSON)."""

    def __init__(self, master_key: str | None = None) -> None:
        self._key = _derive_key(master_key or settings.secret_key)

    def encrypt(self, plaintext: str) -> str:
        aes = AESGCM(self._key)
        nonce = os.urandom(_NONCE_BYTES)
        ct = aes.encrypt(nonce, plaintext.encode("utf-8"), None)
        return base64.b64encode(nonce + ct).decode("ascii")

    def decrypt(self, token: str) -> str:
        raw = base64.b64decode(token)
        nonce, ct = raw[:_NONCE_BYTES], raw[_NONCE_BYTES:]
        aes = AESGCM(self._key)
        return aes.decrypt(nonce, ct, None).decode("utf-8")

    def encrypt_json(self, obj: dict[str, Any]) -> str:
        return self.encrypt(json.dumps(obj, separators=(",", ":"), sort_keys=True))

    def decrypt_json(self, token: str) -> dict[str, Any]:
        return json.loads(self.decrypt(token))


def get_secret_box() -> SecretBox:
    return SecretBox()
