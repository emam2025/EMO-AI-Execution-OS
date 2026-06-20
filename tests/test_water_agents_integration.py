"""Tests for RC17.4.4 — Water Agent Integration.

8 tests covering:
- WaterMonitoringAgent reads plant output from twin
- WaterMonitoringAgent reads pump status from twin
- WaterQualityAgent reads quality readings from twin
- WaterQualityAgent checks quality thresholds
- WaterMaintenanceAgent recommends maintenance from twin
- WaterMaintenanceAgent critical action requires approval
- WaterDistributionAgent reads network status from twin
- WaterDistributionAgent recommends flow adjustment
"""

from __future__ import annotations

import pytest

from core.models.agent import AgentIdentity
from core.industrial.water_twin import WaterTwin
from core.agents.water.water_monitoring_agent import WaterMonitoringAgent
from core.agents.water.water_quality_agent import WaterQualityAgent
from core.agents.water.water_maintenance_agent import WaterMaintenanceAgent
from core.agents.water.water_distribution_agent import WaterDistributionAgent


# ── Helpers ────────────────────────────────────────────────────────────────


def _make_identity(agent_id: str = "test-agent") -> AgentIdentity:
    return AgentIdentity(
        id=agent_id,
        tenant_id="tenant-001",
        org_id="org-001",
        name="Test Agent",
        agent_type="water",
        version="1.0",
    )


class FakeApprovalGate:
    def __init__(self, allowed: bool = True):
        self._allowed = allowed
        self.calls = []

    def check_autonomy(self, agent_id, action, autonomy_level, context=None):
        self.calls.append({
            "agent_id": agent_id,
            "action": action,
            "autonomy_level": autonomy_level,
            "context": context,
        })
        return {"allowed": self._allowed, "requires_approval": True}


# ── Test 1: WaterMonitoringAgent reads plant output from twin ──────────────


def test_water_monitoring_agent_reads_plant_output():
    """WaterMonitoringAgent reads plant output from WaterTwin."""
    twin = WaterTwin()
    twin.update_twin_state("plant-001", {
        "current_flow_mld": 150.0,
        "capacity_mld": 500.0,
        "status": "operational",
    })

    agent = WaterMonitoringAgent(
        identity=_make_identity("monitor-001"),
        water_twin=twin,
    )
    agent.activate()

    result = agent.get_plant_output("plant-001")

    assert result["current_flow_mld"] == 150.0
    assert result["capacity_mld"] == 500.0
    assert result["version"] == 1


# ── Test 2: WaterMonitoringAgent reads pump status from twin ───────────────


def test_water_monitoring_agent_reads_pump_status():
    """WaterMonitoringAgent reads pump station status from WaterTwin."""
    twin = WaterTwin()
    twin.update_twin_state("pump-001", {
        "active_pumps": 3,
        "pump_count": 4,
        "status": "operational",
    })

    agent = WaterMonitoringAgent(
        identity=_make_identity("monitor-002"),
        water_twin=twin,
    )
    agent.activate()

    result = agent.get_pump_status("pump-001")

    assert result["active_pumps"] == 3
    assert result["pump_count"] == 4
    assert result["status"] == "operational"


# ── Test 3: WaterQualityAgent reads quality readings from twin ─────────────


def test_water_quality_agent_reads_readings():
    """WaterQualityAgent reads quality readings from WaterTwin."""
    twin = WaterTwin()
    twin.update_twin_state("sensor-001", {
        "ph_level": 7.2,
        "turbidity_ntu": 0.5,
        "chlorine_ppm": 1.0,
        "status": "active",
    })

    agent = WaterQualityAgent(
        identity=_make_identity("quality-001"),
        water_twin=twin,
    )
    agent.activate()

    result = agent.get_quality_readings("sensor-001")

    assert result["ph_level"] == 7.2
    assert result["turbidity_ntu"] == 0.5
    assert result["chlorine_ppm"] == 1.0


# ── Test 4: WaterQualityAgent checks quality thresholds ────────────────────


def test_water_quality_agent_checks_thresholds():
    """WaterQualityAgent checks quality thresholds and reports violations."""
    twin = WaterTwin()
    twin.update_twin_state("sensor-001", {
        "ph_level": 9.0,
        "turbidity_ntu": 0.5,
        "chlorine_ppm": 1.0,
    })

    agent = WaterQualityAgent(
        identity=_make_identity("quality-002"),
        water_twin=twin,
    )
    agent.activate()

    result = agent.check_quality_thresholds("sensor-001", ph_min=6.5, ph_max=8.5)

    assert result["within_thresholds"] is False
    assert len(result["violations"]) == 1
    assert "pH out of range" in result["violations"][0]


# ── Test 5: WaterMaintenanceAgent recommends maintenance from twin ─────────


def test_water_maintenance_agent_recommends_maintenance():
    """WaterMaintenanceAgent recommends maintenance based on twin state."""
    twin = WaterTwin()
    twin.update_twin_state("pump-001", {
        "efficiency_pct": 75.0,
        "active_pumps": 3,
        "pump_count": 4,
    })

    agent = WaterMaintenanceAgent(
        identity=_make_identity("maintenance-001"),
        water_twin=twin,
    )
    agent.activate()

    result = agent.recommend_maintenance("pump-001")

    assert result["recommendation"] == "schedule_maintenance"
    assert result["priority"] == "high"
    assert result["is_critical"] is False


# ── Test 6: WaterMaintenanceAgent critical action requires approval ────────


def test_water_maintenance_agent_critical_action_requires_approval():
    """WaterMaintenanceAgent checks approval gate for critical actions."""
    twin = WaterTwin()
    twin.update_twin_state("pump-001", {
        "efficiency_pct": 40.0,
        "active_pumps": 1,
        "pump_count": 4,
    })

    gate = FakeApprovalGate(allowed=False)
    agent = WaterMaintenanceAgent(
        identity=_make_identity("maintenance-002"),
        water_twin=twin,
        approval_gate=gate,
    )
    agent.activate()

    result = agent.recommend_maintenance("pump-001")

    assert result["recommendation"] == "critical_action_blocked"
    assert result["is_critical"] is True
    assert gate.calls[0]["action"] == "PUMP_SHUTDOWN"


# ── Test 7: WaterDistributionAgent reads network status from twin ──────────


def test_water_distribution_agent_reads_network_status():
    """WaterDistributionAgent reads network status from WaterTwin."""
    twin = WaterTwin()
    twin.update_twin_state("zone-001", {
        "pressure_psi": 45.0,
        "flow_rate": 120.0,
        "status": "operational",
    })

    agent = WaterDistributionAgent(
        identity=_make_identity("distribution-001"),
        water_twin=twin,
    )
    agent.activate()

    result = agent.get_network_status("zone-001")

    assert result["pressure_psi"] == 45.0
    assert result["flow_rate"] == 120.0
    assert result["version"] == 1


# ── Test 8: WaterDistributionAgent recommends flow adjustment ──────────────


def test_water_distribution_agent_recommends_flow_adjustment():
    """WaterDistributionAgent recommends flow adjustment based on twin state."""
    twin = WaterTwin()
    twin.update_twin_state("zone-001", {
        "flow_rate": 100.0,
        "pressure_psi": 45.0,
    })

    agent = WaterDistributionAgent(
        identity=_make_identity("distribution-002"),
        water_twin=twin,
    )
    agent.activate()

    result = agent.recommend_flow_adjustment("zone-001", target_flow=150.0)

    assert result["recommendation"] == "adjust_flow"
    assert result["current_flow"] == 100.0
    assert result["target_flow"] == 150.0
    assert result["delta"] == 50.0
    assert result["priority"] == "high"
