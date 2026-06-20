"""WarehouseOptimizerAgent — Warehouse Inventory Optimization.

Monitors inventory levels, triggers reorders, optimizes storage.

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
from core.models.manufacturing import Warehouse

if TYPE_CHECKING:
    from core.interfaces.agents import IAgentApprovalGate


class WarehouseOptimizerAgent:
    """Warehouse optimizer — monitors inventory, triggers reorders.

    Requires approval for reorder actions.
    """

    REQUIRED_APPROVAL_ACTIONS = {"reorder_stock", "liquidate_excess"}

    def __init__(
        self,
        identity: AgentIdentity,
        approval_gate: Optional[IAgentApprovalGate] = None,
    ) -> None:
        self._identity = identity
        self._approval_gate = approval_gate
        self._memory = AgentMemory()
        self._skills = AgentSkills(
            registered_tools=["warehouse_optimizer", "inventory_tracker"]
        )
        self._permissions = AgentPermissions(
            allowed_actions=[
                "read_inventory",
                "list_warehouses",
                "reorder_stock",
                "liquidate_excess",
                "adjust_reorder_point",
            ],
            requires_approval_for=["reorder_stock", "liquidate_excess"],
        )
        self._risk = AgentRisk()
        self._cost = AgentCost()
        self._audit = AgentAudit()
        self._status = "created"
        self._warehouses: Dict[str, Warehouse] = {}

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

    def register_warehouse(self, warehouse: Warehouse) -> None:
        self._warehouses[warehouse.id] = warehouse
        self._audit.record_action(
            action="warehouse.registered",
            context={"warehouse_id": warehouse.id, "warehouse_name": warehouse.name},
            result={"status": "registered"},
        )

    def get_inventory_level(self, warehouse_id: str) -> Optional[float]:
        wh = self._warehouses.get(warehouse_id)
        return wh.current_inventory_level if wh else None

    def reorder_stock(self, warehouse_id: str) -> Dict[str, Any]:
        wh = self._warehouses.get(warehouse_id)
        if wh is None:
            return {"status": "error", "reason": "warehouse_not_found"}
        return self.execute("reorder_stock", {"warehouse_id": warehouse_id})
