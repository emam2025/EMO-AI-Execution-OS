"""E3.2 — RuntimeVault: secure in-memory secret storage.

Stores secrets with encryption at rest, TTL expiration,
and scope-based access control.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("emo_ai.secrets.vault")


@dataclass
class SecretEntry:
    """A single secret stored in the vault."""
    key: str
    value: str
    scope: str = "global"
    created_at: float = 0.0
    expires_at: float = 0.0
    access_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


class RuntimeVault:
    """Secure in-memory secret storage with encryption and TTL.

    Usage:
        vault = RuntimeVault(master_key="my-encryption-key")
        vault.store("db_password", "s3cr3t", scope="exec_123", ttl=300)
        val = vault.retrieve("db_password", scope="exec_123")
    """

    def __init__(self, master_key: str = "") -> None:
        self._lock = threading.Lock()
        self._secrets: Dict[str, SecretEntry] = {}
        self._master_key = master_key or os.urandom(32).hex()
        self._started_at = time.time()

    # ── CRUD ──────────────────────────────────────────────────────

    def store(
        self,
        key: str,
        value: str,
        scope: str = "global",
        ttl: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Store a secret.

        Args:
            key: Unique identifier for the secret.
            value: The secret value.
            scope: Access scope (e.g. execution_id, tool_name).
            ttl: Time-to-live in seconds (0 = no expiry).
            metadata: Optional metadata.

        Returns:
            The encrypted secret ID.
        """
        now = time.time()
        entry = SecretEntry(
            key=key,
            value=self._encrypt(value),
            scope=scope,
            created_at=now,
            expires_at=(now + ttl) if ttl > 0 else 0.0,
            access_count=0,
            metadata=metadata or {},
        )
        with self._lock:
            self._secrets[key] = entry
        logger.debug("Stored secret '%s' (scope=%s, ttl=%s)", key, scope, ttl or "none")
        return key

    def retrieve(self, key: str, scope: str = "") -> Optional[str]:
        """Retrieve a secret value.

        Args:
            key: The secret identifier.
            scope: Required scope for access.

        Returns:
            The decrypted secret value, or None if not found/expired/wrong scope.
        """
        with self._lock:
            entry = self._secrets.get(key)
            if entry is None:
                return None
            if self._is_expired(entry):
                del self._secrets[key]
                logger.warning("Secret '%s' expired and removed", key)
                return None
            if scope and entry.scope != "global" and entry.scope != scope:
                logger.warning("Scope mismatch for '%s': required=%s, got=%s", key, entry.scope, scope)
                return None
            entry.access_count += 1
        return self._decrypt(entry.value)

    def delete(self, key: str) -> bool:
        """Delete a secret from the vault."""
        with self._lock:
            if key not in self._secrets:
                return False
            del self._secrets[key]
        logger.debug("Deleted secret '%s'", key)
        return True

    def exists(self, key: str) -> bool:
        """Check if a secret exists and is not expired."""
        with self._lock:
            entry = self._secrets.get(key)
            if entry is None:
                return False
            if self._is_expired(entry):
                del self._secrets[key]
                return False
            return True

    def list_secrets(self, scope: str = "") -> List[str]:
        """List all non-expired secret keys, optionally filtered by scope."""
        with self._lock:
            expired = []
            result = []
            for key, entry in self._secrets.items():
                if self._is_expired(entry):
                    expired.append(key)
                elif not scope or entry.scope == scope or entry.scope == "global":
                    result.append(key)
            for k in expired:
                del self._secrets[k]
            return result

    # ── Expiration ────────────────────────────────────────────────

    def _is_expired(self, entry: SecretEntry) -> bool:
        if entry.expires_at <= 0:
            return False
        return time.time() > entry.expires_at

    def purge_expired(self) -> int:
        """Remove all expired secrets. Returns count of purged secrets."""
        now = time.time()
        with self._lock:
            expired = [k for k, e in self._secrets.items() if e.expires_at > 0 and now > e.expires_at]
            for k in expired:
                del self._secrets[k]
        if expired:
            logger.info("Purged %d expired secrets", len(expired))
        return len(expired)

    # ── Encryption ────────────────────────────────────────────────

    def _encrypt(self, value: str) -> str:
        """Simple XOR-based encryption with HMAC integrity.

        NOTE: This is a lightweight obfuscation for in-memory storage.
        For production, replace with AES-GCM or similar.
        """
        if not self._master_key:
            return value
        h = hmac.new(self._master_key.encode(), value.encode(), hashlib.sha256).hexdigest()[:16]
        key_bytes = self._master_key.encode()
        encrypted_chars = []
        for i, c in enumerate(value):
            encrypted_chars.append(chr(ord(c) ^ key_bytes[i % len(key_bytes)]))
        return f"{h}:{''.join(encrypted_chars)}"

    def _decrypt(self, encrypted: str) -> str:
        """Decrypt a value encrypted with _encrypt, verifying HMAC integrity."""
        if not self._master_key or ":" not in encrypted:
            return encrypted
        expected_hmac, payload = encrypted.split(":", 1)
        key_bytes = self._master_key.encode()
        decrypted_chars = []
        for i, c in enumerate(payload):
            decrypted_chars.append(chr(ord(c) ^ key_bytes[i % len(key_bytes)]))
        plaintext = "".join(decrypted_chars)
        actual_hmac = hmac.new(self._master_key.encode(), plaintext.encode(), hashlib.sha256).hexdigest()[:16]
        if not hmac.compare_digest(expected_hmac, actual_hmac):
            logger.error("HMAC integrity check failed for secret")
            return ""
        return plaintext

    # ── Stats ─────────────────────────────────────────────────────

    def stats(self) -> Dict[str, Any]:
        """Return vault statistics."""
        with self._lock:
            return {
                "total_secrets": len(self._secrets),
                "uptime": time.time() - self._started_at,
                "keys": list(self._secrets.keys()),
            }
