"""Water Distribution Agent — Water Distribution Management.

Manages water distribution network operations.
Observe-only: recommends, never executes control writes directly.

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


class WaterDistributionAgent:
    """Water distribution management agent.

    Manages water distribution network operations.
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
        self._skills = AgentSkills(registered_tools=["water_distribution"])
        self._permissions = AgentPermissions(
            allowed_actions=[
                "read_network_status",
                "read_pressure",
                "recommend_flow_adjustment",
                "report_distribution_issue",
            ],
            requires_approval_for=[],
        )
        self._risk = AgentRisk()
        self._cost = AgentCost()
        self._audit = AgentAudit()
        self._status = "created"

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

    def get_network_status(self, zone_id: str) -> Dict[str, Any]:
        """Query distribution network status from water twin."""
        result: Dict[str, Any]
        if self._water_twin is not None:
            twin_state = self._water_twin.get_twin_state(zone_id)
            result = {
                "zone_id": zone_id,
                "pressure_psi": twin_state.state.get("pressure_psi", 0.0),
                "flow_rate": twin_state.state.get("flow_rate", 0.0),
                "status": twin_state.state.get("status", "unknown"),
                "version": twin_state.version,
            }
        else:
            result = {"zone_id": zone_id, "pressure_psi": 0.0, "flow_rate": 0.0, "status": "unknown"}

        if self._event_bus is not None:
            self._publish_observe_event("get_network_status", zone_id, result)

        self._audit.record_action(
            action="network.status.read",
            context={"agent_id": self._identity.id, "zone_id": zone_id},
            result={"pressure_psi": result.get("pressure_psi", 0.0)},
        )
        return result

    def recommend_flow_adjustment(
        self, zone_id: str, target_flow: float
    ) -> Dict[str, Any]:
        """Recommend flow adjustment for a distribution zone.

        Publishes RECOMMEND event via EventBus.
        """
        recommendation: Dict[str, Any]

        if self._water_twin is not None:
            twin_state = self._water_twin.get_twin_state(zone_id)
            current_flow = twin_state.state.get("flow_rate", 0.0)
            delta = target_flow - current_flow

            recommendation = {
                "zone_id": zone_id,
                "recommendation": "adjust_flow",
                "current_flow": current_flow,
                "target_flow": target_flow,
                "delta": delta,
                "priority": "high" if abs(delta) >= 50 else "medium",
                "is_critical": False,
            }
        else:
            recommendation = {
                "zone_id": zone_id,
                "recommendation": "no_action_needed",
                "reason": "No twin state available",
                "is_critical": False,
            }

        if self._event_bus is not None:
            self._publish_observe_event("recommend_flow_adjustment", zone_id, recommendation)

        self._audit.record_action(
            action="flow.recommendation",
            context={"agent_id": self._identity.id, "zone_id": zone_id},
            result={"recommendation": recommendation.get("recommendation")},
        )
        return recommendation

    def report_distribution_issue(
        self, zone_id: str, issue_type: str, details: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Report a distribution issue."""
        event = WaterOperationalEvent(
            event_id=f"dist-issue-{zone_id}",
            asset_id=zone_id,
            event_type=issue_type,
            severity=WaterEventSeverity.WARNING,
            message=f"Distribution issue: {issue_type}",
            metadata=details,
        )
        if self._water_twin is not None:
            self._water_twin.record_event(zone_id, event)

        self._audit.record_action(
            action="distribution.issue.reported",
            context={"agent_id": self._identity.id, "zone_id": zone_id},
            result={"issue_type": issue_type},
        )
        return {"status": "reported", "issue_type": issue_type}

    def _publish_observe_event(
        self, operation: str, zone_id: str, result: Dict[str, Any]
    ) -> None:
        """Publish an OBSERVE event via EventBus."""
        if self._event_bus is None:
            return
        from core.models.event import EventTopic, ExecutionEvent

        event = ExecutionEvent(
            topic=EventTopic.AGENT_STATE_CHANGED,
            trace_id=f"water-distribution-{operation}-{zone_id}",
            payload={
                "agent_id": self._identity.id,
                "operation": operation,
                "zone_id": zone_id,
                "result": result,
                "domain": "water",
                "action_type": "OBSERVE",
            },
        )
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._event_bus.publish(EventTopic.AGENT_STATE_CHANGED, event))
        except RuntimeError:
            pass
