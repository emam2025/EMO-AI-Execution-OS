"""E3.2 — RuntimeVault: secure in-memory secret storage.

Stores secrets with AES-128-CBC + HMAC-SHA256 encryption at rest,
TTL expiration, and scope-based access control.

Uses Fernet (authenticated encryption) from the cryptography library.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import time
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from cryptography.fernet import Fernet, InvalidToken

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

    Uses Fernet (AES-128-CBC with HMAC-SHA256) for authenticated encryption.

    Usage:
        vault = RuntimeVault()
        vault.store("db_password", "<your-password>", scope="exec_123", ttl=300)
        val = vault.retrieve("db_password", scope="exec_123")
    """

    def __init__(self, master_key: str = "") -> None:
        self._lock = threading.Lock()
        self._secrets: Dict[str, SecretEntry] = {}
        if master_key:
            derived = hashlib.sha256(master_key.encode()).digest()
            self._fernet = Fernet(base64.urlsafe_b64encode(derived))
        else:
            self._fernet = Fernet(Fernet.generate_key())
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
            The secret key.
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

    # ── Encryption (Fernet — AES-128-CBC with HMAC-SHA256) ────────

    def _encrypt(self, value: str) -> str:
        """Encrypt a value using Fernet (AES-128-CBC + HMAC-SHA256)."""
        return self._fernet.encrypt(value.encode()).decode()

    def _decrypt(self, encrypted: str) -> str:
        """Decrypt a value encrypted with _encrypt, verifying HMAC integrity."""
        try:
            return self._fernet.decrypt(encrypted.encode()).decode()
        except InvalidToken:
            logger.error("Fernet integrity check failed for secret")
            return ""

    # ── Stats ─────────────────────────────────────────────────────

    def stats(self) -> Dict[str, Any]:
        """Return vault statistics (no secret keys exposed)."""
        with self._lock:
            return {
                "total_secrets": len(self._secrets),
                "uptime": time.time() - self._started_at,
            }
