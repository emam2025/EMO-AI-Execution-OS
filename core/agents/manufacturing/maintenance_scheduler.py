"""MaintenanceSchedulerAgent — Preventive & Reactive Maintenance Scheduling.

Manages work orders, schedules maintenance, tracks asset health.

Ref: RC17.1.2 — Manufacturing Agents
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional

from core.models.agent import (
    AgentAudit,
    AgentCost,
    AgentIdentity,
    AgentMemory,
    AgentPermissions,
    AgentRisk,
    AgentSkills,
)
from core.models.manufacturing import MaintenanceWorkOrder, WorkOrderStatus

if TYPE_CHECKING:
    from core.interfaces.agents import IAgentApprovalGate


class MaintenanceSchedulerAgent:
    """Maintenance scheduler — manages work orders, schedules maintenance.

    Requires approval for critical/reactive maintenance actions.
    """

    REQUIRED_APPROVAL_ACTIONS = {"approve_work_order", "schedule_reactive_maintenance"}

    def __init__(
        self,
        identity: AgentIdentity,
        approval_gate: Optional[IAgentApprovalGate] = None,
    ) -> None:
        self._identity = identity
        self._approval_gate = approval_gate
        self._memory = AgentMemory()
        self._skills = AgentSkills(
            registered_tools=["maintenance_scheduler", "predictive_analyzer"]
        )
        self._permissions = AgentPermissions(
            allowed_actions=[
                "read_work_orders",
                "create_work_order",
                "approve_work_order",
                "schedule_reactive_maintenance",
                "update_work_order_status",
            ],
            requires_approval_for=["approve_work_order", "schedule_reactive_maintenance"],
        )
        self._risk = AgentRisk()
        self._cost = AgentCost()
        self._audit = AgentAudit()
        self._status = "created"
        self._work_orders: Dict[str, MaintenanceWorkOrder] = {}

    @property
    def identity(self) -> AgentIdentity:
        return self._identity

    @property
    def memory(self) -> AgentMemory:
        return self._memory

    @property
    def skills(self) -> AgentSkills:
        return self._skills

    @property
    def permissions(self) -> AgentPermissions:
        return self._permissions

    @property
    def risk(self) -> AgentRisk:
        return self._risk

    @property
    def cost(self) -> AgentCost:
        return self._cost

    @property
    def audit(self) -> AgentAudit:
        return self._audit

    def activate(self) -> None:
        self._status = "active"
        self._audit.record_action(
            action="agent.activate",
            context={"agent_id": self._identity.id},
            result={"status": "active"},
        )

    def suspend(self, reason: str) -> None:
        self._status = "suspended"
        self._audit.record_action(
            action="agent.suspend",
            context={"agent_id": self._identity.id, "reason": reason},
            result={"status": "suspended"},
        )

    def terminate(self, reason: str) -> None:
        self._status = "terminated"
        self._audit.record_action(
            action="agent.terminate",
            context={"agent_id": self._identity.id, "reason": reason},
            result={"status": "terminated"},
        )

    def execute(
        self, task: str, context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        ctx = context or {}
        requires_approval = task in self.REQUIRED_APPROVAL_ACTIONS

        if requires_approval and self._approval_gate is not None:
            decision = self._approval_gate.check_autonomy(
                agent_id=self._identity.id,
                action=task,
                autonomy_level="L2",
                context=ctx,
            )
            if not decision.get("allowed", False):
                self._audit.record_action(
                    action=f"agent.{task}.denied",
                    context={"agent_id": self._identity.id, "task": task},
                    result=decision,
                )
                return {"status": "denied", "reason": decision.get("reason", "")}

        self._audit.record_action(
            action=f"agent.{task}.executed",
            context={"agent_id": self._identity.id, "task": task},
            result={"status": "completed"},
        )
        return {"status": "completed", "task": task}

    def can_perform(self, action: str, context: Dict[str, Any]) -> Dict[str, Any]:
        allowed = self._permissions.can_perform(action)
        req_approval = self._permissions.requires_approval(action)
        return {
            "allowed": allowed,
            "requires_approval": req_approval,
            "reason": "Action permitted" if allowed else "Action denied",
            "policy_id": None,
        }

    def create_work_order(
        self, asset_id: str, priority: str = "medium"
    ) -> MaintenanceWorkOrder:
        order = MaintenanceWorkOrder(
            asset_id=asset_id,
            priority=priority,
            status=WorkOrderStatus.PENDING,
        )
        self._work_orders[order.id] = order
        self._audit.record_action(
            action="work_order.created",
            context={"order_id": order.id, "asset_id": asset_id},
            result={"status": "created"},
        )
        return order

    def approve_work_order(self, order_id: str) -> Dict[str, Any]:
        order = self._work_orders.get(order_id)
        if order is None:
            return {"status": "error", "reason": "order_not_found"}
        return self.execute("approve_work_order", {"order_id": order_id})

    def get_pending_orders(self) -> List[MaintenanceWorkOrder]:
        return [
            o for o in self._work_orders.values()
            if o.status == WorkOrderStatus.PENDING
        ]
