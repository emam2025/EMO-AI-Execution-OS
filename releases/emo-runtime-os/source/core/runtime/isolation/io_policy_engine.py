"""Phase 4.3 — Isolation IOPolicyEngine.

IO allow/deny policy engine for the isolation layer. All IO MUST
pass through this engine. Controls network, filesystem, and
operation-level policies per tool.

Ref: DEVELOPER.md §15.15b §4.3
Ref: Canon RULE 2 (No uncontrolled IO)
"""

from __future__ import annotations

import logging
from typing import Optional

from core.runtime.io.io_policy_engine import (
    IOPolicyEngine as BaseIOPolicyEngine,
    IOPolicy,
    IOViolation,
)

logger = logging.getLogger("emo_ai.isolation.io_policy")


class IOPolicyEngine:
    """Isolation-layer IO policy engine.

    Wraps the base IOPolicyEngine with isolation-specific:
      - Canon compliance logging
      - Explicit RULE 2 enforcement traceability

    Ref: DEVELOPER.md §15.15b §4.3
    Ref: Canon RULE 2 (No uncontrolled IO)
    """

    def __init__(self, base_engine: Optional[BaseIOPolicyEngine] = None):
        self._base = base_engine or BaseIOPolicyEngine()

    def check(
        self,
        tool: str,
        operation: str,
        target: str = "",
        size: int = 0,
    ) -> None:
        """Check if an IO operation is permitted.

        RULE 2: No IO operation may bypass policy check.
        Raises IOViolation if not permitted.

        Args:
            tool: Tool name requesting the operation.
            operation: Operation type (e.g. "network.get", "file.read").
            target: URL, domain, or filesystem path.
            size: Payload size in bytes.

        Raises:
            IOViolation: If operation is not permitted.
        """
        self._base.check(tool, operation, target, size)

    def allow(self, tool: str, operation: str) -> None:
        """Allow a specific operation for a tool."""
        self._base.allow(tool, operation)
        logger.debug("IO allowed: %s/%s", tool, operation)

    def block(self, tool: str, operation: str) -> None:
        """Block a specific operation for a tool."""
        self._base.block(tool, operation)
        logger.debug("IO blocked: %s/%s", tool, operation)
