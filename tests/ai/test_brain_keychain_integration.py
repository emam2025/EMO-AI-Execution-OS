"""Phase 2 — Brain/Keychain integration tests.

Groups:
  1. TestBrainKeychainIntegration — brain.py retrieves keys via keychain
  2. TestNoOsGetenvDirect          — no direct os.getenv() for LLM keys in brain.py

Ref: EXEC-DIRECTIVE-PHASE2-KEYCHAIN-001
"""

import importlib
import os
from unittest.mock import patch

import keyring
import pytest

from core.security.keychain_provider import SERVICE_NAME


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

def _make_memory_keyring():
    from keyring.backends import fail
    class MemoryKeyring(fail.Keyring):
        def __init__(self):
            self._storage: dict[tuple[str, str], str] = {}
        def get_password(self, service, username):
            return self._storage.get((service, username))
        def set_password(self, service, username, password):
            self._storage[(service, username)] = password
        def delete_password(self, service, username):
            try:
                del self._storage[(service, username)]
            except KeyError:
                raise keyring.errors.PasswordDeleteError("not found")
    return MemoryKeyring()


def _reload_brain():
    """Reload brain so module-level _keychain picks up patched os.environ."""
    import brain as brain_mod
    importlib.reload(brain_mod)
    return brain_mod


@pytest.fixture(autouse=True)
def _reset_keyring():
    keyring.set_keyring(keyring.backends.fail.Keyring())
    yield
    keyring.set_keyring(keyring.backends.fail.Keyring())


# ═══════════════════════════════════════════════════════════════════
# 1. Brain keychain integration
# ═══════════════════════════════════════════════════════════════════

class TestBrainKeychainIntegration:
    """brain.py retrieves keys via KeychainProvider."""

    def test_brain_uses_keychain_for_openrouter(self):
        mem = _make_memory_keyring()
        mem.set_password(SERVICE_NAME, "openrouter", "sk-or-keychain-key")
        keyring.set_keyring(mem)

        with patch.dict(os.environ, {
            "ENVIRONMENT": "production",
            "LLM_PROVIDER": "openrouter",
            "LLM_MODEL": "test-model",
        }, clear=True):
            brain_mod = _reload_brain()
            brain = brain_mod.Brain()

        assert brain._client.api_key == "sk-or-keychain-key"

    def test_brain_uses_keychain_for_groq(self):
        mem = _make_memory_keyring()
        mem.set_password(SERVICE_NAME, "groq", "gsk-keychain-key")
        keyring.set_keyring(mem)

        with patch.dict(os.environ, {
            "ENVIRONMENT": "production",
            "LLM_PROVIDER": "groq",
            "LLM_MODEL": "test-model",
        }, clear=True):
            brain_mod = _reload_brain()
            brain = brain_mod.Brain()

        assert brain._client.api_key == "gsk-keychain-key"

    def test_brain_uses_keychain_for_gemini(self):
        mem = _make_memory_keyring()
        mem.set_password(SERVICE_NAME, "gemini", "gm-keychain-key")
        keyring.set_keyring(mem)

        with patch.dict(os.environ, {
            "ENVIRONMENT": "production",
            "LLM_PROVIDER": "gemini",
            "LLM_MODEL": "test-model",
        }, clear=True):
            brain_mod = _reload_brain()
            brain = brain_mod.Brain()

        assert brain._client.api_key == "gm-keychain-key"

    def test_brain_fallback_development_env(self):
        mem = _make_memory_keyring()
        keyring.set_keyring(mem)

        with patch.dict(os.environ, {
            "ENVIRONMENT": "development",
            "LLM_PROVIDER": "openrouter",
            "LLM_MODEL": "test-model",
            "OPENROUTER_API_KEY": "sk-or-dev-env-key",
        }, clear=True):
            brain_mod = _reload_brain()
            brain = brain_mod.Brain()

        assert brain._client.api_key == "sk-or-dev-env-key"

    def test_brain_production_no_key_uses_placeholder(self):
        mem = _make_memory_keyring()
        keyring.set_keyring(mem)

        with patch.dict(os.environ, {
            "ENVIRONMENT": "production",
            "LLM_PROVIDER": "openrouter",
            "LLM_MODEL": "test-model",
        }, clear=True):
            brain_mod = _reload_brain()
            brain = brain_mod.Brain()

        assert "placeholder" in brain._client.api_key

    def test_brain_ollama_no_keychain(self):
        mem = _make_memory_keyring()
        keyring.set_keyring(mem)

        with patch.dict(os.environ, {
            "ENVIRONMENT": "production",
            "LLM_PROVIDER": "ollama",
            "LLM_MODEL": "test-model",
        }, clear=True):
            brain_mod = _reload_brain()
            brain = brain_mod.Brain()

        assert brain._client.api_key == "ollama"


# ═══════════════════════════════════════════════════════════════════
# 2. No direct os.getenv for sensitive keys
# ═══════════════════════════════════════════════════════════════════

class TestNoOsGetenvDirect:
    """brain.py must not use os.getenv() directly for LLM keys."""

    def test_brain_no_direct_os_getenv_for_keys(self):
        brain_path = os.path.join(os.path.dirname(__file__), "..", "..", "brain.py")
        with open(brain_path) as f:
            source = f.read()

        lines = source.split("\n")
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if "os.getenv" in stripped and not stripped.startswith("#"):
                if any(key in stripped for key in ["OPENROUTER", "GROQ", "GEMINI"]):
                    pytest.fail(f"brain.py:{i} — direct os.getenv for API key: {stripped}")

    def test_main_no_direct_os_getenv_for_keys(self):
        main_path = os.path.join(os.path.dirname(__file__), "..", "..", "main.py")
        with open(main_path) as f:
            source = f.read()

        lines = source.split("\n")
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if "os.getenv" in stripped and not stripped.startswith("#"):
                if any(key in stripped for key in ["OPENROUTER", "GROQ", "GEMINI"]):
                    pytest.fail(f"main.py:{i} — direct os.getenv for API key: {stripped}")
