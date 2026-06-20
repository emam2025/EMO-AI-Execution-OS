"""IOPolicyEngine — File & Network Access Policy Enforcement.

Enforces Default Deny for filesystem and network access.
Maintains allowlists for paths and domains. Any request outside
the allowlist is rejected and a SECURITY_VIOLATION is published.

Ref: Phase E.1.1 — Capability Security Model & IO Policy Engine
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, List, Optional, Set

from core.models.security import SecurityViolation, ViolationAction

if TYPE_CHECKING:
    from core.interfaces.event_bus import IEventBus

logger = logging.getLogger(__name__)


class IOPolicyEngine:
    """IO policy engine — Default Deny for file and network access.

    Maintains allowlists for filesystem paths and network domains.
    Any access attempt outside the allowlists is blocked.
    """

    def __init__(
        self,
        allowed_paths: Optional[List[str]] = None,
        allowed_domains: Optional[List[str]] = None,
        event_bus: Optional[IEventBus] = None,
    ) -> None:
        self._allowed_paths: Set[str] = set(allowed_paths or [])
        self._allowed_domains: Set[str] = set(allowed_domains or [])
        self._event_bus = event_bus
        self._violations: List[SecurityViolation] = []

    def check_file_access(
        self, tool_id: str, path: str, mode: str
    ) -> bool:
        """Check if a tool is allowed to access a file path.

        Default Deny: path must be in the allowlist.
        """
        for allowed in self._allowed_paths:
            if path.startswith(allowed):
                return True

        self._publish_violation(
            tool_id=tool_id,
            requested_capability="filesystem_" + mode,
            reason=(
                f"File access denied: tool='{tool_id}' path='{path}' mode='{mode}'. "
                f"Path not in allowlist."
            ),
        )
        return False

    def check_network_access(self, tool_id: str, url: str) -> bool:
        """Check if a tool is allowed to access a network URL.

        Default Deny: domain must be in the allowlist.
        """
        for domain in self._allowed_domains:
            if domain in url:
                return True

        self._publish_violation(
            tool_id=tool_id,
            requested_capability="network_outbound",
            reason=(
                f"Network access denied: tool='{tool_id}' url='{url}'. "
                f"Domain not in allowlist."
            ),
        )
        return False

    def add_allowed_path(self, path: str) -> None:
        self._allowed_paths.add(path)

    def add_allowed_domain(self, domain: str) -> None:
        self._allowed_domains.add(domain)

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
