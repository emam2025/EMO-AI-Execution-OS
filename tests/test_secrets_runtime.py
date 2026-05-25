"""Tests for Phase E3 — Secrets Runtime.

RuntimeVault, SecretInjector, ScopedCredentials, Secret Expiration.
"""

import time

import pytest

from core.runtime.secrets import (
    RuntimeVault,
    SecretInjector,
    CredentialManager,
    ScopedCredential,
)


# ═══════════════════════════════════════════════════════════════════
# E3.2 — RuntimeVault
# ═══════════════════════════════════════════════════════════════════

class TestRuntimeVault:
    def test_store_and_retrieve(self):
        vault = RuntimeVault()
        vault.store("my_key", "s3cr3t_value", scope="exec_1")
        val = vault.retrieve("my_key", scope="exec_1")
        assert val == "s3cr3t_value"

    def test_retrieve_wrong_scope(self):
        vault = RuntimeVault()
        vault.store("key", "value", scope="exec_a")
        val = vault.retrieve("key", scope="exec_b")
        assert val is None

    def test_retrieve_global_scope(self):
        vault = RuntimeVault()
        vault.store("key", "value", scope="global")
        val = vault.retrieve("key", scope="any_scope")
        assert val == "value"

    def test_retrieve_nonexistent(self):
        vault = RuntimeVault()
        assert vault.retrieve("nobody") is None

    def test_delete(self):
        vault = RuntimeVault()
        vault.store("key", "value")
        assert vault.delete("key") is True
        assert vault.retrieve("key") is None
        assert vault.delete("nobody") is False

    def test_exists(self):
        vault = RuntimeVault()
        vault.store("key", "value")
        assert vault.exists("key") is True
        assert vault.exists("nobody") is False

    def test_list_secrets(self):
        vault = RuntimeVault()
        vault.store("k1", "v1", scope="exec_1")
        vault.store("k2", "v2", scope="exec_2")
        vault.store("k3", "v3", scope="global")
        assert len(vault.list_secrets()) == 3
        assert len(vault.list_secrets(scope="exec_1")) == 2  # k1 + k3 (global)

    def test_expiration(self):
        vault = RuntimeVault()
        vault.store("key", "value", ttl=0.05)
        assert vault.exists("key") is True
        time.sleep(0.06)
        assert vault.exists("key") is False
        assert vault.retrieve("key") is None

    def test_purge_expired(self):
        vault = RuntimeVault()
        vault.store("k1", "v1", ttl=0.02)
        vault.store("k2", "v2")
        vault.store("k3", "v3", ttl=0.02)
        time.sleep(0.03)
        count = vault.purge_expired()
        assert count == 2
        assert vault.exists("k1") is False
        assert vault.exists("k2") is True
        assert vault.exists("k3") is False

    def test_stats(self):
        vault = RuntimeVault()
        vault.store("k1", "v1")
        vault.store("k2", "v2")
        stats = vault.stats()
        assert stats["total_secrets"] == 2

    def test_encryption_roundtrip(self):
        vault = RuntimeVault(master_key="test-master-key-12345")
        vault.store("key", "super-secret-value")
        val = vault.retrieve("key")
        assert val == "super-secret-value"
        # Verify it's encrypted in memory
        raw = vault._secrets["key"].value
        assert "super-secret-value" not in raw or raw.startswith("super") is False


# ═══════════════════════════════════════════════════════════════════
# E3.1 — SecretInjector
# ═══════════════════════════════════════════════════════════════════

class TestSecretInjector:
    def test_inject_single_secret(self):
        vault = RuntimeVault()
        vault.store("DB_PASSWORD", "p@ss", scope="exec_1")
        injector = SecretInjector(vault)
        env = {}
        count = injector.inject(env, "exec_1", ["DB_PASSWORD"], scope="exec_1")
        assert count == 1
        assert env["EMO_SECRET_DB_PASSWORD"] == "p@ss"

    def test_inject_missing_secret(self):
        vault = RuntimeVault()
        injector = SecretInjector(vault)
        env = {}
        count = injector.inject(env, "exec_1", ["MISSING"])
        assert count == 0

    def test_inject_all_for_scope(self):
        vault = RuntimeVault()
        vault.store("KEY_A", "val_a", scope="exec_1")
        vault.store("KEY_B", "val_b", scope="exec_1")
        vault.store("KEY_C", "val_c", scope="exec_2")
        injector = SecretInjector(vault)
        env = {}
        count = injector.inject_all_for_scope(env, "exec_1", scope="exec_1")
        assert count == 2
        assert "EMO_SECRET_KEY_A" in env
        assert "EMO_SECRET_KEY_B" in env
        assert "EMO_SECRET_KEY_C" not in env

    def test_cleanup_removes_env_vars(self):
        vault = RuntimeVault()
        vault.store("KEY", "val", scope="exec_1")
        injector = SecretInjector(vault)
        env = {}
        injector.inject(env, "exec_1", ["KEY"], scope="exec_1")
        assert "EMO_SECRET_KEY" in env
        injector.cleanup(env, "exec_1")
        assert "EMO_SECRET_KEY" not in env

    def test_cleanup_removes_vault_secrets(self):
        vault = RuntimeVault()
        vault.store("KEY", "val", scope="exec_1")
        injector = SecretInjector(vault)
        env = {}
        injector.inject(env, "exec_1", ["KEY"], scope="exec_1")
        injector.cleanup(env, "exec_1")
        assert vault.exists("KEY") is False

    def test_injection_log(self):
        vault = RuntimeVault()
        vault.store("KEY", "val", scope="exec_1")
        injector = SecretInjector(vault)
        env = {}
        injector.inject(env, "exec_1", ["KEY"], scope="exec_1")
        log = injector.injection_log()
        assert len(log) == 1
        assert log[0]["secret_key"] == "KEY"
        assert log[0]["execution_id"] == "exec_1"

    def test_inject_multiple_secrets(self):
        vault = RuntimeVault()
        vault.store("A", "a_val", scope="exec_1")
        vault.store("B", "b_val", scope="exec_1")
        vault.store("C", "c_val", scope="exec_1")
        injector = SecretInjector(vault)
        env = {}
        count = injector.inject(env, "exec_1", ["A", "B", "C"], scope="exec_1")
        assert count == 3
        assert env["EMO_SECRET_A"] == "a_val"
        assert env["EMO_SECRET_B"] == "b_val"
        assert env["EMO_SECRET_C"] == "c_val"


# ═══════════════════════════════════════════════════════════════════
# E3.3 — CredentialManager (ScopedCredentials)
# ═══════════════════════════════════════════════════════════════════

class TestCredentialManager:
    def test_create_credential(self):
        vault = RuntimeVault()
        mgr = CredentialManager(vault)
        cred = mgr.create_credential("exec_1", "api_token", scopes=["read:db"])
        assert cred.execution_id == "exec_1"
        assert cred.credential_type == "api_token"
        assert "read:db" in cred.scopes
        assert len(cred.credential_value) == 48

    def test_validate_credential(self):
        vault = RuntimeVault()
        mgr = CredentialManager(vault)
        cred = mgr.create_credential("exec_1", "api_token")
        assert mgr.validate_credential(cred.credential_id, "exec_1") is True
        assert mgr.validate_credential(cred.credential_id, "exec_2") is False

    def test_revoke_credential(self):
        vault = RuntimeVault()
        mgr = CredentialManager(vault)
        cred = mgr.create_credential("exec_1", "api_token")
        assert mgr.revoke_credential(cred.credential_id) is True
        assert mgr.validate_credential(cred.credential_id, "exec_1") is False

    def test_revoke_for_execution(self):
        vault = RuntimeVault()
        mgr = CredentialManager(vault)
        mgr.create_credential("exec_1", "token_a")
        mgr.create_credential("exec_1", "token_b")
        mgr.create_credential("exec_2", "token_c")
        count = mgr.revoke_for_execution("exec_1")
        assert count == 2
        # exec_2's credential should still be active
        assert len(mgr.list_active()) == 1
        assert len(mgr.list_active(execution_id="exec_2")) == 1

    def test_list_active(self):
        vault = RuntimeVault()
        mgr = CredentialManager(vault)
        mgr.create_credential("exec_1", "token_a")
        mgr.create_credential("exec_2", "token_b")
        active = mgr.list_active()
        assert len(active) == 2
        exec1 = mgr.list_active(execution_id="exec_1")
        assert len(exec1) == 1
        assert exec1[0].credential_type == "token_a"

    def test_purge_expired(self):
        vault = RuntimeVault()
        mgr = CredentialManager(vault)
        mgr.create_credential("exec_1", "token_a", ttl=0.02)
        mgr.create_credential("exec_2", "token_b")
        time.sleep(0.03)
        count = mgr.purge_expired()
        assert count == 1
        assert len(mgr.list_active()) == 1

    def test_revoke_nonexistent(self):
        vault = RuntimeVault()
        mgr = CredentialManager(vault)
        assert mgr.revoke_credential("nobody") is False


# ═══════════════════════════════════════════════════════════════════
# E3 — Integration
# ═══════════════════════════════════════════════════════════════════

class TestE3Integration:
    def test_vault_to_injector_to_cleanup(self):
        vault = RuntimeVault()
        vault.store("DB_PASS", "s3cr3t", scope="exec_99", ttl=300)
        injector = SecretInjector(vault)
        env = {}
        count = injector.inject(env, "exec_99", ["DB_PASS"], scope="exec_99")
        assert count == 1
        assert env["EMO_SECRET_DB_PASS"] == "s3cr3t"

        # Simulate execution running, then cleanup
        injector.cleanup(env, "exec_99")
        assert "EMO_SECRET_DB_PASS" not in env
        assert vault.exists("DB_PASS") is False

    def test_credential_with_injector(self):
        vault = RuntimeVault()
        mgr = CredentialManager(vault)
        cred = mgr.create_credential("exec_50", "db_password", ttl=300)

        # Store the credential value as a vault secret
        vault.store("DB_CRED", cred.credential_value, scope="exec_50", ttl=300)

        injector = SecretInjector(vault)
        env = {}
        injector.inject(env, "exec_50", ["DB_CRED"], scope="exec_50")
        assert env["EMO_SECRET_DB_CRED"] == cred.credential_value

    def test_full_lifecycle(self):
        vault = RuntimeVault()
        mgr = CredentialManager(vault)
        injector = SecretInjector(vault)

        # Store original secret
        vault.store("API_KEY", "sk-orig-12345", scope="exec_100", ttl=3600)

        # Create scoped credential
        cred = mgr.create_credential("exec_100", "scoped_token", scopes=["read:api"])

        # Inject into environment
        env = {}
        injector.inject(env, "exec_100", ["API_KEY"], scope="exec_100")
        assert env["EMO_SECRET_API_KEY"] == "sk-orig-12345"

        # Validate credential
        assert mgr.validate_credential(cred.credential_id, "exec_100") is True

        # Revoke all for execution
        mgr.revoke_for_execution("exec_100")

        # Cleanup
        injector.cleanup(env, "exec_100")
        assert "EMO_SECRET_API_KEY" not in env
        assert mgr.validate_credential(cred.credential_id, "exec_100") is False
