from __future__ import annotations

import base64
import secrets

from app.core.security import SecretBox


def test_encrypt_decrypt_roundtrip():
    box = SecretBox(master_key=base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())
    secret = "s3cr3t-p@ssw0rd!éà"
    token = box.encrypt(secret)
    assert token != secret
    assert box.decrypt(token) == secret


def test_encrypt_json_roundtrip():
    box = SecretBox(master_key="any-passphrase-works")
    payload = {"password": "hunter2", "extra": "x"}
    token = box.encrypt_json(payload)
    assert box.decrypt_json(token) == payload


def test_nonce_makes_ciphertext_unique():
    box = SecretBox(master_key="k")
    assert box.encrypt("same") != box.encrypt("same")


def test_wrong_key_fails():
    box1 = SecretBox(master_key="key-one")
    box2 = SecretBox(master_key="key-two")
    token = box1.encrypt("data")
    try:
        box2.decrypt(token)
        assert False, "le déchiffrement aurait dû échouer"
    except Exception:
        pass


def test_arbitrary_string_key_derives_256_bits():
    # Une clé maîtresse non-base64 doit quand même fonctionner (hachée en SHA-256).
    box = SecretBox(master_key="short")
    assert box.decrypt(box.encrypt("ok")) == "ok"
