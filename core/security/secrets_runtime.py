"""SecretsRuntime — Ephemeral Secret Injection.

Injects secrets into sandboxed tool execution contexts.
Prevents leakage via logs, events, or stdout.
All access is audited via EventBus.

Ref: Phase E.3 — Secrets Runtime (Ephemeral Secret Injection)
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from core.models.secrets import SecretRef, SecretScope

if TYPE_CHECKING:
    from core.interfaces.event_bus import IEventBus

logger = logging.getLogger(__name__)


class SecretsRuntime:
    """Ephemeral secret injection and management.

    Injects secrets into sandboxed tool execution contexts.
    Prevents leakage via logs, events, or stdout.
    All access is audited via EventBus.
    """

    def __init__(self, event_bus: Optional[IEventBus] = None) -> None:
        self._event_bus = event_bus
        self._secrets: Dict[str, str] = {}  # secret_id → hashed_value
        self._refs: Dict[str, SecretRef] = {}  # secret_id → SecretRef
        self._access_log: List[Dict[str, Any]] = []
        self._active_injections: Dict[str, List[str]] = {}  # tool_id → [secret_ids]
        self._secret_timestamps: Dict[str, float] = {}  # secret_id → registration_time

    def _encrypt(self, value: str) -> str:
        """Mock encryption — SHA-256 hash of the value.

        In production, use AES-256-GCM or similar.
        This is a V1 placeholder that proves the value is not stored in plaintext.
        """
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def _decrypt(self, hashed: str, original: str) -> str:
        """Mock decryption — returns original value.

        In production, use proper key management.
        For V1, the caller passes the original value during inject.
        """
        return original

    def register_secret(self, secret_id: str, value: str, ref: SecretRef) -> None:
        """Register a secret with scope and access control.

        The secret value is stored hashed (not in plaintext).
        """
        self._secrets[secret_id] = self._encrypt(value)
        self._refs[secret_id] = ref
        self._secret_timestamps[secret_id] = time.time()
        logger.info("Secret '%s' registered with scope=%s", secret_id, ref.scope.value)

    def inject_for_tool(
        self,
        tool_id: str,
        requested_secrets: List[str],
        raw_values: Optional[Dict[str, str]] = None,
    ) -> Dict[str, str]:
        """Inject secrets for tool execution. Returns decrypted secrets.

        Only returns secrets the tool is authorized to access.
        Respects scope, allowed_tools, and expiration.
        All access is logged and published as audit event.

        Args:
            tool_id: The tool requesting secrets.
            requested_secrets: List of secret_ids to inject.
            raw_values: Map of secret_id → original plaintext (for V1 mock decrypt).

        Returns:
            Dict of secret_id → decrypted value for authorized secrets.
        """
        if raw_values is None:
            raw_values = {}

        now = time.time()
        injected: Dict[str, str] = {}
        denied: List[str] = []

        for secret_id in requested_secrets:
            ref = self._refs.get(secret_id)
            if ref is None:
                denied.append(secret_id)
                continue

            if now - self._secret_timestamps.get(secret_id, 0) > ref.expiration_seconds:
                denied.append(secret_id)
                continue

            if ref.scope == SecretScope.TOOL:
                if ref.allowed_tools and tool_id not in ref.allowed_tools:
                    denied.append(secret_id)
                    continue

            raw = raw_values.get(secret_id, "")
            decrypted = self._decrypt(self._secrets.get(secret_id, ""), raw)
            injected[secret_id] = decrypted

        if injected:
            self._active_injections.setdefault(tool_id, [])
            self._active_injections[tool_id].extend(injected.keys())

        for secret_id in injected:
            self._log_access(tool_id, secret_id, "injected")

        for secret_id in denied:
            self._log_access(tool_id, secret_id, "denied")

        return injected

    def revoke_all_for_tool(self, tool_id: str) -> None:
        """Revoke all secrets injected for a tool after execution.

        Clears the active injection list for the tool.
        """
        secret_ids = self._active_injections.pop(tool_id, [])
        for secret_id in secret_ids:
            self._log_access(tool_id, secret_id, "revoked")

    def is_secret_registered(self, secret_id: str) -> bool:
        """Check if a secret is registered."""
        return secret_id in self._secrets

    def get_ref(self, secret_id: str) -> Optional[SecretRef]:
        """Get the SecretRef for a registered secret."""
        return self._refs.get(secret_id)

    def get_access_log(self) -> List[Dict[str, Any]]:
        """Return the full access audit log."""
        return list(self._access_log)

    def _log_access(self, tool_id: str, secret_id: str, action: str) -> None:
        """Log secret access and publish audit event.

        The log entry never contains the actual secret value.
        """
        entry = {
            "tool_id": tool_id,
            "secret_id": secret_id,
            "action": action,
        }
        self._access_log.append(entry)
        self._publish_audit_event(tool_id, secret_id, action)

    def _publish_audit_event(
        self, tool_id: str, secret_id: str, action: str
    ) -> None:
        """Publish SECURITY_VIOLATION or audit event for secret access."""
        if self._event_bus is None:
            return

        from core.models.event import EventTopic, ExecutionEvent

        event = ExecutionEvent(
            topic=EventTopic.SECURITY_VIOLATION,
            payload={
                "tool_id": tool_id,
                "secret_id": secret_id,
                "action": action,
                "requested_capability": "secret_access",
                "reason": f"Secret '{secret_id}' {action} for tool '{tool_id}'",
                "action_taken": "audited" if action == "injected" else action,
            },
            trace_id=f"secrets-{tool_id}-{secret_id}",
        )
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(
                self._event_bus.publish(EventTopic.SECURITY_VIOLATION, event)
            )
        except RuntimeError:
            pass
