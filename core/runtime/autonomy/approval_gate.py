"""Approval Gate — Runtime Implementation.

Implements IApprovalGate Protocol for human-in-the-loop approval gating.
Uses Dependency Injection for IPolicyManager and IApprovalManager.

Ref: RC16.7-C.2 Human Governance Integration
"""

from typing import Optional, Dict, Any

from core.interfaces.governance import IApprovalGate
from core.interfaces.control_plane import IPolicyManager, IApprovalManager


class ApprovalGate(IApprovalGate):
    """Evaluates policies and requests human approval if needed."""

    def __init__(
        self,
        policy_manager: IPolicyManager,
        approval_manager: IApprovalManager,
    ) -> None:
        self._policy_manager = policy_manager
        self._approval_manager = approval_manager

    def check_and_request(
        self,
        tenant_id: str,
        org_id: Optional[str],
        action: str,
        requested_by: str,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Evaluate policy and request approval if needed."""
        # 1. Evaluate Policy
        evaluation = self._policy_manager.evaluate(
            tenant_id, org_id, action, context
        )

        if evaluation["allowed"]:
            return {
                "status": "APPROVED",
                "request_id": None,
                "reason": "Policy check passed",
            }

        # 2. Check if it requires human approval
        requires_approval = any(
            "requires human approval" in v.lower()
            for v in evaluation["violations"]
        )

        if requires_approval:
            # 3. Create Approval Request
            reason = (
                evaluation["violations"][0]
                if evaluation["violations"]
                else "Requires human approval"
            )
            req = self._approval_manager.create_request(
                tenant_id=tenant_id,
                org_id=org_id,
                action=action,
                requested_by=requested_by,
                reason=reason,
                metadata=context,
            )
            return {
                "status": "PENDING",
                "request_id": req.id,
                "reason": reason,
            }

        # 4. Hard rejection (e.g., resource limit exceeded)
        return {
            "status": "REJECTED",
            "request_id": None,
            "reason": (
                evaluation["violations"][0]
                if evaluation["violations"]
                else "Policy violation"
            ),
        }
