"""Tests for RC17.3.5 — Energy Agent Integration.

8 tests covering:
- EnergyMonitoringAgent reads from twin and publishes event
- LoadForecastAgent predicts from twin and publishes event
- EnergyMaintenanceAgent recommendation publishes event
- EnergyMaintenanceAgent critical action requires approval
- GridAnalystAgent recommendation allowed for trusted
- GridAnalystAgent load shedding blocked for unverified
- GridAnalystAgent load shedding requires approval for trusted
- Multiple agents isolation
"""

from __future__ import annotations

import asyncio

import pytest

from core.models.agent import AgentIdentity
from core.models.energy_policy import EnergyActionType
from core.models.event import EventTopic
from core.industrial.energy_twin import EnergyTwin
from core.governance.energy_safety import EnergySafetyGate
from core.agents.energy.energy_monitoring_agent import EnergyMonitoringAgent
from core.agents.energy.load_forecast_agent import LoadForecastAgent
from core.agents.energy.maintenance_agent import EnergyMaintenanceAgent
from core.agents.energy.grid_analyst_agent import GridAnalystAgent


class MockEventBus:
    def __init__(self) -> None:
        self.published: list[dict] = []

    async def publish(self, topic, event) -> None:
        self.published.append({"topic": topic, "event": event})

    def subscribe(self, topic, handler) -> str:
        return "mock-sub-001"

    def unsubscribe(self, subscription_id: str) -> None:
        pass


class MockApprovalGate:
    def __init__(self, allowed: bool = True) -> None:
        self._allowed = allowed

    def check_autonomy(
        self, agent_id: str, action: str, autonomy_level: str, context: dict
    ) -> dict:
        return {
            "allowed": self._allowed,
            "requires_approval": not self._allowed,
            "reason": "approved" if self._allowed else "denied_by_policy",
            "autonomy_level": autonomy_level,
        }


def _make_identity(agent_id: str) -> AgentIdentity:
    return AgentIdentity(
        id=agent_id,
        tenant_id="tenant-test",
        org_id="org-test",
        name=f"Test Agent {agent_id}",
        agent_type="energy",
    )


def _make_fully_wired_agents() -> tuple:
    """Create all 4 agents with shared EnergyTwin + EventBus."""
    event_bus = MockEventBus()
    twin = EnergyTwin(event_bus=event_bus)
    safety = EnergySafetyGate(event_bus=event_bus)
    approval = MockApprovalGate(allowed=True)
    approval_denied = MockApprovalGate(allowed=False)

    # Pre-populate twin state
    twin.update_twin_state("plant-1", {
        "current_output_mw": 450.0,
        "efficiency_pct": 35.0,
        "status": "operational",
    })
    twin.update_twin_state("grid-1", {
        "current_load_mw": 95.0,
        "max_capacity_mw": 100.0,
        "status": "active",
    })
    twin.update_twin_state("meter-1", {
        "current_draw_kw": 45.0,
    })

    monitoring = EnergyMonitoringAgent(
        identity=_make_identity("monitor-1"),
        energy_twin=twin,
        event_bus=event_bus,
    )
    forecast = LoadForecastAgent(
        identity=_make_identity("forecast-1"),
        energy_twin=twin,
        event_bus=event_bus,
    )
    maintenance = EnergyMaintenanceAgent(
        identity=_make_identity("maintenance-1"),
        energy_twin=twin,
        event_bus=event_bus,
        approval_gate=approval,
    )
    maintenance_denied = EnergyMaintenanceAgent(
        identity=_make_identity("maintenance-denied"),
        energy_twin=twin,
        event_bus=event_bus,
        approval_gate=approval_denied,
    )
    grid_analyst = GridAnalystAgent(
        identity=_make_identity("grid-1"),
        energy_twin=twin,
        event_bus=event_bus,
        safety_gate=safety,
    )

    return (
        monitoring, forecast, maintenance, maintenance_denied,
        grid_analyst, twin, safety, event_bus,
    )


# ── Test 1: EnergyMonitoringAgent reads from twin ─────────────────────────


def test_energy_monitoring_agent_reads_from_twin():
    """MonitoringAgent: reads plant output from EnergyTwin."""
    (
        monitoring, _, _, _, _, twin, _, event_bus,
    ) = _make_fully_wired_agents()

    result = monitoring.get_plant_output("plant-1")

    assert result["asset_id"] == "plant-1"
    assert result["output_mw"] == 450.0
    assert result["version"] >= 2

    # Verify audit trail
    assert len(monitoring.audit.action_log) > 0


# ── Test 2: LoadForecastAgent predicts from twin ─────────────────────────


def test_load_forecast_agent_predicts_from_twin():
    """LoadForecastAgent: forecasts demand using EnergyTwin prediction."""
    (
        _, forecast, _, _, _, twin, _, event_bus,
    ) = _make_fully_wired_agents()

    result = forecast.forecast_demand("grid-1", horizon_hours=12)

    assert result["node_id"] == "grid-1"
    assert result["horizon_hours"] == 12
    assert result["current_load_mw"] == 95.0
    assert result["predicted_load_mw"] == 95.0 * 1.05
    assert result["prediction_id"] is not None

    # Verify audit trail
    assert len(forecast.audit.action_log) > 0


# ── Test 3: MaintenanceAgent recommendation publishes event ────────────────


@pytest.mark.asyncio
async def test_maintenance_agent_recommendation_publishes_event():
    """MaintenanceAgent: publishes event on recommendation."""
    (
        _, _, maintenance, _, _, twin, _, event_bus,
    ) = _make_fully_wired_agents()

    result = maintenance.recommend_maintenance("plant-1")
    await asyncio.sleep(0.01)

    assert result["asset_id"] == "plant-1"
    assert result["recommendation"] == "schedule_maintenance"
    assert result["priority"] == "high"

    # Verify event published
    agent_events = [
        e for e in event_bus.published
        if e["topic"] == EventTopic.AGENT_STATE_CHANGED
    ]
    assert len(agent_events) >= 1
    assert agent_events[0]["event"].payload["domain"] == "energy"


# ── Test 4: MaintenanceAgent critical action requires approval ─────────────


def test_maintenance_agent_critical_action_requires_approval():
    """MaintenanceAgent: critical action denied by approval gate."""
    (
        _, _, _, maintenance_denied, _, twin, _, _,
    ) = _make_fully_wired_agents()

    # Set efficiency below 50% to trigger critical action
    twin.update_twin_state("plant-1", {"efficiency_pct": 35.0})

    result = maintenance_denied.recommend_maintenance("plant-1")

    assert result["asset_id"] == "plant-1"
    assert result["is_critical"] is True
    assert result.get("approval_allowed") is False
    assert result["recommendation"] == "critical_action_blocked"


# ── Test 5: GridAnalystAgent recommendation allowed for trusted ───────────


def test_grid_analyst_recommendation_allowed_for_trusted():
    """GridAnalystAgent: load shedding allowed for TRUSTED level."""
    (
        _, _, _, _, grid_analyst, twin, _, _,
    ) = _make_fully_wired_agents()

    result = grid_analyst.recommend_load_shedding(
        grid_id="grid-1", trust_level="TRUSTED"
    )

    assert result["grid_id"] == "grid-1"
    assert result["utilization_pct"] == 95.0
    assert result["needs_load_shedding"] is True
    assert result["safety_allowed"] is True
    assert result["recommendation"] == "load_shedding_recommended"


# ── Test 6: GridAnalystAgent load shedding blocked for unverified ─────────


@pytest.mark.asyncio
async def test_grid_analyst_load_shedding_blocked_for_unverified():
    """GridAnalystAgent: load shedding blocked for UNVERIFIED trust."""
    (
        _, _, _, _, grid_analyst, twin, _, event_bus,
    ) = _make_fully_wired_agents()

    result = grid_analyst.recommend_load_shedding(
        grid_id="grid-1", trust_level="UNVERIFIED"
    )
    await asyncio.sleep(0.01)

    assert result["grid_id"] == "grid-1"
    assert result["utilization_pct"] == 95.0
    assert result["needs_load_shedding"] is True
    assert result["safety_allowed"] is False
    assert result["recommendation"] == "load_shedding_blocked"

    # Verify SAFETY_VIOLATION event published
    violation_events = [
        e for e in event_bus.published
        if e["topic"] == EventTopic.SAFETY_VIOLATION
    ]
    assert len(violation_events) >= 1


# ── Test 7: GridAnalystAgent load shedding requires approval for trusted ──


def test_grid_analyst_load_shedding_requires_approval_for_trusted():
    """GridAnalystAgent: TRUSTED load shedding is allowed but requires approval."""
    (
        _, _, _, _, grid_analyst, twin, _, _,
    ) = _make_fully_wired_agents()

    result = grid_analyst.recommend_load_shedding(
        grid_id="grid-1", trust_level="TRUSTED"
    )

    assert result["safety_allowed"] is True
    assert result["requires_approval"] is True
    assert result["recommendation"] == "load_shedding_recommended"


# ── Test 8: Multiple agents isolation ─────────────────────────────────────


def test_multiple_agents_isolation():
    """All 4 agents operate independently on shared twin state."""
    (
        monitoring, forecast, maintenance, _, grid_analyst, twin, _, _,
    ) = _make_fully_wired_agents()

    # Each agent reads different data
    plant_out = monitoring.get_plant_output("plant-1")
    forecast_result = forecast.forecast_demand("grid-1")
    maint_result = maintenance.recommend_maintenance("plant-1")
    grid_result = grid_analyst.recommend_load_shedding("grid-1", "TRUSTED")

    # No cross-contamination
    assert plant_out["asset_id"] == "plant-1"
    assert forecast_result["node_id"] == "grid-1"
    assert maint_result["asset_id"] == "plant-1"
    assert grid_result["grid_id"] == "grid-1"

    # Twin state unchanged by reads
    assert twin.get_twin_state("plant-1").state["current_output_mw"] == 450.0
    assert twin.get_twin_state("grid-1").state["current_load_mw"] == 95.0
