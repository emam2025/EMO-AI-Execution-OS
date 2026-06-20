"""Phase 4.2.3 — CapabilityGuard: pre-execution validation.

Enforces: NO capability → NO execution.
Every execution MUST pass capability validation before proceeding.
Integrates with SensitiveToolRegistry for automatic audit logging.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from core.security.capabilities.capability_model import AccessMode, Capability, Scope
from core.security.capabilities.capability_registry import CapabilityRegistry
from core.security.capabilities.sensitive_tools import (
    SensitiveToolRegistry,
    Sensitivity,
)

logger = logging.getLogger("emo_ai.security.capability_guard")


class CapabilityViolation(Exception):
    """Raised when an execution violates capability policy."""

    def __init__(self, tool: str, reason: str):
        self.tool = tool
        self.reason = reason
        super().__init__(f"Capability violation for {tool}: {reason}")


class CapabilityGuard:
    """Pre-execution validation against capability policy.

    Usage:
        guard = CapabilityGuard(registry)
        guard.validate("web_fetch", {"url": "..."})
    """

    def __init__(
        self,
        registry: Optional[CapabilityRegistry] = None,
        sensitive_registry: Optional[SensitiveToolRegistry] = None,
    ):
        self._registry = registry or CapabilityRegistry()
        self._sensitive = sensitive_registry or SensitiveToolRegistry()

    @property
    def registry(self) -> CapabilityRegistry:
        return self._registry

    @property
    def sensitive_registry(self) -> SensitiveToolRegistry:
        return self._sensitive

    def validate(
        self,
        tool_name: str,
        inputs: Optional[Dict[str, Any]] = None,
        execution_id: str = "",
    ) -> Capability:
        """Validate that a tool execution is allowed.

        Args:
            tool_name: Name of the tool to validate.
            inputs: Input parameters (used for context-sensitive checks).
            execution_id: Optional execution ID for audit logging.

        Returns:
            The validated Capability for the tool.

        Raises:
            CapabilityViolation: If the execution is not permitted.
        """
        inputs = inputs or {}
        capability = self._registry.get_capability(tool_name)

        # RULE: NO capability → NO execution
        if not self._registry.has_capability(tool_name):
            raise CapabilityViolation(
                tool=tool_name,
                reason=f"No capability registered for '{tool_name}'",
            )

        # Network check
        url = inputs.get("url", "")
        if url and not capability.network:
            raise CapabilityViolation(
                tool=tool_name,
                reason="Network access blocked by capability policy",
            )

        # Filesystem checks
        path = inputs.get("path", "") or inputs.get("file_path", "")
        if path:
            if capability.filesystem == AccessMode.NONE:
                raise CapabilityViolation(
                    tool=tool_name,
                    reason="Filesystem access blocked by capability policy",
                )
            if '..' in path or path.startswith('/'):
                if capability.filesystem != AccessMode.FULL:
                    raise CapabilityViolation(
                        tool=tool_name,
                        reason=f"Path traversal or absolute path blocked: {path}",
                    )

        # Subprocess check
        command = inputs.get("command", "") or inputs.get("script", "")
        if command and not capability.subprocess:
            raise CapabilityViolation(
                tool=tool_name,
                reason="Subprocess execution blocked by capability policy",
            )

        # Sensitive tool audit (E2 integration)
        if self._sensitive.is_sensitive(tool_name, threshold=Sensitivity.MEDIUM):
            self._sensitive.audit_access(
                tool_name=tool_name,
                execution_id=execution_id or "unknown",
                principal="system",
                metadata={"inputs_keys": list(inputs.keys())},
            )

        logger.debug(
            "Capability validated for %s: network=%s fs=%s subprocess=%s",
            tool_name, capability.network, capability.filesystem, capability.subprocess,
        )
        return capability

    def validate_capability(self, tool_name: str, capability: Capability) -> bool:
        """Check if a capability is sufficient for a tool's requirements.

        Compares all permission fields: network, filesystem, subprocess, scopes.
        Returns True if capability meets or exceeds the tool's required capability.
        """
        required = self._registry.get_capability(tool_name)
        if not self._registry.has_capability(tool_name):
            return False
        if capability.network < required.network:
            return False
        if capability.subprocess < required.subprocess:
            return False
        if not capability.has_scope(Scope.EXECUTE):
            return False
        return True
