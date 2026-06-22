"""E3.3 — ScopedCredentials: per-execution credential management.

Generates scoped API keys, limited tokens, and temporary credentials
that are automatically revoked after the execution completes.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.runtime.secrets.vault import RuntimeVault

logger = logging.getLogger("emo_ai.secrets.credentials")


@dataclass
class ScopedCredential:
    """A credential scoped to a specific execution."""
    credential_id: str
    execution_id: str
    credential_type: str
    credential_value: str
    scopes: List[str] = field(default_factory=list)
    created_at: float = 0.0
    expires_at: float = 0.0
    is_revoked: bool = False


class CredentialManager:
    """Manages scoped credentials with automatic revocation.

    Usage:
        mgr = CredentialManager(vault)
        cred = mgr.create_credential("exec_123", "api_token", scopes=["read:db"])
        token = cred.credential_value
        # ... execution uses token ...
        mgr.revoke_for_execution("exec_123")
    """

    def __init__(self, vault: RuntimeVault) -> None:
        self._vault = vault
        self._lock = threading.Lock()
        self._credentials: Dict[str, ScopedCredential] = {}

    def create_credential(
        self,
        execution_id: str,
        credential_type: str,
        scopes: Optional[List[str]] = None,
        ttl: float = 3600.0,
    ) -> ScopedCredential:
        """Create a scoped credential for an execution.

        Args:
            execution_id: The execution this credential is for.
            credential_type: Type of credential (api_token, db_password, etc.).
            scopes: Access scopes for this credential.
            ttl: Time-to-live in seconds (default 1 hour).

        Returns:
            A ScopedCredential with a generated value.
        """
        credential_id = uuid.uuid4().hex
        value = self._generate_value(credential_id, execution_id)
        now = time.time()
        cred = ScopedCredential(
            credential_id=credential_id,
            execution_id=execution_id,
            credential_type=credential_type,
            credential_value=value,
            scopes=scopes or [],
            created_at=now,
            expires_at=(now + ttl) if ttl > 0 else 0.0,
        )
        with self._lock:
            self._credentials[credential_id] = cred

        self._vault.store(
            f"cred:{credential_id}",
            value,
            scope=execution_id,
            ttl=ttl,
            metadata={"type": credential_type, "scopes": scopes or []},
        )
        logger.info(
            "Created %s credential %s for exec %s (ttl=%s)",
            credential_type, credential_id[:8], execution_id, ttl,
        )
        return cred

    def validate_credential(self, credential_id: str, execution_id: str) -> bool:
        """Check if a credential is valid and not revoked."""
        with self._lock:
            cred = self._credentials.get(credential_id)
            if cred is None:
                return False
            if cred.is_revoked:
                return False
            if cred.execution_id != execution_id:
                return False
            if cred.expires_at > 0 and time.time() > cred.expires_at:
                cred.is_revoked = True
                return False
            return True

    def revoke_credential(self, credential_id: str) -> bool:
        """Revoke a single credential."""
        with self._lock:
            cred = self._credentials.get(credential_id)
            if cred is None:
                return False
            cred.is_revoked = True
        self._vault.delete(f"cred:{credential_id}")
        logger.debug("Revoked credential %s", credential_id[:8])
        return True

    def revoke_for_execution(self, execution_id: str) -> int:
        """Revoke all credentials for a given execution."""
        count = 0
        with self._lock:
            for cred in self._credentials.values():
                if cred.execution_id == execution_id and not cred.is_revoked:
                    cred.is_revoked = True
                    self._vault.delete(f"cred:{cred.credential_id}")
                    count += 1
        if count:
            logger.info("Revoked %d credentials for exec %s", count, execution_id)
        return count

    def list_active(self, execution_id: str = "") -> List[ScopedCredential]:
        """List active (non-revoked, non-expired) credentials."""
        now = time.time()
        with self._lock:
            result = []
            for cred in self._credentials.values():
                if cred.is_revoked:
                    continue
                if cred.expires_at > 0 and now > cred.expires_at:
                    cred.is_revoked = True
                    continue
                if not execution_id or cred.execution_id == execution_id:
                    result.append(cred)
            return result

    def purge_expired(self) -> int:
        """Remove all expired credentials from the registry."""
        now = time.time()
        with self._lock:
            expired = [
                cid for cid, c in self._credentials.items()
                if c.expires_at > 0 and now > c.expires_at
            ]
            for cid in expired:
                del self._credentials[cid]
                self._vault.delete(f"cred:{cid}")
        return len(expired)

    def _generate_value(self, credential_id: str, execution_id: str) -> str:
        """Generate a secure random credential value."""
        raw = f"{credential_id}:{execution_id}:{os.urandom(32).hex()}:{time.time()}"
        return hashlib.sha256(raw.encode()).hexdigest()[:48]



