"""Water Safety Policies — WHO/EPA Compliance.

Enforces WHO and EPA standards for water operations.
Default Deny for control writes: CONTROL_WRITE, PUMP_SHUTDOWN, VALVE_OVERRIDE
are blocked unless explicitly approved by a TRUSTED operator.

Ref: RC17.4.1 — Water Pack Foundation
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Union

from core.models.water import WaterActionType, WaterSafetyDecision


@dataclass(frozen=True)
class WaterPolicy:
    """Policy definition for a water action type."""

    action_type: WaterActionType
    description: str
    min_trust_level: str = "TRUSTED"
    requires_approval: bool = True
    allowed: bool = False


DEFAULT_WATER_POLICIES: Dict[WaterActionType, WaterPolicy] = {
    WaterActionType.OBSERVE: WaterPolicy(
        action_type=WaterActionType.OBSERVE,
        description="Read-only observation of water assets",
        min_trust_level="UNVERIFIED",
        requires_approval=False,
        allowed=True,
    ),
    WaterActionType.ANALYZE: WaterPolicy(
        action_type=WaterActionType.ANALYZE,
        description="Analysis of water quality and flow data",
        min_trust_level="UNVERIFIED",
        requires_approval=False,
        allowed=True,
    ),
    WaterActionType.RECOMMEND: WaterPolicy(
        action_type=WaterActionType.RECOMMEND,
        description="Recommendation for water operations",
        min_trust_level="VERIFIED",
        requires_approval=False,
        allowed=True,
    ),
    WaterActionType.CONTROL_WRITE: WaterPolicy(
        action_type=WaterActionType.CONTROL_WRITE,
        description="Control write to water infrastructure — REQUIRES approval",
        min_trust_level="TRUSTED",
        requires_approval=True,
        allowed=False,
    ),
    WaterActionType.PUMP_SHUTDOWN: WaterPolicy(
        action_type=WaterActionType.PUMP_SHUTDOWN,
        description="Pump station shutdown — REQUIRES approval",
        min_trust_level="TRUSTED",
        requires_approval=True,
        allowed=False,
    ),
    WaterActionType.VALVE_OVERRIDE: WaterPolicy(
        action_type=WaterActionType.VALVE_OVERRIDE,
        description="Valve override — REQUIRES approval",
        min_trust_level="TRUSTED",
        requires_approval=True,
        allowed=False,
    ),
}


class WaterSafetyGate:
    """WHO/EPA safety gate for water operations.

    Default Deny: any action not explicitly allowed is denied.
    Every denied action is recorded in the audit log.
    """

    def __init__(self) -> None:
        self._policies: Dict[WaterActionType, WaterPolicy] = dict(
            DEFAULT_WATER_POLICIES
        )
        self._audit_log: list[Dict[str, Any]] = []

    def set_policy(self, action_type: WaterActionType, policy: WaterPolicy) -> None:
        """Override a policy for an action type."""
        self._policies[action_type] = policy

    def evaluate(
        self,
        action_type: Union[WaterActionType, str],
        trust_level: str = "UNVERIFIED",
        context: Optional[Dict[str, Any]] = None,
    ) -> WaterSafetyDecision:
        """Evaluate an action against WHO/EPA policies.

        Default Deny: if action_type is not in policies, deny.
        """
        ctx = context or {}
        policy = self._policies.get(action_type)

        if policy is None:
            action_name = (
                action_type.value
                if isinstance(action_type, WaterActionType)
                else str(action_type)
            )
            decision = WaterSafetyDecision(
                allowed=False,
                reason=f"Default Deny: unknown action type '{action_name}'",
                action_type=action_type
                if isinstance(action_type, WaterActionType)
                else WaterActionType.OBSERVE,
                requires_approval=False,
                violation_type="unknown_action",
            )
            self._record_decision(decision, ctx)
            return decision

        # Check trust level
        trust_order = {"UNVERIFIED": 0, "VERIFIED": 1, "TRUSTED": 2}
        required = trust_order.get(policy.min_trust_level, 0)
        actual = trust_order.get(trust_level, 0)

        if actual < required:
            decision = WaterSafetyDecision(
                allowed=False,
                reason=f"Trust level insufficient: {trust_level} < {policy.min_trust_level}",
                action_type=action_type,
                requires_approval=policy.requires_approval,
                violation_type="trust_insufficient",
            )
            self._record_decision(decision, ctx)
            return decision

        # Policy-level decision
        if not policy.allowed:
            decision = WaterSafetyDecision(
                allowed=False,
                reason=f"Policy denies action: {policy.description}",
                action_type=action_type,
                requires_approval=policy.requires_approval,
                violation_type="policy_denied",
            )
            self._record_decision(decision, ctx)
            return decision

        # Action allowed
        decision = WaterSafetyDecision(
            allowed=True,
            reason=f"Action allowed: {policy.description}",
            action_type=action_type,
            requires_approval=policy.requires_approval,
        )
        self._record_decision(decision, ctx)
        return decision

    def get_policies(self) -> Dict[WaterActionType, WaterPolicy]:
        """Return all active policies."""
        return dict(self._policies)

    def get_audit_log(self) -> list[Dict[str, Any]]:
        """Return the audit log."""
        return list(self._audit_log)

    def _record_decision(
        self, decision: WaterSafetyDecision, context: Dict[str, Any]
    ) -> None:
        """Record a decision in the audit log."""
        action_name = (
            decision.action_type.value
            if isinstance(decision.action_type, WaterActionType)
            else str(decision.action_type)
        )
        entry = {
            "action_type": action_name,
            "allowed": decision.allowed,
            "reason": decision.reason,
            "requires_approval": decision.requires_approval,
            "violation_type": decision.violation_type,
            "context": context,
        }
        self._audit_log.append(entry)
