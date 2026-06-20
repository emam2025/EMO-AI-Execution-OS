"""Water Quality Agent — Water Quality Monitoring.

Monitors pH, turbidity, and chlorine levels from water quality sensors.
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


class WaterQualityAgent:
    """Water quality monitoring agent.

    Monitors pH, turbidity, and chlorine levels from water quality sensors.
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
        self._skills = AgentSkills(registered_tools=["water_quality"])
        self._permissions = AgentPermissions(
            allowed_actions=[
                "read_ph_level",
                "read_turbidity",
                "read_chlorine",
                "report_quality_alert",
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

    def get_quality_readings(self, sensor_id: str) -> Dict[str, Any]:
        """Query water quality readings from water twin and publish OBSERVE event."""
        result: Dict[str, Any]
        if self._water_twin is not None:
            twin_state = self._water_twin.get_twin_state(sensor_id)
            result = {
                "sensor_id": sensor_id,
                "ph_level": twin_state.state.get("ph_level", 7.0),
                "turbidity_ntu": twin_state.state.get("turbidity_ntu", 0.0),
                "chlorine_ppm": twin_state.state.get("chlorine_ppm", 0.0),
                "status": twin_state.state.get("status", "unknown"),
                "version": twin_state.version,
            }
        else:
            result = {
                "sensor_id": sensor_id,
                "ph_level": 7.0,
                "turbidity_ntu": 0.0,
                "chlorine_ppm": 0.0,
                "status": "unknown",
            }

        if self._event_bus is not None:
            self._publish_observe_event("get_quality_readings", sensor_id, result)

        self._audit.record_action(
            action="quality.readings",
            context={"agent_id": self._identity.id, "sensor_id": sensor_id},
            result={"ph_level": result.get("ph_level", 7.0)},
        )
        return result

    def check_quality_thresholds(
        self, sensor_id: str, ph_min: float = 6.5, ph_max: float = 8.5
    ) -> Dict[str, Any]:
        """Check if quality readings are within WHO/EPA thresholds."""
        readings = self.get_quality_readings(sensor_id)
        violations: List[str] = []

        ph = readings.get("ph_level", 7.0)
        if ph < ph_min or ph > ph_max:
            violations.append(f"pH out of range: {ph}")

        turbidity = readings.get("turbidity_ntu", 0.0)
        if turbidity > 4.0:
            violations.append(f"Turbidity above threshold: {turbo}")

        chlorine = readings.get("chlorine_ppm", 0.0)
        if chlorine < 0.2 or chlorine > 4.0:
            violations.append(f"Chlorine out of range: {chlorine}")

        result = {
            "sensor_id": sensor_id,
            "within_thresholds": len(violations) == 0,
            "violations": violations,
            "readings": readings,
        }

        if violations:
            self.report_quality_alert(sensor_id, violations)

        self._audit.record_action(
            action="quality.threshold_check",
            context={"agent_id": self._identity.id, "sensor_id": sensor_id},
            result={"within_thresholds": len(violations) == 0},
        )
        return result

    def report_quality_alert(
        self, sensor_id: str, violations: List[str]
    ) -> Dict[str, Any]:
        """Report a water quality alert."""
        event = WaterOperationalEvent(
            event_id=f"quality-alert-{sensor_id}",
            asset_id=sensor_id,
            event_type="quality_alert",
            severity=WaterEventSeverity.WARNING,
            message=f"Quality violations: {'; '.join(violations)}",
            metadata={"violations": violations},
        )
        if self._water_twin is not None:
            self._water_twin.record_event(sensor_id, event)

        self._audit.record_action(
            action="quality.alert.reported",
            context={"agent_id": self._identity.id, "sensor_id": sensor_id},
            result={"violation_count": len(violations)},
        )
        return {"status": "reported", "violation_count": len(violations)}

    def _publish_observe_event(
        self, operation: str, sensor_id: str, result: Dict[str, Any]
    ) -> None:
        """Publish an OBSERVE event via EventBus."""
        if self._event_bus is None:
            return
        from core.models.event import EventTopic, ExecutionEvent

        event = ExecutionEvent(
            topic=EventTopic.AGENT_STATE_CHANGED,
            trace_id=f"water-quality-{operation}-{sensor_id}",
            payload={
                "agent_id": self._identity.id,
                "operation": operation,
                "sensor_id": sensor_id,
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
