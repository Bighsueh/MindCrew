"""Envelope encryption for at-rest secrets (Phase 26 / S2).

Encrypts values like ``llm_providers.api_key`` with Fernet (AES-128-CBC +
HMAC-SHA256) so a ``pg_dump`` or DB backup leak does not directly expose
provider credentials. Ciphertext is stored as ``fernet:<token>`` so reads can
transparently fall back to legacy plaintext during rollout.

Master key source: ``LLM_PROVIDER_KEY_MASTER`` env var (a 32-byte url-safe
base64 Fernet key, e.g. ``Fernet.generate_key().decode()``). In ``development``
the key falls back to a deterministic value derived from ``JWT_SECRET_KEY`` so
local dev keeps working without extra setup; production startup raises if it
is missing or invalid.
"""
from __future__ import annotations

import base64
import hashlib
import logging
import os
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

CIPHERTEXT_PREFIX = "fernet:"


class SecretCipherError(RuntimeError):
    """Raised when the master key is missing/invalid or decryption fails."""


def is_ciphertext(value: str | None) -> bool:
    return bool(value) and value.startswith(CIPHERTEXT_PREFIX)  # type: ignore[union-attr]


@lru_cache(maxsize=1)
def _cipher() -> Fernet:
    raw = os.getenv("LLM_PROVIDER_KEY_MASTER", "").strip()
    if raw:
        try:
            return Fernet(raw.encode("utf-8"))
        except (ValueError, TypeError) as exc:  # invalid base64 / wrong length
            raise SecretCipherError(
                "LLM_PROVIDER_KEY_MASTER is set but is not a valid Fernet key "
                "(expect 32 url-safe base64 bytes; generate with "
                "`python -c 'from cryptography.fernet import Fernet; "
                "print(Fernet.generate_key().decode())'`)"
            ) from exc

    app_env = os.getenv("APP_ENV", "development").lower()
    if app_env != "development":
        raise SecretCipherError(
            "LLM_PROVIDER_KEY_MASTER is required outside development. "
            "Set a 32-byte url-safe base64 Fernet key in the environment."
        )

    jwt_secret = os.getenv("JWT_SECRET_KEY", "change-me-in-production")
    logger.warning(
        "LLM_PROVIDER_KEY_MASTER not set; deriving a dev-only key from "
        "JWT_SECRET_KEY. DO NOT use this in production."
    )
    derived = hashlib.sha256(jwt_secret.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(derived))


def encrypt_secret(plaintext: str) -> str:
    """Encrypt plaintext; returns ``fernet:<token>``. Empty input returns ''."""
    if plaintext is None or plaintext == "":
        return ""
    if is_ciphertext(plaintext):
        # Idempotent: already encrypted, keep as-is so re-saves don't double-wrap.
        return plaintext
    token = _cipher().encrypt(plaintext.encode("utf-8")).decode("utf-8")
    return f"{CIPHERTEXT_PREFIX}{token}"


def decrypt_secret(value: str | None) -> str:
    """Decrypt ``fernet:<token>``; pass through legacy plaintext unchanged.

    Raises ``SecretCipherError`` if a ciphertext payload cannot be decrypted
    (wrong master key, tampered token). Empty values return ''.
    """
    if value is None or value == "":
        return ""
    if not is_ciphertext(value):
        # Legacy plaintext row — pre-encryption rollout. Caller may choose to
        # re-encrypt on next write. Logged at DEBUG to avoid noise.
        logger.debug("decrypt_secret: value is plaintext (legacy row)")
        return value
    token = value[len(CIPHERTEXT_PREFIX):]
    try:
        return _cipher().decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise SecretCipherError(
            "Failed to decrypt secret — wrong LLM_PROVIDER_KEY_MASTER or "
            "tampered ciphertext."
        ) from exc
