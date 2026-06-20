"""Energy Safety Gate — NERC-CIP Enforcement.

Enforces NERC-CIP policies for energy operations.
Default Deny: any control write is blocked unless explicitly approved.
Publishes SAFETY_VIOLATION events on every denial.

Ref: RC17.3.2 — Energy Safety Policies
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Dict, Optional, Union

from core.models.energy_policy import (
    DEFAULT_NERC_CIP_POLICIES,
    EnergyActionType,
    EnergyRiskLevel,
    EnergySafetyDecision,
    NERCCIPPolicy,
)

if TYPE_CHECKING:
    from core.interfaces.event_bus import IEventBus


class EnergySafetyGate:
    """NERC-CIP safety gate for energy operations.

    Default Deny: any action not explicitly allowed is denied.
    Every denial publishes a SAFETY_VIOLATION event.
    """

    def __init__(self, event_bus: Optional[IEventBus] = None) -> None:
        self._event_bus = event_bus
        self._policies: Dict[EnergyActionType, NERCCIPPolicy] = dict(
            DEFAULT_NERC_CIP_POLICIES
        )
        self._audit_log: list[Dict[str, Any]] = []

    def set_policy(self, action_type: EnergyActionType, policy: NERCCIPPolicy) -> None:
        """Override a policy for an action type."""
        self._policies[action_type] = policy

    def evaluate(
        self,
        action_type: Union[EnergyActionType, str],
        trust_level: str = "UNVERIFIED",
        context: Optional[Dict[str, Any]] = None,
    ) -> EnergySafetyDecision:
        """Evaluate an action against NERC-CIP policies.

        Default Deny: if action_type is not in policies, deny.
        """
        ctx = context or {}
        policy = self._policies.get(action_type)

        if policy is None:
            action_name = action_type.value if isinstance(action_type, EnergyActionType) else str(action_type)
            decision = EnergySafetyDecision(
                allowed=False,
                reason=f"Default Deny: unknown action type '{action_name}'",
                action_type=action_type,
                requires_approval=False,
                violation_type="unknown_action",
            )
            self._record_decision(decision, ctx)
            self._publish_violation(decision, ctx)
            return decision

        # Check trust level
        trust_order = {"UNVERIFIED": 0, "VERIFIED": 1, "TRUSTED": 2}
        required = trust_order.get(policy.min_trust_level, 0)
        actual = trust_order.get(trust_level, 0)

        if actual < required:
            decision = EnergySafetyDecision(
                allowed=False,
                reason=f"Trust level insufficient: {trust_level} < {policy.min_trust_level}",
                action_type=action_type,
                requires_approval=policy.requires_approval,
                violation_type="trust_insufficient",
            )
            self._record_decision(decision, ctx)
            self._publish_violation(decision, ctx)
            return decision

        # Action allowed (may still require approval)
        decision = EnergySafetyDecision(
            allowed=True,
            reason=f"Action allowed: {policy.description}",
            action_type=action_type,
            requires_approval=policy.requires_approval,
        )
        self._record_decision(decision, ctx)
        return decision

    def is_control_write(self, action_type: EnergyActionType) -> bool:
        """Check if an action type is a control write (always requires approval)."""
        return action_type in {
            EnergyActionType.CONTROL_WRITE,
            EnergyActionType.GRID_SHUTDOWN,
            EnergyActionType.LOAD_SHEDDING,
            EnergyActionType.PLANT_START,
            EnergyActionType.PLANT_STOP,
        }

    def get_policies(self) -> Dict[EnergyActionType, NERCCIPPolicy]:
        """Return all active policies."""
        return dict(self._policies)

    def get_audit_log(self) -> list[Dict[str, Any]]:
        """Return the audit log."""
        return list(self._audit_log)

    def _record_decision(
        self, decision: EnergySafetyDecision, context: Dict[str, Any]
    ) -> None:
        """Record a decision in the audit log."""
        action_name = decision.action_type.value if isinstance(decision.action_type, EnergyActionType) else str(decision.action_type)
        entry = {
            "action_type": action_name,
            "allowed": decision.allowed,
            "reason": decision.reason,
            "requires_approval": decision.requires_approval,
            "violation_type": decision.violation_type,
            "context": context,
        }
        self._audit_log.append(entry)

    def _publish_violation(
        self, decision: EnergySafetyDecision, context: Dict[str, Any]
    ) -> None:
        """Publish a SAFETY_VIOLATION event if event_bus is available."""
        if self._event_bus is None:
            return
        from core.models.event import EventTopic, ExecutionEvent

        event = ExecutionEvent(
            topic=EventTopic.SAFETY_VIOLATION,
            trace_id=f"energy-safety-{decision.action_type.value}",
            payload={
                "action_type": decision.action_type.value,
                "allowed": decision.allowed,
                "reason": decision.reason,
                "violation_type": decision.violation_type,
                "context": context,
                "domain": "energy",
            },
        )
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(
                self._event_bus.publish(EventTopic.SAFETY_VIOLATION, event)
            )
        except RuntimeError:
            pass
