"""Phase 4.3.1 — IOPolicyEngine: allow/deny rules for IO operations.

Controls which IO operations are permitted based on tool,
domain, and access mode.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger("emo_ai.io.policy")


class IOViolation(Exception):
    """Raised when an IO operation violates policy."""

    def __init__(self, operation: str, reason: str, tool: str = ""):
        self.operation = operation
        self.reason = reason
        self.tool = tool
        super().__init__(f"IO policy violation [{tool}]: {operation} — {reason}")


@dataclass
class IOPolicy:
    """Policy for a specific IO operation type."""
    allowed: bool = True
    allowed_domains: List[str] = field(default_factory=list)
    allowed_paths: List[str] = field(default_factory=list)
    max_size: int = 0
    rate_limit: float = 0.0


class IOPolicyEngine:
    """Central policy engine for IO operations.

    Evaluates whether an IO operation is permitted based on
    tool identity, operation type, and target.
    """

    def __init__(self) -> None:
        self._tool_policies: Dict[str, Dict[str, IOPolicy]] = {}
        self._default_policy = IOPolicy(allowed=False)

    def set_policy(
        self,
        tool: str,
        operation: str,
        policy: IOPolicy,
    ) -> None:
        """Set an IO policy for a specific tool + operation."""
        if tool not in self._tool_policies:
            self._tool_policies[tool] = {}
        self._tool_policies[tool][operation] = policy
        logger.debug("IO policy set for %s/%s", tool, operation)

    def check(
        self,
        tool: str,
        operation: str,
        target: str = "",
        size: int = 0,
    ) -> None:
        """Check if an IO operation is permitted.

        Raises IOViolation if not permitted.
        """
        policy = self._tool_policies.get(tool, {}).get(operation, self._default_policy)

        if not policy.allowed:
            raise IOViolation(operation, "Operation type not allowed", tool)

        if policy.allowed_domains and target:
            domain_match = any(d in target for d in policy.allowed_domains)
            if not domain_match:
                raise IOViolation(
                    operation, f"Domain {target} not in allowed list", tool,
                )

        if policy.allowed_paths and target:
            path_match = any(target.startswith(p) for p in policy.allowed_paths)
            if not path_match:
                raise IOViolation(
                    operation, f"Path {target} not in allowed list", tool,
                )

        if policy.max_size > 0 and size > policy.max_size:
            raise IOViolation(
                operation, f"Size {size} exceeds max {policy.max_size}", tool,
            )

    def allow(self, tool: str, operation: str) -> None:
        """Allow a specific operation for a tool."""
        self.set_policy(tool, operation, IOPolicy(allowed=True))

    def block(self, tool: str, operation: str) -> None:
        """Block a specific operation for a tool."""
        self.set_policy(tool, operation, IOPolicy(allowed=False))
