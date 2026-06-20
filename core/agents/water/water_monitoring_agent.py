"""Water Monitoring Agent — Water Operations Monitoring.

Monitors treatment plant output, pump station status, and distribution.
Publishes events via IEventBus, queries via WaterTwin.

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


class WaterMonitoringAgent:
    """Water operations monitor.

    Monitors treatment plant output, pump station status, and distribution.
    All actions are observe-only in V1 (no control writes).
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
        self._skills = AgentSkills(registered_tools=["water_monitoring"])
        self._permissions = AgentPermissions(
            allowed_actions=[
                "read_plant_output",
                "read_pump_status",
                "read_distribution",
                "report_anomaly",
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

    def suspend(self, reason: str) -> None:
        self._status = "suspended"
        self._audit.record_action(
            action="agent.suspend",
            context={"agent_id": self._identity.id, "reason": reason},
            result={"status": "suspended"},
        )

    def run_task(
        self, task: str, context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Run a monitoring task."""
        self._audit.record_action(
            action=f"agent.{task}.executed",
            context={"agent_id": self._identity.id, "task": task},
            result={"status": "completed"},
        )
        return {"status": "completed", "task": task}

    def get_plant_output(self, asset_id: str) -> Dict[str, Any]:
        """Query treatment plant output from water twin and publish OBSERVE event."""
        result: Dict[str, Any]
        if self._water_twin is not None:
            twin_state = self._water_twin.get_twin_state(asset_id)
            result = {
                "asset_id": asset_id,
                "current_flow_mld": twin_state.state.get("current_flow_mld", 0.0),
                "capacity_mld": twin_state.state.get("capacity_mld", 0.0),
                "status": twin_state.state.get("status", "unknown"),
                "version": twin_state.version,
            }
        else:
            result = {"asset_id": asset_id, "current_flow_mld": 0.0, "status": "unknown"}

        if self._event_bus is not None:
            self._publish_observe_event("get_plant_output", asset_id, result)

        self._audit.record_action(
            action="plant_output.read",
            context={"agent_id": self._identity.id, "asset_id": asset_id},
            result={"current_flow_mld": result.get("current_flow_mld", 0.0)},
        )
        return result

    def get_pump_status(self, station_id: str) -> Dict[str, Any]:
        """Query pump station status from water twin."""
        if self._water_twin is not None:
            twin_state = self._water_twin.get_twin_state(station_id)
            return {
                "station_id": station_id,
                "active_pumps": twin_state.state.get("active_pumps", 0),
                "pump_count": twin_state.state.get("pump_count", 0),
                "status": twin_state.state.get("status", "unknown"),
            }
        return {"station_id": station_id, "active_pumps": 0, "status": "unknown"}

    def report_anomaly(
        self, asset_id: str, anomaly_type: str, details: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Report an operational anomaly."""
        event = WaterOperationalEvent(
            event_id=f"anomaly-{asset_id}",
            asset_id=asset_id,
            event_type=anomaly_type,
            severity=WaterEventSeverity.WARNING,
            message=f"Anomaly detected: {anomaly_type}",
            metadata=details,
        )
        if self._water_twin is not None:
            self._water_twin.record_event(asset_id, event)

        self._audit.record_action(
            action="anomaly.reported",
            context={"agent_id": self._identity.id, "asset_id": asset_id},
            result={"anomaly_type": anomaly_type},
        )
        return {"status": "reported", "anomaly_type": anomaly_type}

    def _publish_observe_event(
        self, operation: str, asset_id: str, result: Dict[str, Any]
    ) -> None:
        """Publish an OBSERVE event via EventBus."""
        if self._event_bus is None:
            return
        from core.models.event import EventTopic, ExecutionEvent

        event = ExecutionEvent(
            topic=EventTopic.AGENT_STATE_CHANGED,
            trace_id=f"water-monitor-{operation}-{asset_id}",
            payload={
                "agent_id": self._identity.id,
                "operation": operation,
                "asset_id": asset_id,
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
