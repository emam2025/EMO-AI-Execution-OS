"""Phase 4.2 — Isolation CapabilityGuard.

Isolation-specific capability validation that wraps the base
CapabilityGuard and adds SandboxContext validation per the
design models in artifacts/design/phase4/models/.

Enforces: NO capability → NO execution (RULE 3).
All checks align with Canon LAW 10, LAW 23-27.

Ref: DEVELOPER.md §15.15b §4.2
Ref: Canon RULE 3 (Capability First)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from core.runtime.sandbox.sandbox_context import (
    SandboxContext,
    FilesystemMode,
    NetworkMode,
)
from core.security.capabilities.capability_guard import (
    CapabilityGuard as BaseCapabilityGuard,
    CapabilityViolation,
)
from core.security.capabilities.capability_model import Capability, AccessMode
from core.security.capabilities.capability_registry import CapabilityRegistry

logger = logging.getLogger("emo_ai.isolation.capability_guard")


class CapabilityStatus:
    """Result of a capability validation check.

    Maps to design model in artifacts/design/phase4/models/03_security_resource_models.py.
    Provides structured denial reasons for failure propagation.

    Ref: DEVELOPER.md §15.15b §4.2 — ICapabilityGuard.validate()
    """
    def __init__(
        self,
        allowed: bool = False,
        capability: Optional[Capability] = None,
        reason: str = "",
        violations: Optional[List[str]] = None,
    ):
        self.allowed = allowed
        self.capability = capability
        self.reason = reason
        self.violations = violations or []


class CapabilityGuard:
    """Isolation-layer capability guard with SandboxContext validation.

    Wraps the base CapabilityGuard and enforces:
      - Capability exists for the tool (LAW 10)
      - SandboxContext permissions match or exceed capability
      - No capability → no execution (RULE 3)

    Ref: DEVELOPER.md §15.15b §4.2
    Ref: Canon RULE 3 (Capability First)
    Ref: Canon LAW 10 (Workers are unreliable — must validate before scheduling)
    """

    def __init__(
        self,
        registry: Optional[CapabilityRegistry] = None,
        base_guard: Optional[BaseCapabilityGuard] = None,
    ):
        self._base = base_guard or BaseCapabilityGuard(
            registry=registry or CapabilityRegistry(),
        )

    @property
    def registry(self) -> CapabilityRegistry:
        return self._base.registry

    def validate(
        self,
        tool_name: str,
        inputs: Dict[str, Any],
        context: Optional[SandboxContext] = None,
    ) -> CapabilityStatus:
        """Validate tool against capability registry with SandboxContext checks.

        Args:
            tool_name: Name of the tool to validate.
            inputs: Input parameters for context-aware validation.
            context: SandboxContext to validate against capability permissions.

        Returns:
            CapabilityStatus with allowed flag, capability, and violations.

        Raises:
            CapabilityViolation: From base guard on capability registry failure
                                 (also caught and wrapped in CapabilityStatus).
        """
        try:
            capability = self._base.validate(tool_name, inputs)
        except CapabilityViolation as e:
            return CapabilityStatus(
                allowed=False,
                reason=str(e),
                violations=[f"No capability registered for '{tool_name}'"],
            )

        violations: List[str] = []

        # RULE 3: Capability defines network/filesystem/subprocess permissions
        if context is not None:
            fs_violations = self._check_filesystem_compatibility(capability, context)
            violations.extend(fs_violations)

            net_violations = self._check_network_compatibility(capability, context)
            violations.extend(net_violations)

        # LAW 10: Validate bounds before scheduling
        if context is not None and context.cpu_limit > capability.max_cpu:
            violations.append(
                f"Requested CPU {context.cpu_limit}s exceeds capability max {capability.max_cpu}s"
            )

        if context is not None and context.memory_limit > capability.max_memory:
            violations.append(
                f"Requested memory {context.memory_limit} exceeds capability max {capability.max_memory}"
            )

        if violations:
            return CapabilityStatus(
                allowed=False,
                capability=capability,
                reason="; ".join(violations),
                violations=violations,
            )

        return CapabilityStatus(allowed=True, capability=capability)

    # ── Internal helpers ──

    @staticmethod
    def _check_filesystem_compatibility(
        capability: Capability,
        context: SandboxContext,
    ) -> List[str]:
        """Check filesystem mode compatibility between capability and context."""
        violations: List[str] = []
        fs_none = capability.filesystem == AccessMode.NONE
        if context.filesystem_mode == FilesystemMode.FULL and fs_none:
            violations.append("Filesystem FULL requested but capability denies filesystem access")
        if context.filesystem_mode == FilesystemMode.WRITE_TEMP and fs_none:
            violations.append("Filesystem WRITE requested but capability denies filesystem access")
        if context.filesystem_mode == FilesystemMode.READ_ONLY and fs_none:
            violations.append("Filesystem READ requested but capability denies filesystem access")
        if context.allowed_paths:
            for path in context.allowed_paths:
                if capability.allowed_paths and path not in capability.allowed_paths:
                    violations.append(f"Path '{path}' not in capability allowed_paths")
        return violations

    @staticmethod
    def _check_network_compatibility(
        capability: Capability,
        context: SandboxContext,
    ) -> List[str]:
        """Check network mode compatibility between capability and context."""
        violations: List[str] = []
        if context.network_mode == NetworkMode.FULL and not capability.network:
            violations.append("Network FULL requested but capability denies network access")
        if context.network_mode == NetworkMode.ALLOW_LIST and not capability.network:
            violations.append("Network ALLOW_LIST requested but capability denies network access")
        if context.allowed_domains:
            for domain in context.allowed_domains:
                if capability.allowed_domains and domain not in capability.allowed_domains:
                    violations.append(f"Domain '{domain}' not in capability allowed_domains")
        return violations
