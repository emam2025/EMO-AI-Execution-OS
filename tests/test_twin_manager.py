"""Tests for TwinManager Implementation.

Ref: RC16.9.3 — TwinManager Implementation
"""

import pytest

from core.industrial.twin_manager import TwinManager
from core.models.industrial import OperationalEvent, EventSeverity


@pytest.fixture
def manager():
    return TwinManager()


@pytest.fixture
def asset_id():
    return "machine-001"


def test_get_twin_state_initial(manager, asset_id):
    """Test getting initial twin state (empty)."""
    state = manager.get_twin_state(asset_id)
    assert state.asset_id == asset_id
    assert state.state == {}
    assert state.version == 1


def test_update_twin_state(manager, asset_id):
    """Test updating twin state."""
    state = manager.update_twin_state(asset_id, {"temperature": 75.0, "status": "running"})
    assert state.state["temperature"] == 75.0
    assert state.state["status"] == "running"
    assert state.version == 2
    assert state.last_updated is not None


def test_update_twin_state_multiple(manager, asset_id):
    """Test multiple state updates increment version."""
    manager.update_twin_state(asset_id, {"temp": 70})
    manager.update_twin_state(asset_id, {"temp": 75})
    manager.update_twin_state(asset_id, {"temp": 80})

    state = manager.get_twin_state(asset_id)
    assert state.version == 4  # 1 (initial) + 3 updates
    assert state.state["temp"] == 80


def test_simulate(manager, asset_id):
    """Test simulation scenario."""
    manager.update_twin_state(asset_id, {"temperature": 75.0, "status": "running"})

    result = manager.simulate(asset_id, {
        "state_changes": {"temperature": 90.0},
        "expected_outcome": "overheating"
    })

    assert result["simulation_id"] is not None
    assert result["asset_id"] == asset_id
    assert result["result"]["simulated_state"]["temperature"] == 90.0
    assert result["result"]["predicted_outcome"] == "overheating"
    assert result["timestamp"] is not None


def test_record_event(manager, asset_id):
    """Test recording operational event."""
    event = OperationalEvent(
        id="event-001",
        asset_id=asset_id,
        event_type="temperature_alert",
        severity=EventSeverity.WARNING,
        data={"temperature": 85.5}
    )

    manager.record_event(asset_id, event)

    events = manager.get_events(asset_id)
    assert len(events) == 1
    assert events[0].event_type == "temperature_alert"
    assert events[0].severity == EventSeverity.WARNING


def test_get_events_with_limit(manager, asset_id):
    """Test getting events with limit."""
    for i in range(5):
        event = OperationalEvent(
            id=f"event-{i}",
            asset_id=asset_id,
            event_type="test",
            severity=EventSeverity.INFO
        )
        manager.record_event(asset_id, event)

    events = manager.get_events(asset_id, limit=3)
    assert len(events) == 3
    assert events[0].id == "event-2"  # Last 3 events


def test_get_events_empty(manager, asset_id):
    """Test getting events when none exist."""
    events = manager.get_events(asset_id)
    assert len(events) == 0


def test_clear_state(manager, asset_id):
    """Test clearing twin state and events."""
    manager.update_twin_state(asset_id, {"temp": 75})
    event = OperationalEvent(
        id="event-001",
        asset_id=asset_id,
        event_type="test",
        severity=EventSeverity.INFO
    )
    manager.record_event(asset_id, event)

    result = manager.clear_state(asset_id)
    assert result is True

    # State should be reset
    state = manager.get_twin_state(asset_id)
    assert state.state == {}
    assert state.version == 1

    # Events should be cleared
    events = manager.get_events(asset_id)
    assert len(events) == 0


def test_simulate_nonexistent_asset(manager):
    """Test simulation without asset_manager (no validation)."""
    # Without asset_manager, simulation should still work
    result = manager.simulate("nonexistent", {"state_changes": {"temp": 90}})
    assert result["asset_id"] == "nonexistent"
    assert result["result"]["simulated_state"]["temp"] == 90


def test_multiple_assets(manager):
    """Test managing multiple twins independently."""
    manager.update_twin_state("asset-1", {"temp": 70})
    manager.update_twin_state("asset-2", {"temp": 80})

    state1 = manager.get_twin_state("asset-1")
    state2 = manager.get_twin_state("asset-2")

    assert state1.state["temp"] == 70
    assert state2.state["temp"] == 80
    assert state1.version == 2
    assert state2.version == 2


# ── Test Event Publishing ─────────────────────────────────────────────


class MockEventBus:
    """Mock IEventBus for testing event publishing."""

    def __init__(self):
        self.published = []

    async def publish(self, topic, event):
        self.published.append({"topic": topic, "event": event})

    def subscribe(self, topic, handler):
        return "mock-sub-id"

    def unsubscribe(self, subscription_id):
        pass


@pytest.mark.asyncio
async def test_publish_event_on_update():
    """Publish event when twin state is updated."""
    from core.models.event import EventTopic
    import asyncio

    event_bus = MockEventBus()
    manager = TwinManager(event_bus=event_bus)
    state = manager.update_twin_state("machine-001", {"temp": 75})

    assert state.state["temp"] == 75
    await asyncio.sleep(0.01)
    assert len(event_bus.published) == 1
    assert event_bus.published[0]["topic"] == EventTopic.TWIN_STATE_UPDATED


@pytest.mark.asyncio
async def test_no_event_bus_still_works():
    """TwinManager works without event_bus."""
    manager = TwinManager(event_bus=None)
    state = manager.update_twin_state("machine-001", {"temp": 75})
    assert state.state["temp"] == 75
