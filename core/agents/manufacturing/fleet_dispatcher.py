"""FleetDispatcherAgent — Fleet Dispatch & Route Optimization.

Manages vehicle fleet, dispatches routes, monitors delivery status.

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
from core.models.manufacturing import FleetVehicle, SupplyRoute, VehicleStatus

if TYPE_CHECKING:
    from core.interfaces.agents import IAgentApprovalGate


class FleetDispatcherAgent:
    """Fleet dispatcher — manages vehicles, dispatches routes.

    Requires approval for dispatch and route override actions.
    """

    REQUIRED_APPROVAL_ACTIONS = {"dispatch_vehicle", "override_route"}

    def __init__(
        self,
        identity: AgentIdentity,
        approval_gate: Optional[IAgentApprovalGate] = None,
    ) -> None:
        self._identity = identity
        self._approval_gate = approval_gate
        self._memory = AgentMemory()
        self._skills = AgentSkills(
            registered_tools=["fleet_dispatcher", "route_optimizer"]
        )
        self._permissions = AgentPermissions(
            allowed_actions=[
                "read_fleet_status",
                "list_routes",
                "dispatch_vehicle",
                "override_route",
                "update_vehicle_location",
            ],
            requires_approval_for=["dispatch_vehicle", "override_route"],
        )
        self._risk = AgentRisk()
        self._cost = AgentCost()
        self._audit = AgentAudit()
        self._status = "created"
        self._vehicles: Dict[str, FleetVehicle] = {}
        self._routes: Dict[str, SupplyRoute] = {}

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

    def register_vehicle(self, vehicle: FleetVehicle) -> None:
        self._vehicles[vehicle.id] = vehicle
        self._audit.record_action(
            action="vehicle.registered",
            context={"vehicle_id": vehicle.id, "vehicle_type": vehicle.type},
            result={"status": "registered"},
        )

    def register_route(self, route: SupplyRoute) -> None:
        self._routes[route.id] = route
        self._audit.record_action(
            action="route.registered",
            context={"route_id": route.id, "origin": route.origin},
            result={"status": "registered"},
        )

    def get_vehicle_status(self, vehicle_id: str) -> Optional[VehicleStatus]:
        v = self._vehicles.get(vehicle_id)
        return v.status if v else None

    def dispatch_vehicle(self, vehicle_id: str) -> Dict[str, Any]:
        v = self._vehicles.get(vehicle_id)
        if v is None:
            return {"status": "error", "reason": "vehicle_not_found"}
        return self.execute("dispatch_vehicle", {"vehicle_id": vehicle_id})

    def override_route(self, route_id: str) -> Dict[str, Any]:
        r = self._routes.get(route_id)
        if r is None:
            return {"status": "error", "reason": "route_not_found"}
        return self.execute("override_route", {"route_id": route_id})
