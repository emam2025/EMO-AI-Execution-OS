"""SensitiveToolClassifier — Dynamic Sensitivity Classification.

Classifies tools by sensitivity level and enforces EXECUTE_SENSITIVE
capability requirement for CRITICAL tools. Any new or modified tool
must pass classification before being granted execution privileges.

Ref: Phase E.2 — Advanced Capability Security (Dynamic Sensitive Tool Classification)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Dict, List, Optional

from core.models.security import (
    Capability,
    ToolSensitivityLevel,
)

if TYPE_CHECKING:
    from core.interfaces.event_bus import IEventBus

logger = logging.getLogger(__name__)


class SensitiveToolClassifier:
    """Dynamic sensitive tool classifier.

    Maintains a registry of tool sensitivity classifications.
    Enforces that CRITICAL tools require EXECUTE_SENSITIVE capability.
    Any tool not explicitly classified defaults to LOW sensitivity.
    """

    REQUIRED_CAPS_FOR_CRITICAL: tuple = (Capability.EXECUTE_SENSITIVE,)

    def __init__(self, event_bus: Optional[IEventBus] = None) -> None:
        self._event_bus = event_bus
        self._classifications: Dict[str, ToolSensitivityLevel] = {}
        self._violations: List[Dict[str, str]] = []

    def classify(self, tool_id: str, level: ToolSensitivityLevel) -> None:
        """Register or update a tool's sensitivity classification."""
        old_level = self._classifications.get(tool_id)
        self._classifications[tool_id] = level
        logger.info(
            "Tool '%s' classified as %s (was: %s)",
            tool_id,
            level.value,
            old_level.value if old_level else "unclassified",
        )

    def get_classification(self, tool_id: str) -> ToolSensitivityLevel:
        """Get the sensitivity level for a tool. Defaults to LOW."""
        return self._classifications.get(tool_id, ToolSensitivityLevel.LOW)

    def requires_execute_sensitive(self, tool_id: str) -> bool:
        """Return True if the tool is classified as CRITICAL."""
        return self.get_classification(tool_id) == ToolSensitivityLevel.CRITICAL

    def check_critical_access(
        self, tool_id: str, requested_capabilities: List[Capability]
    ) -> bool:
        """Check if a CRITICAL tool has EXECUTE_SENSITIVE in requested capabilities.

        Returns True if:
        1. Tool is NOT CRITICAL (no special requirement).
        2. Tool IS CRITICAL and EXECUTE_SENSITIVE is in requested capabilities.

        Returns False and records violation if:
        - Tool IS CRITICAL and EXECUTE_SENSITIVE is NOT requested.
        """
        if not self.requires_execute_sensitive(tool_id):
            return True

        if Capability.EXECUTE_SENSITIVE in requested_capabilities:
            return True

        violation = {
            "tool_id": tool_id,
            "reason": (
                f"CRITICAL tool '{tool_id}' requires EXECUTE_SENSITIVE capability. "
                f"Requested: {[c.value for c in requested_capabilities]}"
            ),
            "sensitivity_level": ToolSensitivityLevel.CRITICAL.value,
        }
        self._violations.append(violation)
        logger.warning(
            "SENSITIVE_VIOLATION: tool=%s reason=%s",
            tool_id,
            violation["reason"],
        )
        self._publish_violation(violation)
        return False

    def get_violations(self) -> List[Dict[str, str]]:
        """Return all recorded violations."""
        return list(self._violations)

    def list_classified_tools(self) -> Dict[str, ToolSensitivityLevel]:
        """Return all tool classifications."""
        return dict(self._classifications)

    def _publish_violation(self, violation: Dict[str, str]) -> None:
        """Publish a SECURITY_VIOLATION event for critical access denial."""
        if self._event_bus is None:
            return

        import asyncio
        from core.models.event import EventTopic, ExecutionEvent

        event = ExecutionEvent(
            topic=EventTopic.SECURITY_VIOLATION,
            payload={
                "tool_id": violation["tool_id"],
                "requested_capability": "execute_sensitive",
                "reason": violation["reason"],
                "action_taken": "blocked",
                "sensitivity_level": violation["sensitivity_level"],
            },
            trace_id=f"classifier-{violation['tool_id']}",
        )
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(
                self._event_bus.publish(EventTopic.SECURITY_VIOLATION, event)
            )
        except RuntimeError:
            pass
