"""Agent OS — Policy Integration Layer.

Bridges Agent OS with PolicyManager for governance enforcement.

Ref: RC16.8.3 — Agent ↔ PolicyManager Integration
Ref: LAW 9 (Governance Independence)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Optional

from core.models.agent import AgentAudit

if TYPE_CHECKING:
    from core.interfaces.control_plane import IApprovalManager, IPolicyManager

from core.interfaces.agents import IAgentPolicyGate


class AgentPolicyGate(IAgentPolicyGate):
    """Evaluates agent actions against active policies."""

    def __init__(
        self,
        policy_manager: IPolicyManager,
        approval_manager: Optional[IApprovalManager] = None,
        audit: Optional[AgentAudit] = None,
    ) -> None:
        self._pm = policy_manager
        self._am = approval_manager
        self._audit = audit or AgentAudit()

    def evaluate_action(
        self,
        agent_id: str,
        tenant_id: str,
        org_id: Optional[str],
        action: str,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Evaluate agent action against policies.

        Decision flow:
        1. Call PolicyManager.evaluate()
        2. If allowed → return ALLOW
        3. If requires approval → create ApprovalRequest, return REQUIRE_APPROVAL
        4. If hard violation → return DENY
        """
        # Step 1: Evaluate policy
        evaluation = self._pm.evaluate(tenant_id, org_id, action, context)

        # Step 2: Check result
        if evaluation["allowed"]:
            self._audit.record_action(
                action="policy.evaluate",
                context={"agent_id": agent_id, "action": action},
                result={"decision": "ALLOW"},
            )
            return {
                "decision": "ALLOW",
                "reason": "No policy violations",
                "policy_id": None,
                "approval_request_id": None,
            }

        # Step 3: Check if requires approval
        requires_approval = any(
            "requires human approval" in v.lower()
            for v in evaluation["violations"]
        )

        if requires_approval and self._am is not None:
            # Create approval request
            reason = (
                evaluation["violations"][0]
                if evaluation["violations"]
                else "Policy requires approval"
            )
            req = self._am.create_request(
                tenant_id=tenant_id,
                org_id=org_id,
                action=action,
                requested_by=agent_id,
                reason=reason,
                metadata={**context, "agent_id": agent_id},
            )

            self._audit.record_action(
                action="policy.request_approval",
                context={"agent_id": agent_id, "action": action},
                result={"decision": "REQUIRE_APPROVAL", "request_id": req.id},
            )

            return {
                "decision": "REQUIRE_APPROVAL",
                "reason": reason,
                "policy_id": None,
                "approval_request_id": req.id,
            }

        # Step 4: Hard denial
        reason = (
            evaluation["violations"][0]
            if evaluation["violations"]
            else "Policy violation"
        )
        self._audit.record_action(
            action="policy.deny",
            context={"agent_id": agent_id, "action": action},
            result={"decision": "DENY", "reason": reason},
        )

        return {
            "decision": "DENY",
            "reason": reason,
            "policy_id": None,
            "approval_request_id": None,
        }
