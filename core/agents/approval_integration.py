"""Agent OS — Approval Integration Layer (L0-L4 Autonomy Enforcement).

Bridges Agent OS with ApprovalGate for autonomy level enforcement.

Ref: RC16.8.4 — Agent ↔ ApprovalGate Integration
Ref: LAW 9 (Governance Independence)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Optional

from core.models.agent import AgentAudit, AutonomyLevel

if TYPE_CHECKING:
    from core.interfaces.control_plane import IApprovalManager

from core.interfaces.agents import IAgentApprovalGate


class AgentApprovalGate(IAgentApprovalGate):
    """Enforces autonomy levels (L0-L4) for agent actions."""

    # ── Autonomy Level Permissions ─────────────────────────────────────────
    LEVEL_PERMISSIONS: Dict[str, Dict[str, bool]] = {
        "L0": {"read": False, "write": False, "execute": False},  # Observe only
        "L1": {"read": True, "write": False, "execute": False},   # Recommend only
        "L2": {"read": True, "write": False, "execute": False},   # Execute with approval
        "L3": {"read": True, "write": True, "execute": True},     # Limited autonomous
        "L4": {"read": True, "write": True, "execute": True},     # Full autonomy
    }

    def __init__(
        self,
        approval_manager: Optional[IApprovalManager] = None,
        audit: Optional[AgentAudit] = None,
    ) -> None:
        self._am = approval_manager
        self._audit = audit or AgentAudit()

    def _classify_action(self, action: str) -> str:
        """Classify action as read/write/execute."""
        read_actions = ["read", "get", "list", "query", "fetch"]
        write_actions = ["create", "update", "delete", "modify"]
        execute_actions = ["execute", "run", "deploy", "terminate"]

        action_lower = action.lower()
        if any(action_lower.startswith(a) for a in read_actions):
            return "read"
        elif any(action_lower.startswith(a) for a in write_actions):
            return "write"
        elif any(action_lower.startswith(a) for a in execute_actions):
            return "execute"
        return "execute"  # Default to execute for unknown actions

    def check_autonomy(
        self,
        agent_id: str,
        action: str,
        autonomy_level: str,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Check if agent can execute action at given autonomy level."""
        # Validate autonomy level
        if autonomy_level not in self.LEVEL_PERMISSIONS:
            return {
                "allowed": False,
                "requires_approval": False,
                "reason": f"Invalid autonomy level: {autonomy_level}",
                "autonomy_level": autonomy_level,
            }

        action_type = self._classify_action(action)
        permissions = self.LEVEL_PERMISSIONS[autonomy_level]

        # L0: Block all actions (observe only)
        if autonomy_level == "L0":
            self._audit.record_action(
                action="autonomy.check",
                context={
                    "agent_id": agent_id,
                    "action": action,
                    "level": autonomy_level,
                },
                result={"decision": "DENY", "reason": "L0 observe-only mode"},
            )
            return {
                "allowed": False,
                "requires_approval": False,
                "reason": "Agent in L0 observe-only mode",
                "autonomy_level": autonomy_level,
            }

        # Check if action type is permitted at this level
        if not permissions.get(action_type, False):
            # L2: Can read/write, but not execute without approval
            if autonomy_level == "L2" and action_type in ["write", "execute"]:
                # Require approval
                if self._am is not None:
                    req = self._am.create_request(
                        tenant_id=context.get("tenant_id", "unknown"),
                        org_id=context.get("org_id"),
                        action=action,
                        requested_by=agent_id,
                        reason=f"L2 requires approval for {action_type} action",
                        metadata={**context, "autonomy_level": autonomy_level},
                    )
                    self._audit.record_action(
                        action="autonomy.request_approval",
                        context={
                            "agent_id": agent_id,
                            "action": action,
                            "level": autonomy_level,
                        },
                        result={
                            "decision": "REQUIRE_APPROVAL",
                            "request_id": req.id,
                        },
                    )
                    return {
                        "allowed": False,
                        "requires_approval": True,
                        "reason": f"L2 requires approval for {action_type} action",
                        "autonomy_level": autonomy_level,
                    }

                # No approval manager → deny
                self._audit.record_action(
                    action="autonomy.deny",
                    context={
                        "agent_id": agent_id,
                        "action": action,
                        "level": autonomy_level,
                    },
                    result={
                        "decision": "DENY",
                        "reason": "No approval manager available",
                    },
                )
                return {
                    "allowed": False,
                    "requires_approval": False,
                    "reason": "L2 requires approval but no approval manager available",
                    "autonomy_level": autonomy_level,
                }

            # Action not permitted at this level
            self._audit.record_action(
                action="autonomy.deny",
                context={
                    "agent_id": agent_id,
                    "action": action,
                    "level": autonomy_level,
                },
                result={
                    "decision": "DENY",
                    "reason": f"{action_type} not permitted at {autonomy_level}",
                },
            )
            return {
                "allowed": False,
                "requires_approval": False,
                "reason": f"{action_type.capitalize()} actions not permitted at {autonomy_level}",
                "autonomy_level": autonomy_level,
            }

        # L3/L4: Allow within bounds
        self._audit.record_action(
            action="autonomy.allow",
            context={
                "agent_id": agent_id,
                "action": action,
                "level": autonomy_level,
            },
            result={"decision": "ALLOW"},
        )
        return {
            "allowed": True,
            "requires_approval": False,
            "reason": f"Action permitted at {autonomy_level}",
            "autonomy_level": autonomy_level,
        }
