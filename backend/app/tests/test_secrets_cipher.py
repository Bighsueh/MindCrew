"""Unit tests for ``app.security.secrets`` (Phase 26 / S2)."""
from __future__ import annotations

import importlib
import os

import pytest
from cryptography.fernet import Fernet


@pytest.fixture
def fresh_secrets(monkeypatch):
    """Reload module so the lru_cache on _cipher() picks up env changes."""
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("LLM_PROVIDER_KEY_MASTER", key)
    monkeypatch.setenv("APP_ENV", "production")
    import app.security.secrets as mod
    importlib.reload(mod)
    yield mod
    # Re-reload so other tests see a fresh cache.
    monkeypatch.delenv("LLM_PROVIDER_KEY_MASTER", raising=False)
    importlib.reload(mod)


def test_encrypt_then_decrypt_roundtrip(fresh_secrets):
    cipher = fresh_secrets.encrypt_secret("sk-abc-123")
    assert cipher.startswith("fernet:")
    assert fresh_secrets.decrypt_secret(cipher) == "sk-abc-123"


def test_encrypt_empty_returns_empty(fresh_secrets):
    assert fresh_secrets.encrypt_secret("") == ""
    assert fresh_secrets.decrypt_secret("") == ""


def test_decrypt_legacy_plaintext_passthrough(fresh_secrets):
    # Pre-rollout rows have no prefix — must pass through so the registry
    # keeps working until the migration upgrades them.
    assert fresh_secrets.decrypt_secret("legacy-plaintext-key") == "legacy-plaintext-key"


def test_encrypt_is_idempotent(fresh_secrets):
    once = fresh_secrets.encrypt_secret("hello")
    twice = fresh_secrets.encrypt_secret(once)
    # Already encrypted, should not double-wrap.
    assert once == twice


def test_wrong_master_key_fails_decrypt(monkeypatch):
    # Encrypt with key A, attempt to decrypt with key B → must raise.
    import app.security.secrets as mod

    key_a = Fernet.generate_key().decode()
    monkeypatch.setenv("LLM_PROVIDER_KEY_MASTER", key_a)
    monkeypatch.setenv("APP_ENV", "production")
    importlib.reload(mod)
    token = mod.encrypt_secret("secret")

    key_b = Fernet.generate_key().decode()
    monkeypatch.setenv("LLM_PROVIDER_KEY_MASTER", key_b)
    importlib.reload(mod)
    with pytest.raises(mod.SecretCipherError):
        mod.decrypt_secret(token)

    monkeypatch.delenv("LLM_PROVIDER_KEY_MASTER", raising=False)
    importlib.reload(mod)


def test_production_without_master_key_raises(monkeypatch):
    import app.security.secrets as mod

    monkeypatch.delenv("LLM_PROVIDER_KEY_MASTER", raising=False)
    monkeypatch.setenv("APP_ENV", "production")
    importlib.reload(mod)
    with pytest.raises(mod.SecretCipherError):
        mod.encrypt_secret("anything")

    monkeypatch.setenv("APP_ENV", "development")
    importlib.reload(mod)


def test_dev_fallback_derives_key_from_jwt_secret(monkeypatch):
    import app.security.secrets as mod

    monkeypatch.delenv("LLM_PROVIDER_KEY_MASTER", raising=False)
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-dev-secret")
    importlib.reload(mod)

    token = mod.encrypt_secret("dev-key")
    assert mod.decrypt_secret(token) == "dev-key"
