"""CapabilityGuard — Pre-execution Capability Validation.

Enforces Default Deny: no capability registered → no execution.
Publishes SECURITY_VIOLATION events via IEventBus on policy failure.
Integrates with SensitiveToolClassifier for CRITICAL tool enforcement.

Ref: Phase E.1.1 — Capability Security Model & IO Policy Engine
Ref: Phase E.2 — Advanced Capability Security (Dynamic Sensitive Tool Classification)
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Dict, List, Optional

from core.models.security import (
    Capability,
    CapabilityManifest,
    SecurityViolation,
    ViolationAction,
)

if TYPE_CHECKING:
    from core.interfaces.event_bus import IEventBus
    from core.security.sensitive_tool_classifier import SensitiveToolClassifier

logger = logging.getLogger(__name__)


class CapabilityGuard:
    """Capability-based access guard — Default Deny enforcement.

    Maintains a registry of tool manifests. Each check compares
    requested capabilities against the registered manifest.
    Unregistered tools are always rejected.

    When a SensitiveToolClassifier is attached, CRITICAL tools
    automatically require EXECUTE_SENSITIVE capability.
    """

    def __init__(
        self,
        event_bus: Optional[IEventBus] = None,
        classifier: Optional[SensitiveToolClassifier] = None,
    ) -> None:
        self._event_bus = event_bus
        self._classifier = classifier
        self._manifests: Dict[str, CapabilityManifest] = {}
        self._violations: List[SecurityViolation] = []

    def set_classifier(self, classifier: SensitiveToolClassifier) -> None:
        """Attach a sensitive tool classifier for dynamic enforcement."""
        self._classifier = classifier

    def register_manifest(
        self, tool_id: str, manifest: CapabilityManifest
    ) -> None:
        """Register a capability manifest for a tool."""
        self._manifests[tool_id] = manifest

    def check(
        self, tool_id: str, requested_capabilities: List[Capability]
    ) -> bool:
        """Check if a tool has all requested capabilities.

        Returns True only if:
        1. The tool is registered with a manifest.
        2. All requested capabilities are in the allowed set.
        3. If CRITICAL, EXECUTE_SENSITIVE is in requested capabilities.

        Publishes SECURITY_VIOLATION on failure.
        """
        manifest = self._manifests.get(tool_id)
        if manifest is None:
            self._publish_violation(
                tool_id=tool_id,
                requested_capability="any",
                reason=f"Tool '{tool_id}' is not registered — Default Deny",
            )
            return False

        for cap in requested_capabilities:
            if cap not in manifest.allowed_capabilities:
                self._publish_violation(
                    tool_id=tool_id,
                    requested_capability=cap.value,
                    reason=(
                        f"Capability '{cap.value}' not in manifest for tool '{tool_id}'. "
                        f"Allowed: {[c.value for c in manifest.allowed_capabilities]}"
                    ),
                )
                return False

        if self._classifier is not None:
            if not self._classifier.check_critical_access(
                tool_id, requested_capabilities
            ):
                return False

        return True

    def get_manifest(self, tool_id: str) -> Optional[CapabilityManifest]:
        return self._manifests.get(tool_id)

    def get_violations(self) -> List[SecurityViolation]:
        return list(self._violations)

    def _publish_violation(
        self,
        tool_id: str,
        requested_capability: str,
        reason: str,
    ) -> None:
        """Record and publish a security violation."""
        violation = SecurityViolation(
            tool_id=tool_id,
            requested_capability=requested_capability,
            reason=reason,
            action_taken=ViolationAction.BLOCKED,
        )
        self._violations.append(violation)
        logger.warning(
            "SECURITY_VIOLATION: tool=%s cap=%s reason=%s",
            tool_id,
            requested_capability,
            reason,
        )

        if self._event_bus is not None:
            try:
                from core.models.event import EventTopic, ExecutionEvent

                event = ExecutionEvent(
                    topic=EventTopic.SECURITY_VIOLATION,
                    payload={
                        "violation_id": violation.violation_id,
                        "tool_id": tool_id,
                        "requested_capability": requested_capability,
                        "reason": reason,
                        "action_taken": violation.action_taken.value,
                    },
                    trace_id=violation.violation_id,
                )
                loop = asyncio.get_running_loop()
                loop.create_task(
                    self._event_bus.publish(EventTopic.SECURITY_VIOLATION, event)
                )
            except RuntimeError:
                pass
