"""Agent OS — Unified Agent Protocol.

This module defines the canonical contract for all agents in EMO AI.
Every agent (planner, coder, critic, optimizer, domain-specific) MUST
implement this protocol.

Ref: RC16.8 — Agent OS Unification
Ref: LAW 2 (Interface Authority)
Ref: LAW 9 (Governance Independence)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Protocol, runtime_checkable

if TYPE_CHECKING:
    from core.models.agent import (
        AgentAudit,
        AgentCost,
        AgentIdentity,
        AgentMemory,
        AgentPermissions,
        AgentRisk,
        AgentSkills,
    )


@runtime_checkable
class IBaseAgent(Protocol):
    """Canonical contract for all EMO AI agents.

    Every agent MUST:
    - Have a unique identity (AgentIdentity)
    - Maintain memory (AgentMemory)
    - Declare skills (AgentSkills)
    - Respect permissions (AgentPermissions)
    - Track risk level (AgentRisk)
    - Account for costs (AgentCost)
    - Produce audit trail (AgentAudit)
    """

    # ── Identity ──────────────────────────────────────────────

    @property
    def identity(self) -> AgentIdentity:
        """Unique agent identity (immutable after creation)."""
        ...

    # ── Memory ────────────────────────────────────────────────

    @property
    def memory(self) -> AgentMemory:
        """Agent's memory (short-term, long-term, episodic)."""
        ...

    # ── Skills ────────────────────────────────────────────────

    @property
    def skills(self) -> AgentSkills:
        """Registered skills and learned patterns."""
        ...

    # ── Permissions ───────────────────────────────────────────

    @property
    def permissions(self) -> AgentPermissions:
        """RBAC permissions (integrated with PolicyManager)."""
        ...

    # ── Risk ──────────────────────────────────────────────────

    @property
    def risk(self) -> AgentRisk:
        """Current risk level and autonomy mode (L0-L4)."""
        ...

    # ── Cost ──────────────────────────────────────────────────

    @property
    def cost(self) -> AgentCost:
        """Token usage, compute tracking, billing."""
        ...

    # ── Audit ─────────────────────────────────────────────────

    @property
    def audit(self) -> AgentAudit:
        """Action log, decision traces."""
        ...

    # ── Lifecycle ─────────────────────────────────────────────

    def activate(self) -> None:
        """Transition agent to ACTIVE state."""
        ...

    def suspend(self, reason: str) -> None:
        """Transition agent to SUSPENDED state."""
        ...

    def terminate(self, reason: str) -> None:
        """Transition agent to TERMINATED state (final)."""
        ...

    # ── Execution ─────────────────────────────────────────────

    def execute(
        self, task: str, context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Execute a task within the agent's capabilities.

        MUST:
        - Check permissions before execution
        - Update cost tracking
        - Record audit trail
        - Update memory with results
        - Respect risk level (may require approval)

        Returns:
            Dict with: result, status, cost, audit_id
        """
        ...

    # ── Governance Integration ────────────────────────────────

    def can_perform(self, action: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Check if agent can perform action (integrates with PolicyManager).

        Returns:
            {
                "allowed": bool,
                "requires_approval": bool,
                "reason": str,
                "policy_id": Optional[str]
            }
        """
        ...


class IAgentLifecycleManager(Protocol):
    """Manages strict agent state transitions (CREATED → ACTIVE → SUSPENDED → TERMINATED).

    MUST:
    - Verify agent exists via IResourceManager
    - Enforce valid transitions only
    - Record state changes in audit trail
    - Reject operations on TERMINATED agents
    """

    def activate(self, agent_id: str) -> Dict[str, Any]:
        """Transition agent to ACTIVE state."""
        ...

    def suspend(self, agent_id: str, reason: str) -> Dict[str, Any]:
        """Transition agent to SUSPENDED state."""
        ...

    def terminate(self, agent_id: str, reason: str) -> Dict[str, Any]:
        """Transition agent to TERMINATED state (final)."""
        ...

    def get_status(self, agent_id: str) -> Dict[str, Any]:
        """Get current agent status."""
        ...


class IAgentPolicyGate(Protocol):
    """Bridge between Agent OS and PolicyManager.

    Evaluates agent actions against active policies before execution.
    Returns decision: ALLOW, DENY, or REQUIRE_APPROVAL.

    Ref: RC16.8.3 — Agent ↔ PolicyManager Integration
    Ref: LAW 9 (Governance Independence)
    """

    def evaluate_action(
        self,
        agent_id: str,
        tenant_id: str,
        org_id: Optional[str],
        action: str,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Evaluate agent action against policies.

        Returns:
            {
                "decision": "ALLOW" | "DENY" | "REQUIRE_APPROVAL",
                "reason": str,
                "policy_id": Optional[str],
                "approval_request_id": Optional[str]
            }
        """
        ...


class IAgentApprovalGate(Protocol):
    """Bridge between Agent OS and ApprovalGate for L0-L4 autonomy enforcement.

    Checks agent's autonomy level before execution:
    - L0 (OBSERVE): Block all actions
    - L1 (RECOMMEND): Allow read-only actions, block writes
    - L2 (EXECUTE_WITH_APPROVAL): Require approval for all actions
    - L3 (LIMITED_AUTONOMOUS): Allow within policy bounds
    - L4 (DOMAIN_AUTONOMOUS): Full autonomy in domain

    Ref: RC16.8.4 — Agent ↔ ApprovalGate Integration
    Ref: LAW 9 (Governance Independence)
    """

    def check_autonomy(
        self,
        agent_id: str,
        action: str,
        autonomy_level: str,  # "L0", "L1", "L2", "L3", "L4"
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Check if agent can execute action at given autonomy level.

        Returns:
            {
                "allowed": bool,
                "requires_approval": bool,
                "reason": str,
                "autonomy_level": str
            }
        """
        ...
