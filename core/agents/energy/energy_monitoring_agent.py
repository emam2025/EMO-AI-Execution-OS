"""Energy Monitoring Agent — Energy Operations Monitoring.

Monitors power plant output, grid load, and smart meter consumption.
Publishes events via IEventBus, queries via EnergyTwin.

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
    EnergyOperationalEvent,
    EnergyEventSeverity,
)

if TYPE_CHECKING:
    from core.interfaces.agents import IAgentApprovalGate
    from core.interfaces.event_bus import IEventBus
    from core.industrial.energy_twin import EnergyTwin


class EnergyMonitoringAgent:
    """Energy operations monitor.

    Monitors power plant output, grid load, and smart meter consumption.
    All actions are observe-only in V1 (no control writes).
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
        self._skills = AgentSkills(registered_tools=["energy_monitoring"])
        self._permissions = AgentPermissions(
            allowed_actions=[
                "read_plant_output",
                "read_grid_load",
                "read_meter_consumption",
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

    def execute(
        self, task: str, context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Execute a monitoring task."""
        self._audit.record_action(
            action=f"agent.{task}.executed",
            context={"agent_id": self._identity.id, "task": task},
            result={"status": "completed"},
        )
        return {"status": "completed", "task": task}

    def get_plant_output(self, asset_id: str) -> Dict[str, Any]:
        """Query plant output from energy twin and publish OBSERVE event."""
        result: Dict[str, Any]
        if self._energy_twin is not None:
            twin_state = self._energy_twin.get_twin_state(asset_id)
            result = {
                "asset_id": asset_id,
                "output_mw": twin_state.state.get("current_output_mw", 0.0),
                "status": twin_state.state.get("status", "unknown"),
                "version": twin_state.version,
            }
        else:
            result = {"asset_id": asset_id, "output_mw": 0.0, "status": "unknown"}

        if self._event_bus is not None:
            self._publish_observe_event("get_plant_output", asset_id, result)

        self._audit.record_action(
            action="plant_output.read",
            context={"agent_id": self._identity.id, "asset_id": asset_id},
            result={"output_mw": result.get("output_mw", 0.0)},
        )
        return result

    def get_grid_load(self, node_id: str) -> Dict[str, Any]:
        """Query grid node load from energy twin."""
        if self._energy_twin is not None:
            twin_state = self._energy_twin.get_twin_state(node_id)
            return {
                "node_id": node_id,
                "current_load_mw": twin_state.state.get("current_load_mw", 0.0),
                "max_capacity_mw": twin_state.state.get("max_capacity_mw", 0.0),
                "status": twin_state.state.get("status", "unknown"),
            }
        return {"node_id": node_id, "current_load_mw": 0.0, "status": "unknown"}

    def report_anomaly(
        self, asset_id: str, anomaly_type: str, details: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Report an operational anomaly."""
        event = EnergyOperationalEvent(
            id=f"anomaly-{asset_id}",
            asset_id=asset_id,
            event_type=anomaly_type,
            severity=EnergyEventSeverity.WARNING,
            data=details,
        )
        if self._energy_twin is not None:
            self._energy_twin.record_event(asset_id, event)

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
            trace_id=f"energy-monitor-{operation}-{asset_id}",
            payload={
                "agent_id": self._identity.id,
                "operation": operation,
                "asset_id": asset_id,
                "result": result,
                "domain": "energy",
                "action_type": "OBSERVE",
            },
        )
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._event_bus.publish(EventTopic.AGENT_STATE_CHANGED, event))
        except RuntimeError:
            pass
