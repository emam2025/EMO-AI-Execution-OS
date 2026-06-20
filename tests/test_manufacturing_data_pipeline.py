"""Tests for Manufacturing Data Pipeline (RC17.1.5).

6 tests covering connector ingestion, safety validation, twin updates,
event publishing, background loop, and audit trail.

Ref: RC17.1.5 — Manufacturing Data Pipeline (Connectors → TwinManager)
"""

import asyncio

import pytest

from core.industrial.data_pipeline import DataPipeline
from core.models.event import EventTopic


# ── Mocks ─────────────────────────────────────────────────────────────────────


class MockTwinManager:
    """Mock ITwinManager for testing."""

    def __init__(self) -> None:
        self.states: dict = {}
        self.update_calls: list[dict] = []

    def get_twin_state(self, asset_id: str):
        from core.models.industrial import TwinState
        return self.states.get(asset_id, TwinState(asset_id=asset_id, state={}))

    def update_twin_state(self, asset_id: str, new_state: dict):
        from core.models.industrial import TwinState
        old = self.states.get(asset_id, TwinState(asset_id=asset_id, state={}))
        updated = TwinState(
            asset_id=asset_id,
            state={**old.state, **new_state},
            version=old.version + 1,
        )
        self.states[asset_id] = updated
        self.update_calls.append({"asset_id": asset_id, "new_state": new_state})
        return updated

    def simulate(self, asset_id, scenario):
        return {}

    def record_event(self, asset_id, event):
        pass


class MockEventBus:
    """Mock IEventBus for testing."""

    def __init__(self) -> None:
        self.published: list[dict] = []

    async def publish(self, topic: EventTopic, event) -> None:
        self.published.append({"topic": topic, "event": event})

    def subscribe(self, topic, handler) -> str:
        return "mock-sub-001"

    def unsubscribe(self, subscription_id: str) -> None:
        pass


class MockConnector:
    """Mock OPC-UA connector for testing."""

    def __init__(self, values: dict) -> None:
        self._values = values

    def read_node_values(self, node_ids: list) -> dict:
        results = {}
        for nid in node_ids:
            if nid in self._values:
                results[nid] = self._values[nid]
            else:
                raise ValueError(f"Node not found: {nid}")
        return results


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_read_event(node_ids: list, connector_type: str = "opcua"):
    """Create a mock CONNECTOR_READ_SUCCESS event."""
    from core.models.event import ExecutionEvent
    return ExecutionEvent(
        topic=EventTopic.CONNECTOR_READ_SUCCESS,
        trace_id="test-trace",
        payload={
            "connector_type": connector_type,
            "node_ids": node_ids,
            "success": True,
        },
    )


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_register_connector_and_mapping():
    """register_connector and register_mapping must store values correctly."""
    tm = MockTwinManager()
    eb = MockEventBus()
    pipeline = DataPipeline(twin_manager=tm, event_bus=eb)

    connector = MockConnector({"temp_01": 72.5})
    pipeline.register_connector("opcua-1", connector)
    pipeline.register_mapping("temp_01", "asset-line-1", "temperature")

    assert "opcua-1" in pipeline._connectors
    assert pipeline._mappings["temp_01"]["asset_id"] == "asset-line-1"
    assert pipeline._mappings["temp_01"]["field"] == "temperature"


@pytest.mark.asyncio
async def test_ingest_updates_twin_state():
    """Ingestion event must update twin state with the read value."""
    tm = MockTwinManager()
    eb = MockEventBus()
    pipeline = DataPipeline(twin_manager=tm, event_bus=eb)

    connector = MockConnector({"temp_01": 72.5})
    pipeline.register_connector("opcua-1", connector)
    pipeline.register_mapping("temp_01", "asset-line-1", "temperature")

    event = _make_read_event(["temp_01"], "opcua-1")
    await pipeline._handle_connector_read(event)

    assert len(tm.update_calls) == 1
    assert tm.update_calls[0]["asset_id"] == "asset-line-1"
    assert tm.update_calls[0]["new_state"]["temperature"] == 72.5


@pytest.mark.asyncio
async def test_ingest_respects_safety_limits():
    """Values exceeding threshold must trigger SAFETY_VIOLATION, not twin update."""
    tm = MockTwinManager()
    eb = MockEventBus()
    pipeline = DataPipeline(twin_manager=tm, event_bus=eb)

    pipeline.set_threshold("temperature", 100.0)

    connector = MockConnector({"temp_02": 150.0})
    pipeline.register_connector("opcua-1", connector)
    pipeline.register_mapping("temp_02", "asset-line-2", "temperature")

    event = _make_read_event(["temp_02"], "opcua-1")
    await pipeline._handle_connector_read(event)
    await asyncio.sleep(0.01)

    # Twin must NOT be updated
    assert len(tm.update_calls) == 0
    # SAFETY_VIOLATION must be published
    violations = [p for p in eb.published if p["topic"] == EventTopic.SAFETY_VIOLATION]
    assert len(violations) == 1
    assert violations[0]["event"].payload["value"] == 150.0
    assert violations[0]["event"].payload["threshold"] == 100.0


@pytest.mark.asyncio
async def test_ingest_publishes_twin_state_updated_event():
    """Successful ingestion must publish TWIN_STATE_UPDATED event."""
    tm = MockTwinManager()
    eb = MockEventBus()
    pipeline = DataPipeline(twin_manager=tm, event_bus=eb)

    connector = MockConnector({"press_01": 101.3})
    pipeline.register_connector("mqtt-1", connector)
    pipeline.register_mapping("press_01", "asset-line-3", "pressure")

    event = _make_read_event(["press_01"], "mqtt-1")
    await pipeline._handle_connector_read(event)
    await asyncio.sleep(0.01)

    twin_events = [p for p in eb.published if p["topic"] == EventTopic.TWIN_STATE_UPDATED]
    assert len(twin_events) == 1
    assert twin_events[0]["event"].payload["asset_id"] == "asset-line-3"
    assert twin_events[0]["event"].payload["field"] == "pressure"
    assert twin_events[0]["event"].payload["value"] == 101.3


@pytest.mark.asyncio
async def test_background_loop_starts_and_stops():
    """start_background_loop and stop_background_loop must manage the task."""
    tm = MockTwinManager()
    eb = MockEventBus()
    pipeline = DataPipeline(twin_manager=tm, event_bus=eb)

    pipeline.start_background_loop(interval_seconds=0.1)
    assert pipeline._running is True
    assert pipeline._background_task is not None

    await asyncio.sleep(0.05)
    pipeline.stop_background_loop()
    assert pipeline._running is False


@pytest.mark.asyncio
async def test_ingest_records_audit_trail_with_source():
    """Each successful twin update must be recorded in the audit log with source."""
    tm = MockTwinManager()
    eb = MockEventBus()
    pipeline = DataPipeline(twin_manager=tm, event_bus=eb)

    connector = MockConnector({"vib_01": 0.5})
    pipeline.register_connector("modbus-1", connector)
    pipeline.register_mapping("vib_01", "asset-pump-1", "vibration")

    event = _make_read_event(["vib_01"], "modbus-1")
    await pipeline._handle_connector_read(event)

    audit = pipeline.get_audit_log()
    assert len(audit) == 1
    entry = audit[0]
    assert entry["asset_id"] == "asset-pump-1"
    assert entry["field"] == "vibration"
    assert entry["value"] == 0.5
    assert entry["source"]["connector_id"] == "modbus-1"
    assert entry["source"]["node_id"] == "vib_01"
