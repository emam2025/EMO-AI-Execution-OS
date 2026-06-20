"""Tests for RC17.4.3 — Water Twin & DataPipeline Integration.

6 tests covering:
- WaterTwin state update and version increment
- WaterTwin simulation and prediction
- WaterDataPipeline ingest blocks CONTROL_WRITE via WaterSafetyGate
- WaterDataPipeline ingest_from_connector reads live data
- WaterTwin audit trail records events
- WaterDataPipeline audit trail records ingestion
"""

from __future__ import annotations

import pytest

from core.models.water import WaterActionType, WaterOperationalEvent, WaterEventSeverity
from core.governance.water_policies import WaterSafetyGate
from core.industrial.water_twin import WaterTwin
from core.industrial.water_data_pipeline import WaterDataPipeline
from core.connectors.water.water_scada_connector import WaterSCADAConnector


# ── Test 1: WaterTwin state update and version increment ───────────────────


def test_water_twin_state_update_and_version():
    """WaterTwin state updates correctly and version increments."""
    twin = WaterTwin()

    state = twin.update_twin_state("plant-001", {"flow_rate": 120.5})
    assert state.version == 1
    assert state.state["flow_rate"] == 120.5

    state = twin.update_twin_state("plant-001", {"pressure_psi": 45.0})
    assert state.version == 2
    assert state.state["flow_rate"] == 120.5
    assert state.state["pressure_psi"] == 45.0


# ── Test 2: WaterTwin simulation and prediction ───────────────────────────


def test_water_twin_simulation_and_prediction():
    """WaterTwin simulation and prediction return structured results."""
    twin = WaterTwin()
    twin.update_twin_state("pump-001", {"active_pumps": 3})

    sim = twin.simulate(
        "pump-001",
        {
            "state_changes": {"active_pumps": 1},
            "expected_outcome": "reduced_flow",
        },
    )
    assert sim["result"]["simulated_state"]["active_pumps"] == 1
    assert sim["result"]["predicted_outcome"] == "reduced_flow"
    assert len(twin.get_simulations()) == 1

    pred = twin.predict("pump-001", horizon_hours=12)
    assert pred["horizon_hours"] == 12
    assert pred["current_state"]["active_pumps"] == 3


# ── Test 3: WaterDataPipeline blocks CONTROL_WRITE ────────────────────────


def test_water_data_pipeline_blocks_control_write():
    """WaterDataPipeline blocks CONTROL_WRITE via WaterSafetyGate."""
    twin = WaterTwin()
    gate = WaterSafetyGate()

    class FakeEventBus:
        def __init__(self):
            self.events = []
        async def publish(self, topic, event):
            self.events.append((topic, event))

    bus = FakeEventBus()
    pipeline = WaterDataPipeline(water_twin=twin, safety_gate=gate, event_bus=bus)

    pipeline.register_tag_mapping("control_valve_001", "valve-001", "valve_override")

    result = pipeline.ingest_water_data(
        connector_id="test",
        tag_data={"control_valve_001": True},
        trust_level="TRUSTED",
    )

    assert result["blocked"] == 1
    assert result["updated"] == 0
    assert result["details"][0]["status"] == "blocked"
    assert result["details"][0]["violation_type"] == "policy_denied"


# ── Test 4: WaterDataPipeline ingest_from_connector ────────────────────────


def test_water_data_pipeline_ingest_from_connector():
    """WaterDataPipeline ingest_from_connector reads live SCADA data."""
    twin = WaterTwin()
    gate = WaterSafetyGate()

    class FakeEventBus:
        def __init__(self):
            self.events = []
        async def publish(self, topic, event):
            self.events.append((topic, event))

    bus = FakeEventBus()
    pipeline = WaterDataPipeline(water_twin=twin, safety_gate=gate, event_bus=bus)

    scada = WaterSCADAConnector()
    scada.set_tag_value("flow_rate", 150.0)
    scada.set_tag_value("pressure_psi", 42.0)

    pipeline.register_connector("scada-001", scada)
    pipeline.register_tag_mapping("flow_rate", "plant-001", "current_flow_mld")
    pipeline.register_tag_mapping("pressure_psi", "plant-001", "pressure_psi")

    result = pipeline.ingest_from_connector(
        connector_id="scada-001",
        tag_ids=["flow_rate", "pressure_psi"],
        trust_level="UNVERIFIED",
    )

    assert result["updated"] == 2
    assert result["blocked"] == 0

    state = twin.get_twin_state("plant-001")
    assert state.state["current_flow_mld"] == 150.0
    assert state.state["pressure_psi"] == 42.0


# ── Test 5: WaterTwin audit trail records events ──────────────────────────


def test_water_twin_audit_trail_records_events():
    """WaterTwin records operational events in audit trail."""
    twin = WaterTwin()

    event = WaterOperationalEvent(
        event_id="evt-001",
        asset_id="plant-001",
        event_type="quality_alert",
        severity=WaterEventSeverity.WARNING,
        message="pH level below threshold",
    )
    twin.record_event("plant-001", event)

    events = twin.get_events("plant-001")
    assert len(events) == 1
    assert events[0].event_type == "quality_alert"
    assert events[0].severity == WaterEventSeverity.WARNING

    events_limited = twin.get_events("plant-001", limit=1)
    assert len(events_limited) == 1


# ── Test 6: WaterDataPipeline audit trail records ingestion ────────────────


def test_water_data_pipeline_audit_trail():
    """WaterDataPipeline records ingestion events in audit trail."""
    twin = WaterTwin()
    gate = WaterSafetyGate()

    class FakeEventBus:
        def __init__(self):
            self.events = []
        async def publish(self, topic, event):
            self.events.append((topic, event))

    bus = FakeEventBus()
    pipeline = WaterDataPipeline(water_twin=twin, safety_gate=gate, event_bus=bus)

    pipeline.register_tag_mapping("ph_001", "sensor-001", "ph_level")

    pipeline.ingest_water_data(
        connector_id="test",
        tag_data={"ph_001": 7.2},
        trust_level="UNVERIFIED",
    )

    audit = pipeline.get_audit_log()
    assert len(audit) == 1
    assert audit[0]["tag_id"] == "ph_001"
    assert audit[0]["asset_id"] == "sensor-001"
    assert audit[0]["status"] == "updated"

    stats = pipeline.get_stats()
    assert stats["updated"] == 1
    assert stats["blocked"] == 0
