"""Energy Maintenance Agent — Asset Maintenance Management.

Manages maintenance tickets for energy assets.
Observe-only: recommends, never executes maintenance directly.

Ref: RC17.3 — Energy Pack Foundation
"""

from __future__ import annotations

import asyncio
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
from core.models.energy import (
    MaintenancePriority,
    MaintenanceStatus,
    MaintenanceTicket,
)

if TYPE_CHECKING:
    from core.interfaces.agents import IAgentApprovalGate
    from core.interfaces.event_bus import IEventBus
    from core.industrial.energy_twin import EnergyTwin


class EnergyMaintenanceAgent:
    """Energy maintenance management agent.

    Manages maintenance tickets for energy assets.
    All actions are observe/recommend in V1.
    """

    def __init__(
        self,
        identity: AgentIdentity,
        energy_twin: Optional[EnergyTwin] = None,
        event_bus: Optional[IEventBus] = None,
        approval_gate: Optional[IAgentApprovalGate] = None,
    ) -> None:
        self._identity = identity
        self._energy_twin = energy_twin
        self._event_bus = event_bus
        self._approval_gate = approval_gate
        self._memory = AgentMemory()
        self._skills = AgentSkills(registered_tools=["energy_maintenance"])
        self._permissions = AgentPermissions(
            allowed_actions=[
                "read_maintenance_tickets",
                "create_maintenance_ticket",
                "recommend_maintenance",
                "update_ticket_status",
            ],
            requires_approval_for=["update_ticket_status"],
        )
        self._risk = AgentRisk()
        self._cost = AgentCost()
        self._audit = AgentAudit()
        self._status = "created"
        self._tickets: Dict[str, MaintenanceTicket] = {}

    @property
    def identity(self) -> AgentIdentity:
        return self._identity

    @property
    def memory(self) -> AgentMemory:
        return self._memory

    @property
    def permissions(self) -> AgentPermissions:
        return self._permissions

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

    def create_ticket(
        self,
        asset_id: str,
        title: str,
        description: str,
        priority: MaintenancePriority = MaintenancePriority.MEDIUM,
    ) -> MaintenanceTicket:
        """Create a maintenance ticket."""
        ticket = MaintenanceTicket(
            id=f"ticket-{len(self._tickets) + 1}",
            asset_id=asset_id,
            title=title,
            description=description,
            priority=priority,
        )
        self._tickets[ticket.id] = ticket
        self._audit.record_action(
            action="ticket.created",
            context={"agent_id": self._identity.id, "asset_id": asset_id},
            result={"ticket_id": ticket.id},
        )
        return ticket

    def get_ticket(self, ticket_id: str) -> Optional[MaintenanceTicket]:
        """Get a maintenance ticket."""
        return self._tickets.get(ticket_id)

    def list_tickets(
        self, asset_id: Optional[str] = None
    ) -> List[MaintenanceTicket]:
        """List maintenance tickets, optionally filtered by asset."""
        tickets = list(self._tickets.values())
        if asset_id is not None:
            tickets = [t for t in tickets if t.asset_id == asset_id]
        return tickets

    def _publish_maintenance_event(
        self, action_type: str, asset_id: str, result: Dict[str, Any]
    ) -> None:
        """Publish a maintenance event via EventBus."""
        if self._event_bus is None:
            return
        from core.models.event import EventTopic, ExecutionEvent

        event = ExecutionEvent(
            topic=EventTopic.AGENT_STATE_CHANGED,
            trace_id=f"energy-maintenance-{asset_id}",
            payload={
                "agent_id": self._identity.id,
                "operation": "recommend_maintenance",
                "asset_id": asset_id,
                "action_type": action_type,
                "result": result,
                "domain": "energy",
            },
        )
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._event_bus.publish(EventTopic.AGENT_STATE_CHANGED, event))
        except RuntimeError:
            pass

    def recommend_maintenance(self, asset_id: str) -> Dict[str, Any]:
        """Recommend maintenance for an asset based on twin state.

        If recommendation requires a critical action (e.g., PLANT_STOP),
        checks ApprovalGate before publishing. Publishes event via EventBus.
        """
        recommendation: Dict[str, Any]
        is_critical = False

        if self._energy_twin is not None:
            twin_state = self._energy_twin.get_twin_state(asset_id)
            efficiency = twin_state.state.get("efficiency_pct", 100.0)
            if efficiency < 80.0:
                is_critical = efficiency < 50.0
                recommendation = {
                    "asset_id": asset_id,
                    "recommendation": "schedule_maintenance",
                    "reason": f"Efficiency below threshold: {efficiency}%",
                    "priority": "high",
                    "is_critical": is_critical,
                }
            else:
                recommendation = {
                    "asset_id": asset_id,
                    "recommendation": "no_action_needed",
                    "reason": "Asset operating within normal parameters",
                    "is_critical": False,
                }
        else:
            recommendation = {
                "asset_id": asset_id,
                "recommendation": "no_action_needed",
                "reason": "No twin state available",
                "is_critical": False,
            }

        # Check approval gate for critical actions
        if is_critical and self._approval_gate is not None:
            approval_result = self._approval_gate.check_autonomy(
                agent_id=self._identity.id,
                action="PLANT_STOP",
                autonomy_level="L2",
                context={"asset_id": asset_id, "efficiency": efficiency},
            )
            recommendation["approval_required"] = approval_result.get(
                "requires_approval", False
            )
            recommendation["approval_allowed"] = approval_result.get("allowed", False)
            if not approval_result.get("allowed", False):
                recommendation["recommendation"] = "critical_action_blocked"
                recommendation["reason"] = (
                    f"Approval gate denied PLANT_STOP: {approval_result.get('reason', 'unauthorized')}"
                )

        # Publish event
        if self._event_bus is not None:
            action_type = "CONTROL_WRITE" if is_critical else "RECOMMEND"
            self._publish_maintenance_event(action_type, asset_id, recommendation)

        self._audit.record_action(
            action="maintenance.recommended",
            context={"agent_id": self._identity.id, "asset_id": asset_id},
            result={"recommendation": recommendation.get("recommendation")},
        )
        return recommendation
