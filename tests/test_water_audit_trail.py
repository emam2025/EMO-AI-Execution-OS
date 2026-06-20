"""Tests for RC17.4.6 — Water E2E Audit Trail Verification.

Verifies that all water domain components produce complete, consistent
audit trails: WaterSafetyGate, WaterDataPipeline, WaterTwin, and agents.
"""

from __future__ import annotations

import pytest

from core.models.agent import AgentIdentity
from core.models.water import WaterActionType, WaterEventSeverity, WaterOperationalEvent
from core.governance.water_policies import WaterSafetyGate
from core.industrial.water_twin import WaterTwin
from core.industrial.water_data_pipeline import WaterDataPipeline
from core.connectors.water.water_scada_connector import WaterSCADAConnector
from core.connectors.water.water_modbus_connector import WaterModbusConnector
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


# ── Test 1: WaterSafetyGate audit trail completeness ──────────────────────


def test_water_safety_gate_audit_trail_completeness():
    """WaterSafetyGate records every evaluation in audit log."""
    gate = WaterSafetyGate()

    gate.evaluate(WaterActionType.OBSERVE, "UNVERIFIED")
    gate.evaluate(WaterActionType.ANALYZE, "UNVERIFIED")
    gate.evaluate(WaterActionType.RECOMMEND, "VERIFIED")
    gate.evaluate(WaterActionType.CONTROL_WRITE, "TRUSTED")
    gate.evaluate(WaterActionType.PUMP_SHUTDOWN, "TRUSTED")
    gate.evaluate(WaterActionType.VALVE_OVERRIDE, "TRUSTED")
    gate.evaluate("UNKNOWN_ACTION", "TRUSTED")

    log = gate.get_audit_log()
    assert len(log) == 7

    allowed = [e for e in log if e["allowed"]]
    denied = [e for e in log if not e["allowed"]]
    assert len(allowed) == 3  # OBSERVE, ANALYZE, RECOMMEND
    assert len(denied) == 4  # CONTROL_WRITE, PUMP_SHUTDOWN, VALVE_OVERRIDE, UNKNOWN

    for entry in log:
        assert "action_type" in entry
        assert "allowed" in entry
        assert "reason" in entry
        assert "violation_type" in entry or entry["allowed"]


# ── Test 2: WaterDataPipeline audit trail records ingestion ───────────────


def test_water_data_pipeline_audit_trail_records_ingestion():
    """WaterDataPipeline records all ingestion events with correct fields."""
    twin = WaterTwin()
    gate = WaterSafetyGate()
    bus = FakeEventBus()
    pipeline = WaterDataPipeline(water_twin=twin, safety_gate=gate, event_bus=bus)

    pipeline.register_tag_mapping("flow_001", "plant-001", "current_flow_mld")
    pipeline.register_tag_mapping("ph_001", "sensor-001", "ph_level")
    pipeline.register_tag_mapping("control_001", "valve-001", "valve_override")

    pipeline.ingest_water_data(
        connector_id="test",
        tag_data={"flow_001": 150.0, "ph_001": 7.2, "control_001": True},
        trust_level="TRUSTED",
    )

    audit = pipeline.get_audit_log()
    assert len(audit) == 3

    updated = [e for e in audit if e["status"] == "updated"]
    blocked = [e for e in audit if e["status"] == "blocked"]
    assert len(updated) == 2
    assert len(blocked) == 1

    for entry in audit:
        assert "tag_id" in entry
        assert "asset_id" in entry
        assert "field" in entry
        assert "status" in entry
        assert "reason" in entry


# ── Test 3: WaterTwin audit trail records operational events ──────────────


def test_water_twin_audit_trail_records_operational_events():
    """WaterTwin records operational events with full metadata."""
    twin = WaterTwin()

    events = [
        WaterOperationalEvent(
            event_id=f"evt-{i}",
            asset_id=f"asset-{i}",
            event_type="quality_alert",
            severity=WaterEventSeverity.WARNING,
            message=f"Alert {i}",
            metadata={"key": f"value_{i}"},
        )
        for i in range(5)
    ]

    for event in events:
        twin.record_event(event.asset_id, event)

    for i in range(5):
        recorded = twin.get_events(f"asset-{i}")
        assert len(recorded) == 1
        assert recorded[0].event_id == f"evt-{i}"
        assert recorded[0].event_type == "quality_alert"
        assert recorded[0].severity == WaterEventSeverity.WARNING
        assert recorded[0].metadata["key"] == f"value_{i}"

    all_events = twin.get_events("asset-0", limit=1)
    assert len(all_events) == 1


# ── Test 4: WaterSafetyGate audit trail with trust level enforcement ──────


def test_water_safety_gate_audit_trail_trust_enforcement():
    """WaterSafetyGate records trust level violations in audit log."""
    gate = WaterSafetyGate()

    gate.evaluate(WaterActionType.PUMP_SHUTDOWN, "UNVERIFIED")
    gate.evaluate(WaterActionType.PUMP_SHUTDOWN, "VERIFIED")
    gate.evaluate(WaterActionType.PUMP_SHUTDOWN, "TRUSTED")

    log = gate.get_audit_log()
    assert len(log) == 3

    trust_violations = [e for e in log if e["violation_type"] == "trust_insufficient"]
    policy_denials = [e for e in log if e["violation_type"] == "policy_denied"]
    assert len(trust_violations) == 2  # UNVERIFIED, VERIFIED
    assert len(policy_denials) == 1  # TRUSTED (policy denies, requires approval)

    assert log[0]["reason"].startswith("Trust level insufficient")
    assert log[1]["reason"].startswith("Trust level insufficient")
    assert log[2]["reason"].startswith("Policy denies action")


# ── Test 5: Full E2E audit trail verification ─────────────────────────────


def test_water_e2e_full_audit_trail_verification():
    """Full E2E: all components produce consistent audit trails."""
    gate = WaterSafetyGate()
    twin = WaterTwin()
    bus = FakeEventBus()
    pipeline = WaterDataPipeline(water_twin=twin, safety_gate=gate, event_bus=bus)

    scada = WaterSCADAConnector()
    scada.set_tag_value("flow_rate", 150.0)
    scada.set_tag_value("ph_level", 7.2)

    modbus = WaterModbusConnector()
    modbus.set_register_value("turbidity_001", 0.5)

    pipeline.register_connector("scada-001", scada)
    pipeline.register_connector("modbus-001", modbus)
    pipeline.register_tag_mapping("flow_rate", "plant-001", "current_flow_mld")
    pipeline.register_tag_mapping("ph_level", "sensor-001", "ph_level")
    pipeline.register_tag_mapping("turbidity_001", "sensor-001", "turbidity_ntu")

    pipeline.ingest_from_connector("scada-001", ["flow_rate", "ph_level"])
    pipeline.ingest_from_connector("modbus-001", ["turbidity_001"])

    gate.evaluate(WaterActionType.CONTROL_WRITE, "TRUSTED")
    gate.evaluate(WaterActionType.PUMP_SHUTDOWN, "UNVERIFIED")

    monitor = WaterMonitoringAgent(
        identity=_make_identity("monitor-001"), water_twin=twin
    )
    monitor.activate()
    monitor.get_plant_output("plant-001")
    monitor.report_anomaly("plant-001", "low_pressure", {"psi": 30.0})

    quality = WaterQualityAgent(
        identity=_make_identity("quality-001"), water_twin=twin
    )
    quality.activate()
    quality.get_quality_readings("sensor-001")
    quality.check_quality_thresholds("sensor-001")

    maintenance = WaterMaintenanceAgent(
        identity=_make_identity("maint-001"), water_twin=twin
    )
    maintenance.activate()
    maintenance.recommend_maintenance("plant-001")

    distribution = WaterDistributionAgent(
        identity=_make_identity("dist-001"), water_twin=twin
    )
    distribution.activate()
    distribution.get_network_status("plant-001")
    distribution.report_distribution_issue("plant-001", "pipe_leak", {"location": "zone-A"})

    pipeline_audit = pipeline.get_audit_log()
    assert len(pipeline_audit) == 3
    assert all(e["status"] == "updated" for e in pipeline_audit)

    gate_audit = gate.get_audit_log()
    assert len(gate_audit) == 5
    blocked = [e for e in gate_audit if not e["allowed"]]
    assert len(blocked) == 2

    plant_events = twin.get_events("plant-001")
    assert len(plant_events) == 2
    assert plant_events[0].event_type == "low_pressure"

    sensor_events = twin.get_events("sensor-001")
    assert len(sensor_events) == 1
    assert sensor_events[0].event_type == "quality_alert"

    dist_events = twin.get_events("plant-001")
    assert len(dist_events) == 2
    assert dist_events[1].event_type == "pipe_leak"

    monitor_audit = monitor.audit
    assert len(monitor_audit.action_log) >= 2

    quality_audit = quality.audit
    assert len(quality_audit.action_log) >= 2

    maint_audit = maintenance.audit
    assert len(maint_audit.action_log) >= 1

    dist_audit = distribution.audit
    assert len(dist_audit.action_log) >= 2

    stats = pipeline.get_stats()
    assert stats["updated"] == 3
    assert stats["blocked"] == 0
