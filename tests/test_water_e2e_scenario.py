"""Tests for RC17.4.5 — Water E2E Scenario.

Full water domain simulation:
- SCADA → WaterDataPipeline → WaterTwin
- Water quality monitoring with WHO/EPA thresholds
- WaterSafetyGate blocks CONTROL_WRITE/PUMP_SHUTDOWN/VALVE_OVERRIDE
- Agent recommendations: maintenance, distribution, quality
- Approval gate for critical actions
- Audit trail verification
"""

from __future__ import annotations

import asyncio
import pytest

from core.models.agent import AgentIdentity
from core.models.water import WaterActionType, WaterEventSeverity
from core.governance.water_policies import WaterSafetyGate
from core.industrial.water_twin import WaterTwin
from core.industrial.water_data_pipeline import WaterDataPipeline
from core.connectors.water.water_scada_connector import WaterSCADAConnector
from core.agents.water.water_monitoring_agent import WaterMonitoringAgent
from core.agents.water.water_quality_agent import WaterQualityAgent
from core.agents.water.water_maintenance_agent import WaterMaintenanceAgent
from core.agents.water.water_distribution_agent import WaterDistributionAgent


# ── Helpers ────────────────────────────────────────────────────────────────


def _make_identity(agent_id: str) -> AgentIdentity:
    return AgentIdentity(
        id=agent_id,
        tenant_id="tenant-001",
        org_id="org-001",
        name=f"Agent {agent_id}",
        agent_type="water",
        version="1.0",
    )


class FakeEventBus:
    def __init__(self):
        self.events = []

    async def publish(self, topic, event):
        self.events.append((topic, event))


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


# ── Test 1: Full water domain E2E simulation ──────────────────────────────


def test_water_e2e_full_simulation():
    """Full water domain E2E: SCADA → Pipeline → Twin → Agents → Safety → Audit."""
    # Stage 1: Setup
    gate = WaterSafetyGate()
    twin = WaterTwin()
    bus = FakeEventBus()
    pipeline = WaterDataPipeline(water_twin=twin, safety_gate=gate, event_bus=bus)

    scada = WaterSCADAConnector(endpoint_url="scada://water-plant:502")
    scada.set_tag_value("flow_rate", 150.0)
    scada.set_tag_value("pressure_psi", 42.0)
    scada.set_tag_value("ph_level", 7.2)
    scada.set_tag_value("turbidity_ntu", 0.5)
    scada.set_tag_value("chlorine_ppm", 1.0)

    pipeline.register_connector("scada-001", scada)
    pipeline.register_tag_mapping("flow_rate", "plant-001", "current_flow_mld")
    pipeline.register_tag_mapping("pressure_psi", "plant-001", "pressure_psi")
    pipeline.register_tag_mapping("ph_level", "sensor-001", "ph_level")
    pipeline.register_tag_mapping("turbidity_ntu", "sensor-001", "turbidity_ntu")
    pipeline.register_tag_mapping("chlorine_ppm", "sensor-001", "chlorine_ppm")

    # Stage 2: Ingest normal read-only data
    result = pipeline.ingest_from_connector(
        connector_id="scada-001",
        tag_ids=["flow_rate", "pressure_psi", "ph_level", "turbidity_ntu", "chlorine_ppm"],
        trust_level="UNVERIFIED",
    )
    assert result["updated"] == 5
    assert result["blocked"] == 0

    plant_state = twin.get_twin_state("plant-001")
    assert plant_state.state["current_flow_mld"] == 150.0
    assert plant_state.state["pressure_psi"] == 42.0

    sensor_state = twin.get_twin_state("sensor-001")
    assert sensor_state.state["ph_level"] == 7.2
    assert sensor_state.state["turbidity_ntu"] == 0.5
    assert sensor_state.state["chlorine_ppm"] == 1.0

    # Stage 3: Safety gate blocks CONTROL_WRITE
    decision = gate.evaluate(WaterActionType.CONTROL_WRITE, "TRUSTED")
    assert decision.allowed is False
    assert decision.violation_type == "policy_denied"
    assert decision.requires_approval is True

    # Stage 4: Safety gate blocks PUMP_SHUTDOWN
    decision = gate.evaluate(WaterActionType.PUMP_SHUTDOWN, "TRUSTED")
    assert decision.allowed is False
    assert decision.violation_type == "policy_denied"
    assert decision.requires_approval is True

    # Stage 5: Safety gate blocks VALVE_OVERRIDE
    decision = gate.evaluate(WaterActionType.VALVE_OVERRIDE, "TRUSTED")
    assert decision.allowed is False
    assert decision.violation_type == "policy_denied"
    assert decision.requires_approval is True

    # Stage 6: Water monitoring agent reads plant output
    monitor = WaterMonitoringAgent(
        identity=_make_identity("monitor-001"),
        water_twin=twin,
    )
    monitor.activate()
    plant_output = monitor.get_plant_output("plant-001")
    assert plant_output["current_flow_mld"] == 150.0
    assert plant_output["version"] == 2

    # Stage 7: Water quality agent checks thresholds
    quality = WaterQualityAgent(
        identity=_make_identity("quality-001"),
        water_twin=twin,
    )
    quality.activate()
    quality_check = quality.check_quality_thresholds("sensor-001", ph_min=6.5, ph_max=8.5)
    assert quality_check["within_thresholds"] is True

    # Stage 8: Water maintenance agent recommends maintenance
    maintenance = WaterMaintenanceAgent(
        identity=_make_identity("maintenance-001"),
        water_twin=twin,
    )
    maintenance.activate()
    maint_rec = maintenance.recommend_maintenance("plant-001")
    assert maint_rec["recommendation"] == "no_action_needed"

    # Stage 9: Water distribution agent reads network status
    distribution = WaterDistributionAgent(
        identity=_make_identity("distribution-001"),
        water_twin=twin,
    )
    distribution.activate()
    net_status = distribution.get_network_status("plant-001")
    assert net_status["pressure_psi"] == 42.0

    # Stage 10: Audit trail verification
    pipeline_audit = pipeline.get_audit_log()
    assert len(pipeline_audit) == 5
    assert all(a["status"] == "updated" for a in pipeline_audit)

    gate_audit = gate.get_audit_log()
    assert len(gate_audit) == 8  # 5 OBSERVE from pipeline + 3 blocked from safety checks
    blocked_entries = [a for a in gate_audit if not a["allowed"]]
    assert len(blocked_entries) == 3

    twin_events = twin.get_events("sensor-001")
    assert len(twin_events) == 0  # No events recorded for normal operations

    # Stage 11: Stats verification
    stats = pipeline.get_stats()
    assert stats["updated"] == 5
    assert stats["blocked"] == 0
