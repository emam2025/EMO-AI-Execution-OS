"""Water Maintenance Agent — Asset Maintenance Management.

Manages maintenance for water assets (pumps, valves, sensors).
Observe-only: recommends, never executes maintenance directly.

Ref: RC17.4.4 — Water Agent Integration
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
from core.models.water import (
    WaterOperationalEvent,
    WaterEventSeverity,
)

if TYPE_CHECKING:
    from core.interfaces.agents import IAgentApprovalGate
    from core.interfaces.event_bus import IEventBus
    from core.industrial.water_twin import WaterTwin


class WaterMaintenanceAgent:
    """Water maintenance management agent.

    Manages maintenance for water assets.
    All actions are observe/recommend in V1.
    """

    def __init__(
        self,
        identity: AgentIdentity,
        water_twin: Optional[WaterTwin] = None,
        event_bus: Optional[IEventBus] = None,
        approval_gate: Optional[IAgentApprovalGate] = None,
    ) -> None:
        self._identity = identity
        self._water_twin = water_twin
        self._event_bus = event_bus
        self._approval_gate = approval_gate
        self._memory = AgentMemory()
        self._skills = AgentSkills(registered_tools=["water_maintenance"])
        self._permissions = AgentPermissions(
            allowed_actions=[
                "read_maintenance_status",
                "recommend_maintenance",
                "report_maintenance_need",
            ],
            requires_approval_for=[],
        )
        self._risk = AgentRisk()
        self._cost = AgentCost()
        self._audit = AgentAudit()
        self._status = "created"
        self._maintenance_tickets: List[Dict[str, Any]] = []

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

    def recommend_maintenance(self, asset_id: str) -> Dict[str, Any]:
        """Recommend maintenance for an asset based on twin state.

        If recommendation requires a critical action (e.g., PUMP_SHUTDOWN),
        checks ApprovalGate before publishing. Publishes event via EventBus.
        """
        recommendation: Dict[str, Any]
        is_critical = False

        if self._water_twin is not None:
            twin_state = self._water_twin.get_twin_state(asset_id)
            efficiency = twin_state.state.get("efficiency_pct", 100.0)
            pump_count = twin_state.state.get("pump_count", 0)
            active_pumps = twin_state.state.get("active_pumps", 0)

            if efficiency < 80.0:
                is_critical = efficiency < 50.0
                recommendation = {
                    "asset_id": asset_id,
                    "recommendation": "schedule_maintenance",
                    "reason": f"Efficiency below threshold: {efficiency}%",
                    "priority": "high",
                    "is_critical": is_critical,
                }
            elif pump_count > 0 and active_pumps < pump_count * 0.5:
                recommendation = {
                    "asset_id": asset_id,
                    "recommendation": "check_pump_status",
                    "reason": f"Active pumps below 50%: {active_pumps}/{pump_count}",
                    "priority": "medium",
                    "is_critical": False,
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

        if is_critical and self._approval_gate is not None:
            approval_result = self._approval_gate.check_autonomy(
                agent_id=self._identity.id,
                action="PUMP_SHUTDOWN",
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
                    f"Approval gate denied PUMP_SHUTDOWN: {approval_result.get('reason', 'unauthorized')}"
                )

        if self._event_bus is not None:
            action_type = "CONTROL_WRITE" if is_critical else "RECOMMEND"
            self._publish_maintenance_event(action_type, asset_id, recommendation)

        self._audit.record_action(
            action="maintenance.recommended",
            context={"agent_id": self._identity.id, "asset_id": asset_id},
            result={"recommendation": recommendation.get("recommendation")},
        )
        return recommendation

    def get_maintenance_tickets(self, asset_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get maintenance tickets, optionally filtered by asset."""
        tickets = self._maintenance_tickets
        if asset_id is not None:
            tickets = [t for t in tickets if t.get("asset_id") == asset_id]
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
            trace_id=f"water-maintenance-{asset_id}",
            payload={
                "agent_id": self._identity.id,
                "operation": "recommend_maintenance",
                "asset_id": asset_id,
                "action_type": action_type,
                "result": result,
                "domain": "water",
            },
        )
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._event_bus.publish(EventTopic.AGENT_STATE_CHANGED, event))
        except RuntimeError:
            pass
