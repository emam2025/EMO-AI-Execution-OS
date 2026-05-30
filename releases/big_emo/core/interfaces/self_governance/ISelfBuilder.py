"""
Self-Builder Protocol — ISelfBuilder (Interface Only).

Defines the contract for proposing and sandbox-validating new tools/agents
within Guard OS boundaries. No implementation, no execution.

LAW-8:  no cross-tenant tool leakage.
LAW-20: sandbox validation mandatory before any tool is materialised.
LAW-21: risk_score must be computed before tool approval.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class ToolDraft(Protocol):
    """Read-only view of a proposed tool draft."""

    draft_id: str
    tenant_id: str
    intent: str
    tool_spec: Dict[str, Any]
    risk_score: float
    status: str


class ISelfBuilder(ABC):
    """Contract for self-building tools and agents within Guard OS.

    Every tool proposal must pass sandbox validation before it can be
    materialised. No direct access to ExecutionEngine.
    """

    @abstractmethod
    def propose_tool(
        self,
        intent: str,
        tenant_id: str,
        constraints: Optional[Dict[str, Any]] = None,
    ) -> ToolDraft:
        """Propose a new tool or agent based on intent and constraints.

        Args:
            intent:      Natural-language description of the tool/agent to build.
            tenant_id:   LAW-6 mandatory tenant scope.
            constraints: Safety, resource, or policy bounds.

        Returns:
            ToolDraft with draft_id, risk_score, and status.
        """
        ...

    @abstractmethod
    def validate_sandbox(
        self,
        draft: Dict[str, Any],
        tenant_id: str,
    ) -> bool:
        """Validate a tool draft within sandboxed environment.

        Checks: no privilege escalation, no resource overreach,
        no cross-tenant leakage, no ExecEngine access.

        Args:
            draft:      ToolDraft dict to validate.
            tenant_id:  LAW-6 mandatory tenant scope.

        Returns:
            True if the draft passes all sandbox guards.
        """
        ...
