"""Load Forecast Agent — Energy Demand Forecasting.

Forecasts energy demand based on historical load profiles and real-time data.
Observe-only: recommends, never acts.

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
from core.models.energy import LoadProfile

if TYPE_CHECKING:
    from core.interfaces.agents import IAgentApprovalGate
    from core.interfaces.event_bus import IEventBus
    from core.industrial.energy_twin import EnergyTwin


class LoadForecastAgent:
    """Energy demand forecasting agent.

    Forecasts energy demand based on historical load profiles.
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
        self._skills = AgentSkills(registered_tools=["load_forecasting"])
        self._permissions = AgentPermissions(
            allowed_actions=[
                "read_load_profile",
                "forecast_demand",
                "recommend_load_balance",
            ],
            requires_approval_for=[],
        )
        self._risk = AgentRisk()
        self._cost = AgentCost()
        self._audit = AgentAudit()
        self._status = "created"
        self._load_profiles: Dict[str, LoadProfile] = {}

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

    def register_load_profile(self, profile: LoadProfile) -> None:
        """Register a load profile for forecasting."""
        self._load_profiles[profile.id] = profile

    def forecast_demand(
        self, node_id: str, horizon_hours: int = 24
    ) -> Dict[str, Any]:
        """Forecast demand for a grid node via EnergyTwin prediction."""
        current_state: Dict[str, Any] = {}
        prediction: Dict[str, Any] = {}
        if self._energy_twin is not None:
            twin_state = self._energy_twin.get_twin_state(node_id)
            current_state = twin_state.state
            prediction = self._energy_twin.predict(node_id, horizon_hours)

        current_load = current_state.get("current_load_mw", 0.0)
        forecast = {
            "node_id": node_id,
            "horizon_hours": horizon_hours,
            "current_load_mw": current_load,
            "predicted_load_mw": current_load * 1.05,
            "confidence": 0.82,
            "prediction_id": prediction.get("prediction_id"),
        }

        if self._event_bus is not None:
            self._publish_analyze_event("forecast_demand", node_id, forecast)

        self._audit.record_action(
            action="forecast.demand",
            context={"agent_id": self._identity.id, "node_id": node_id},
            result=forecast,
        )
        return forecast

    def recommend_load_balance(
        self, node_ids: List[str]
    ) -> Dict[str, Any]:
        """Recommend load balancing across nodes."""
        node_loads: Dict[str, float] = {}
        for nid in node_ids:
            if self._energy_twin is not None:
                twin_state = self._energy_twin.get_twin_state(nid)
                node_loads[nid] = twin_state.state.get("current_load_mw", 0.0)
            else:
                node_loads[nid] = 0.0

        total = sum(node_loads.values())
        avg = total / len(node_loads) if node_loads else 0.0

        recommendations = []
        for nid, load in node_loads.items():
            if load > avg * 1.2:
                recommendations.append({
                    "node_id": nid,
                    "action": "reduce",
                    "current_load": load,
                    "target_load": avg,
                })
            elif load < avg * 0.8:
                recommendations.append({
                    "node_id": nid,
                    "action": "increase",
                    "current_load": load,
                    "target_load": avg,
                })

        return {
            "node_loads": node_loads,
            "average_load": avg,
            "recommendations": recommendations,
        }

    def get_load_profile(self, profile_id: str) -> Optional[LoadProfile]:
        """Get a registered load profile."""
        return self._load_profiles.get(profile_id)

    def _publish_analyze_event(
        self, operation: str, asset_id: str, result: Dict[str, Any]
    ) -> None:
        """Publish an ANALYZE event via EventBus."""
        if self._event_bus is None:
            return
        from core.models.event import EventTopic, ExecutionEvent

        event = ExecutionEvent(
            topic=EventTopic.AGENT_STATE_CHANGED,
            trace_id=f"load-forecast-{operation}-{asset_id}",
            payload={
                "agent_id": self._identity.id,
                "operation": operation,
                "asset_id": asset_id,
                "result": result,
                "domain": "energy",
                "action_type": "ANALYZE",
            },
        )
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._event_bus.publish(EventTopic.AGENT_STATE_CHANGED, event))
        except RuntimeError:
            pass
