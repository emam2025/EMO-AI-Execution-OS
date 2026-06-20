"""Tests for RC17.3.3 — Energy Twin & DataPipeline Integration.

6 tests covering:
- Read-only data ingestion updates twin
- Control write blocked by safety gate
- Twin state version increments
- TWIN_STATE_UPDATED event publishing
- Audit trail records ingestion
- Multiple assets isolation
"""

import asyncio

import pytest

from core.models.event import EventTopic
from core.industrial.energy_twin import EnergyTwin
from core.governance.energy_safety import EnergySafetyGate
from core.industrial.energy_data_pipeline import EnergyDataPipeline


class MockEventBus:
    def __init__(self) -> None:
        self.published: list[dict] = []

    async def publish(self, topic: EventTopic, event) -> None:
        self.published.append({"topic": topic, "event": event})

    def subscribe(self, topic, handler) -> str:
        return "mock-sub-001"

    def unsubscribe(self, subscription_id: str) -> None:
        pass


def _make_pipeline() -> tuple:
    """Create a fully wired EnergyDataPipeline with mock event bus."""
    event_bus = MockEventBus()
    twin = EnergyTwin(event_bus=event_bus)
    safety = EnergySafetyGate(event_bus=event_bus)
    pipeline = EnergyDataPipeline(
        energy_twin=twin,
        safety_gate=safety,
        event_bus=event_bus,
    )
    return pipeline, twin, safety, event_bus


# ── Test 1: Read-only data updates twin ────────────────────────────────────


def test_ingest_read_only_data_updates_twin():
    """Pipeline: OBSERVE telemetry data updates EnergyTwin successfully."""
    pipeline, twin, _, _ = _make_pipeline()
    pipeline.register_tag_mapping("PLANT1.OUTPUT", "plant-1", "current_output_mw")
    pipeline.register_tag_mapping("PLANT1.EFFICIENCY", "plant-1", "efficiency_pct")

    result = pipeline.ingest_energy_data(
        connector_id="scada",
        tag_data={"PLANT1.OUTPUT": 450.0, "PLANT1.EFFICIENCY": 38.5},
        trust_level="UNVERIFIED",
    )

    assert result["updated"] == 2
    assert result["blocked"] == 0

    twin_state = twin.get_twin_state("plant-1")
    assert twin_state.state["current_output_mw"] == 450.0
    assert twin_state.state["efficiency_pct"] == 38.5


# ── Test 2: Control write blocked by safety gate ───────────────────────────


def test_ingest_control_write_data_is_blocked_by_safety_gate():
    """Pipeline: CONTROL_WRITE data is blocked by EnergySafetyGate."""
    pipeline, twin, _, event_bus = _make_pipeline()
    pipeline.register_tag_mapping("PLANT1.SETPOINT", "plant-1", "control_setpoint")

    result = pipeline.ingest_energy_data(
        connector_id="scada",
        tag_data={"PLANT1.SETPOINT": 500.0},
        trust_level="UNVERIFIED",
    )

    assert result["blocked"] == 1
    assert result["updated"] == 0

    # Twin should NOT have the control value
    twin_state = twin.get_twin_state("plant-1")
    assert "control_setpoint" not in twin_state.state


# ── Test 3: Twin state version increments ──────────────────────────────────


def test_twin_state_version_increments_on_valid_update():
    """Pipeline: valid updates cause EnergyTwin version to increment."""
    pipeline, twin, _, _ = _make_pipeline()
    pipeline.register_tag_mapping("GRID1.LOAD", "grid-1", "current_load_mw")

    pipeline.ingest_energy_data(
        connector_id="scada",
        tag_data={"GRID1.LOAD": 120.0},
        trust_level="UNVERIFIED",
    )
    state_v1 = twin.get_twin_state("grid-1")
    version_after_first = state_v1.version
    load_after_first = state_v1.state["current_load_mw"]

    pipeline.ingest_energy_data(
        connector_id="scada",
        tag_data={"GRID1.LOAD": 135.0},
        trust_level="UNVERIFIED",
    )
    state_v2 = twin.get_twin_state("grid-1")

    assert version_after_first == 2
    assert load_after_first == 120.0
    assert state_v2.version == 3
    assert state_v2.state["current_load_mw"] == 135.0


# ── Test 4: Pipeline publishes TWIN_STATE_UPDATED event ────────────────────


@pytest.mark.asyncio
async def test_energy_pipeline_publishes_twin_updated_event():
    """Pipeline: successful updates publish TWIN_STATE_UPDATED events."""
    pipeline, twin, _, event_bus = _make_pipeline()
    pipeline.register_tag_mapping("METER1.DRAW", "meter-1", "current_draw_kw")

    pipeline.ingest_energy_data(
        connector_id="mqtt",
        tag_data={"METER1.DRAW": 45.2},
        trust_level="UNVERIFIED",
    )
    await asyncio.sleep(0.01)

    twin_events = [
        e for e in event_bus.published
        if e["topic"] == EventTopic.TWIN_STATE_UPDATED
    ]
    assert len(twin_events) >= 1
    assert twin_events[0]["event"].payload["asset_id"] == "meter-1"
    assert twin_events[0]["event"].payload["domain"] == "energy"


# ── Test 5: Audit trail records ingestion ──────────────────────────────────


def test_energy_pipeline_audit_trail_records_ingestion():
    """Pipeline: every ingestion is recorded in the audit trail."""
    pipeline, twin, _, _ = _make_pipeline()
    pipeline.register_tag_mapping("PLANT1.OUTPUT", "plant-1", "current_output_mw")
    pipeline.register_tag_mapping("PLANT1.SETPOINT", "plant-1", "control_setpoint")

    pipeline.ingest_energy_data(
        connector_id="scada",
        tag_data={
            "PLANT1.OUTPUT": 450.0,
            "PLANT1.SETPOINT": 500.0,
        },
        trust_level="UNVERIFIED",
    )

    log = pipeline.get_audit_log()
    assert len(log) == 2

    updated_entry = next(e for e in log if e["status"] == "updated")
    assert updated_entry["field"] == "current_output_mw"
    assert updated_entry["asset_id"] == "plant-1"

    blocked_entry = next(e for e in log if e["status"] == "blocked")
    assert blocked_entry["field"] == "control_setpoint"


# ── Test 6: Multiple assets isolation ──────────────────────────────────────


def test_multiple_assets_isolation_in_energy_twin():
    """Pipeline: data for different assets is isolated in EnergyTwin."""
    pipeline, twin, _, _ = _make_pipeline()
    pipeline.register_tag_mapping("PLANT1.OUTPUT", "plant-1", "current_output_mw")
    pipeline.register_tag_mapping("GRID1.LOAD", "grid-1", "current_load_mw")
    pipeline.register_tag_mapping("METER1.DRAW", "meter-1", "current_draw_kw")

    pipeline.ingest_energy_data(
        connector_id="scada",
        tag_data={
            "PLANT1.OUTPUT": 450.0,
            "GRID1.LOAD": 120.0,
            "METER1.DRAW": 45.2,
        },
        trust_level="UNVERIFIED",
    )

    plant1 = twin.get_twin_state("plant-1")
    grid1 = twin.get_twin_state("grid-1")
    meter1 = twin.get_twin_state("meter-1")

    assert plant1.state["current_output_mw"] == 450.0
    assert grid1.state["current_load_mw"] == 120.0
    assert meter1.state["current_draw_kw"] == 45.2

    # No cross-contamination
    assert "current_load_mw" not in plant1.state
    assert "current_output_mw" not in grid1.state
    assert "current_draw_kw" not in plant1.state
