"""Policy Manager — Control Plane Implementation.

Implements IPolicyManager Protocol for policy lifecycle management.
In-memory storage only — no database in this phase.

Ref: RC16.7-B.4 PolicyManager
"""

from typing import Dict, List, Optional, Any
import uuid
from datetime import datetime, timezone

from core.interfaces.control_plane import (
    IPolicyManager,
    Policy,
    PolicyType,
    PolicyStatus,
)


class PolicyManager(IPolicyManager):
    """Manages policies and evaluates rules."""

    def __init__(self) -> None:
        self._policies: Dict[str, Policy] = {}

    def create_policy(
        self,
        tenant_id: str,
        name: str,
        policy_type: PolicyType,
        rules: Dict[str, Any],
        org_id: Optional[str] = None,
    ) -> Policy:
        """Create a new policy."""
        policy = Policy(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            org_id=org_id,
            name=name,
            policy_type=policy_type,
            rules=rules,
            status=PolicyStatus.ACTIVE,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._policies[policy.id] = policy
        return policy

    def get_policy(self, policy_id: str) -> Optional[Policy]:
        """Retrieve a policy by ID."""
        return self._policies.get(policy_id)

    def list_policies(
        self,
        tenant_id: str,
        org_id: Optional[str] = None,
        policy_type: Optional[PolicyType] = None,
    ) -> List[Policy]:
        """List policies with optional filters."""
        policies = [
            p for p in self._policies.values() if p.tenant_id == tenant_id
        ]
        if org_id is not None:
            policies = [
                p for p in policies if p.org_id == org_id or p.org_id is None
            ]
        if policy_type is not None:
            policies = [p for p in policies if p.policy_type == policy_type]
        return [p for p in policies if p.status == PolicyStatus.ACTIVE]

    def update_policy_status(self, policy_id: str, status: PolicyStatus) -> bool:
        """Update policy status. Returns True if successful."""
        if policy_id in self._policies:
            self._policies[policy_id].status = status
            return True
        return False

    def delete_policy(self, policy_id: str) -> bool:
        """Delete a policy. Returns True if successful."""
        if policy_id in self._policies:
            del self._policies[policy_id]
            return True
        return False

    def evaluate(
        self,
        tenant_id: str,
        org_id: Optional[str],
        action: str,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Evaluate all active policies against an action.

        Returns:
            {"allowed": bool, "violations": list[str]}
        """
        policies = self.list_policies(tenant_id, org_id)
        violations: List[str] = []

        for policy in policies:
            if policy.policy_type == PolicyType.RESOURCE_LIMIT:
                limit = policy.rules.get("max_count")
                current = context.get("current_count", 0)
                if limit is not None and current >= limit:
                    violations.append(
                        f"Policy '{policy.name}' violated: max_count ({limit}) reached."
                    )

            elif policy.policy_type == PolicyType.APPROVAL_REQUIRED:
                if action in policy.rules.get("require_approval_for", []):
                    violations.append(
                        f"Policy '{policy.name}' requires human approval for action '{action}'."
                    )

        return {
            "allowed": len(violations) == 0,
            "violations": violations,
            "evaluated_policies_count": len(policies),
        }
