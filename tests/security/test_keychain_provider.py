"""Phase 2 — KeychainProvider security tests.

Groups:
  1. TestKeychainLifecycle  — set/get/delete cycles, missing key handling
  2. TestDevFallback        — ENV=development allows .env, ENV=production refuses
  3. TestAuditLogging       — every operation recorded in audit logs
  4. TestNoPlaintextStorage — no keys leak into logs or plaintext files

Ref: EXEC-DIRECTIVE-PHASE2-KEYCHAIN-001
Ref: Canon LAW 1, 2, 12
"""

import os
import io
import logging
from unittest.mock import patch, MagicMock

import keyring
import pytest

from core.security.keychain_provider import KeychainProvider, SERVICE_NAME, AUDIT_LOGGER


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def _reset_keyring_backend():
    """Use a non-interactive in-memory keyring backend for tests."""
    keyring.set_keyring(keyring.backends.fail.Keyring())
    yield
    keyring.set_keyring(keyring.backends.fail.Keyring())


def _make_memory_keyring():
    """Create an in-memory keyring backend for isolated testing."""
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


# ═══════════════════════════════════════════════════════════════════
# 1. Keychain lifecycle
# ═══════════════════════════════════════════════════════════════════

class TestKeychainLifecycle:
    """set/get/delete cycles, missing key handling."""

    def test_set_and_get(self):
        mem = _make_memory_keyring()
        keyring.set_keyring(mem)
        kp = KeychainProvider()
        kp.set("openrouter", "sk-or-test")
        assert kp.get("openrouter") == "sk-or-test"

    def test_get_missing(self):
        mem = _make_memory_keyring()
        keyring.set_keyring(mem)
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}, clear=True):
            kp = KeychainProvider()
            result = kp.get("nonexistent")
        assert result is None

    def test_delete(self):
        mem = _make_memory_keyring()
        keyring.set_keyring(mem)
        kp = KeychainProvider()
        kp.set("test_key", "test_value")
        assert kp.get("test_key") == "test_value"
        kp.delete("test_key")
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}, clear=True):
            assert kp.get("test_key") is None

    def test_delete_nonexistent_no_error(self):
        mem = _make_memory_keyring()
        keyring.set_keyring(mem)
        kp = KeychainProvider()
        kp.delete("does_not_exist")

    def test_set_overwrites(self):
        mem = _make_memory_keyring()
        keyring.set_keyring(mem)
        kp = KeychainProvider()
        kp.set("overwrite_test", "value1")
        kp.set("overwrite_test", "value2")
        assert kp.get("overwrite_test") == "value2"

    def test_multiple_accounts(self):
        mem = _make_memory_keyring()
        keyring.set_keyring(mem)
        kp = KeychainProvider()
        kp.set("openrouter", "or-key")
        kp.set("groq", "gq-key")
        kp.set("gemini", "gm-key")
        assert kp.get("openrouter") == "or-key"
        assert kp.get("groq") == "gq-key"
        assert kp.get("gemini") == "gm-key"


# ═══════════════════════════════════════════════════════════════════
# 2. Dev fallback
# ═══════════════════════════════════════════════════════════════════

class TestDevFallback:
    """ENV=development allows .env fallback, ENV=production refuses."""

    def test_production_no_fallback(self):
        mem = _make_memory_keyring()
        keyring.set_keyring(mem)
        with patch.dict(os.environ, {
            "ENVIRONMENT": "production",
            "OPENROUTER_API_KEY": "should-not-leak",
        }, clear=True):
            kp = KeychainProvider()
            result = kp.get("openrouter")
        assert result is None, "Production must not fall back to env"

    def test_development_fallback_success(self):
        mem = _make_memory_keyring()
        keyring.set_keyring(mem)
        with patch.dict(os.environ, {
            "ENVIRONMENT": "development",
            "OPENROUTER_API_KEY": "dev-key",
        }, clear=True):
            kp = KeychainProvider()
            result = kp.get("openrouter")
        assert result == "dev-key"

    def test_development_fallback_missing_env(self):
        mem = _make_memory_keyring()
        keyring.set_keyring(mem)
        with patch.dict(os.environ, {
            "ENVIRONMENT": "development",
        }, clear=True):
            kp = KeychainProvider()
            result = kp.get("openrouter")
        assert result is None

    def test_default_environment_is_production(self):
        mem = _make_memory_keyring()
        keyring.set_keyring(mem)
        with patch.dict(os.environ, {}, clear=True):
            kp = KeychainProvider()
            assert kp._is_dev is False

    def test_development_fallback_logs_warning(self):
        mem = _make_memory_keyring()
        keyring.set_keyring(mem)
        log_capture = io.StringIO()
        handler = logging.StreamHandler(log_capture)
        logger = logging.getLogger("emo_ai.keychain")
        logger.addHandler(handler)
        logger.setLevel(logging.WARNING)
        try:
            with patch.dict(os.environ, {
                "ENVIRONMENT": "development",
                "OPENROUTER_API_KEY": "dev-key",
            }, clear=True):
                kp = KeychainProvider()
                kp.get("openrouter")
        finally:
            logger.removeHandler(handler)
        output = log_capture.getvalue()
        assert "Using ENV fallback" in output
        assert "PRODUCTION MUST USE KEYRING" in output

    def test_keyring_available_in_dev_still_uses_keyring(self):
        mem = _make_memory_keyring()
        mem.set_password(SERVICE_NAME, "openrouter", "keyring-key")
        keyring.set_keyring(mem)
        with patch.dict(os.environ, {
            "ENVIRONMENT": "development",
            "OPENROUTER_API_KEY": "env-key",
        }, clear=True):
            kp = KeychainProvider()
            result = kp.get("openrouter")
        assert result == "keyring-key", "Keyring takes priority over env fallback"


# ═══════════════════════════════════════════════════════════════════
# 3. Audit logging
# ═══════════════════════════════════════════════════════════════════

class TestAuditLogging:
    """Every get/set/delete recorded in audit log."""

    def _capture_audit(self, func) -> str:
        log_capture = io.StringIO()
        handler = logging.StreamHandler(log_capture)
        AUDIT_LOGGER.addHandler(handler)
        AUDIT_LOGGER.setLevel(logging.INFO)
        try:
            func()
        finally:
            AUDIT_LOGGER.removeHandler(handler)
        return log_capture.getvalue()

    def test_get_logs_audit(self):
        mem = _make_memory_keyring()
        mem.set_password(SERVICE_NAME, "audit_test", "secret")
        keyring.set_keyring(mem)

        def do_get():
            kp = KeychainProvider()
            kp.get("audit_test")

        output = self._capture_audit(do_get)
        assert "action=read" in output
        assert "account=audit_test" in output
        assert "status=success" in output

    def test_set_logs_audit(self):
        mem = _make_memory_keyring()
        keyring.set_keyring(mem)

        def do_set():
            kp = KeychainProvider()
            kp.set("audit_test", "new_secret")

        output = self._capture_audit(do_set)
        assert "action=set" in output
        assert "account=audit_test" in output
        assert "status=success" in output

    def test_delete_logs_audit(self):
        mem = _make_memory_keyring()
        keyring.set_keyring(mem)

        def do_delete():
            kp = KeychainProvider()
            kp.set("audit_test", "x")
            kp.delete("audit_test")

        output = self._capture_audit(do_delete)
        assert "action=delete" in output
        assert "account=audit_test" in output
        assert "status=success" in output

    def test_get_miss_logs_audit(self):
        mem = _make_memory_keyring()
        keyring.set_keyring(mem)

        def do_get_miss():
            with patch.dict(os.environ, {"ENVIRONMENT": "production"}, clear=True):
                kp = KeychainProvider()
                kp.get("does_not_exist")

        output = self._capture_audit(do_get_miss)
        assert "status=miss" in output


# ═══════════════════════════════════════════════════════════════════
# 4. No plaintext storage
# ═══════════════════════════════════════════════════════════════════

class TestNoPlaintextStorage:
    """Keys must not leak into logs or plaintext files."""

    def test_key_not_in_log_output_on_miss(self):
        mem = _make_memory_keyring()
        keyring.set_keyring(mem)

        log_capture = io.StringIO()
        handler = logging.StreamHandler(log_capture)
        logger = logging.getLogger("emo_ai.keychain")
        logger.addHandler(handler)
        logger.setLevel(logging.WARNING)
        try:
            kp = KeychainProvider()
            with patch.dict(os.environ, {"ENVIRONMENT": "production"}, clear=True):
                kp.get("nonexistent")
        finally:
            logger.removeHandler(handler)

        output = log_capture.getvalue()
        assert "sk-or-" not in output
        assert "gsk_" not in output

    def test_key_not_serialized_in_error(self):
        from keyring.backend import KeyringBackend

        class ExplodingKeyring(KeyringBackend):
            priority = 0
            def get_password(self, service, username):
                raise keyring.errors.KeyringError("simulated failure")
            def set_password(self, service, username, password):
                raise NotImplementedError
            def delete_password(self, service, username):
                raise NotImplementedError

        keyring.set_keyring(ExplodingKeyring())

        log_capture = io.StringIO()
        handler = logging.StreamHandler(log_capture)
        logger = logging.getLogger("emo_ai.keychain")
        logger.addHandler(handler)
        logger.setLevel(logging.WARNING)
        try:
            kp = KeychainProvider()
            with patch.dict(os.environ, {"ENVIRONMENT": "production"}, clear=True):
                kp.get("nonexistent")
        finally:
            logger.removeHandler(handler)

        output = log_capture.getvalue()
        assert "sk-or-" not in output
        assert "gsk_" not in output

    def test_key_not_logged_in_audit(self):
        mem = _make_memory_keyring()
        mem.set_password(SERVICE_NAME, "super_secret_account", "sk-or-v1-abc123")
        keyring.set_keyring(mem)

        log_capture = io.StringIO()
        handler = logging.StreamHandler(log_capture)
        AUDIT_LOGGER.addHandler(handler)
        AUDIT_LOGGER.setLevel(logging.INFO)
        try:
            kp = KeychainProvider()
            kp.get("super_secret_account")
        finally:
            AUDIT_LOGGER.removeHandler(handler)

        output = log_capture.getvalue()
        assert "sk-or-v1-abc123" not in output, "Audit log must not contain the secret value"

    def test_cannot_read_key_from_source(self):
        source_path = os.path.join(os.path.dirname(__file__), "..", "..", "core", "security", "keychain_provider.py")
        with open(source_path) as f:
            source = f.read()
        assert "os.getenv" in source
        assert "OPENROUTER_API_KEY" not in source or "#" in source.split("OPENROUTER_API_KEY")[0][-5:]


# ═══════════════════════════════════════════════════════════════════
# 5. Edge cases
# ═══════════════════════════════════════════════════════════════════

class TestEdgeCases:
    """Empty values, special characters, service name isolation."""

    def test_empty_secret(self):
        mem = _make_memory_keyring()
        keyring.set_keyring(mem)
        kp = KeychainProvider()
        kp.set("empty_test", "")
        result = kp.get("empty_test")
        assert result == ""

    def test_service_name_isolation(self):
        mem = _make_memory_keyring()
        keyring.set_keyring(mem)
        kp1 = KeychainProvider(service="Service-A")
        kp2 = KeychainProvider(service="Service-B")
        kp1.set("shared_account", "value-a")
        kp2.set("shared_account", "value-b")
        assert kp1.get("shared_account") == "value-a"
        assert kp2.get("shared_account") == "value-b"

    def test_keyring_error_returns_none(self):
        from keyring.backend import KeyringBackend

        class BrokenKeyring(KeyringBackend):
            priority = 0
            def get_password(self, service, username):
                raise keyring.errors.KeyringError("broken")
            def set_password(self, service, username, password):
                raise NotImplementedError
            def delete_password(self, service, username):
                raise NotImplementedError

        keyring.set_keyring(BrokenKeyring())

        with patch.dict(os.environ, {"ENVIRONMENT": "production"}, clear=True):
            kp = KeychainProvider()
            result = kp.get("any_key")
        assert result is None
