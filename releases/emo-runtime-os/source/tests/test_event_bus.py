"""Tests for Phase 3.5 Runtime Event Model — EventBus + EventStore."""

import os
import sys
import tempfile
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.models.events import ExecutionEvent, make_trace_id
from core.runtime.event_bus import InMemoryEventBus
from core.runtime.event_store import EventStore


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def event_bus():
    return InMemoryEventBus()


@pytest.fixture
def sample_event():
    return ExecutionEvent(
        event_id="evt-001",
        event_type="NODE_STARTED",
        timestamp=time.time(),
        source="test_module",
        payload={"node_id": "n1", "dag_id": "dag-1"},
        trace_id=make_trace_id(),
        session_id="session-1",
    )


# ── InMemoryEventBus Tests ───────────────────────────────────────────────────

class TestInMemoryEventBus:

    def test_publish_and_subscribe(self, event_bus, sample_event):
        received = []

        def handler(event):
            received.append(event)

        event_bus.subscribe("execution", handler)
        event_bus.publish("execution", sample_event)

        assert len(received) == 1
        assert received[0].event_id == "evt-001"

    def test_multiple_subscribers(self, event_bus, sample_event):
        received_1 = []
        received_2 = []

        def handler_1(event):
            received_1.append(event)

        def handler_2(event):
            received_2.append(event)

        event_bus.subscribe("execution", handler_1)
        event_bus.subscribe("execution", handler_2)
        event_bus.publish("execution", sample_event)

        assert len(received_1) == 1
        assert len(received_2) == 1

    def test_unsubscribe(self, event_bus, sample_event):
        received = []

        def handler(event):
            received.append(event)

        event_bus.subscribe("execution", handler)
        event_bus.unsubscribe("execution", handler)
        event_bus.publish("execution", sample_event)

        assert len(received) == 0

    def test_topic_isolation(self, event_bus, sample_event):
        received_a = []
        received_b = []

        def handler_a(event):
            received_a.append(event)

        def handler_b(event):
            received_b.append(event)

        event_bus.subscribe("topic_a", handler_a)
        event_bus.subscribe("topic_b", handler_b)
        event_bus.publish("topic_a", sample_event)

        assert len(received_a) == 1
        assert len(received_b) == 0

    def test_get_events(self, event_bus, sample_event):
        event_bus.publish("execution", sample_event)
        events = event_bus.get_events("execution")
        assert len(events) == 1
        assert events[0].event_id == "evt-001"

    def test_get_all_events(self, event_bus, sample_event):
        ev2 = ExecutionEvent(
            event_id="evt-002",
            event_type="NODE_COMPLETED",
            timestamp=time.time(),
            source="test",
        )
        event_bus.publish("execution", sample_event)
        event_bus.publish("governance", ev2)

        all_events = event_bus.get_all_events()
        assert len(all_events) == 2

    def test_get_events_limit(self, event_bus):
        for i in range(10):
            event = ExecutionEvent(
                event_id=f"evt-{i:03d}",
                event_type="NODE_STARTED",
                timestamp=time.time(),
                source="test",
            )
            event_bus.publish("execution", event)

        events = event_bus.get_events("execution", limit=3)
        assert len(events) == 3
        assert events[-1].event_id == "evt-009"

    def test_clear(self, event_bus, sample_event):
        event_bus.publish("execution", sample_event)
        event_bus.clear()
        assert len(event_bus.get_all_events()) == 0

    def test_duplicate_subscription(self, event_bus, sample_event):
        received = []

        def handler(event):
            received.append(event)

        event_bus.subscribe("execution", handler)
        event_bus.subscribe("execution", handler)
        event_bus.publish("execution", sample_event)

        assert len(received) == 1

    def test_publish_no_subscribers(self, event_bus, sample_event):
        event_bus.publish("orphan_topic", sample_event)
        events = event_bus.get_events("orphan_topic")
        assert len(events) == 1


# ── EventStore Tests ─────────────────────────────────────────────────────────

class TestEventStore:

    @pytest.fixture
    def temp_store(self):
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
            path = f.name
        store = EventStore(path=path)
        yield store
        if os.path.exists(path):
            os.remove(path)

    def test_append_and_replay(self, temp_store):
        event = ExecutionEvent(
            event_id="evt-001",
            event_type="NODE_STARTED",
            timestamp=1000.0,
            source="test",
            payload={"key": "value"},
            trace_id="trace-1",
            session_id="session-1",
        )
        temp_store.append(event)
        events = temp_store.replay()
        assert len(events) == 1
        assert events[0].event_id == "evt-001"
        assert events[0].payload["key"] == "value"

    def test_replay_empty(self, temp_store):
        events = temp_store.replay()
        assert events == []

    def test_replay_by_session(self, temp_store):
        for i in range(3):
            event = ExecutionEvent(
                event_id=f"evt-{i:03d}",
                event_type="NODE_STARTED",
                timestamp=1000.0 + i,
                source="test",
                session_id="session-1",
            )
            temp_store.append(event)

        event_other = ExecutionEvent(
            event_id="evt-other",
            event_type="NODE_STARTED",
            timestamp=2000.0,
            source="test",
            session_id="session-2",
        )
        temp_store.append(event_other)

        s1 = temp_store.replay(session_id="session-1")
        assert len(s1) == 3

        s2 = temp_store.replay(session_id="session-2")
        assert len(s2) == 1

    def test_clear(self, temp_store):
        event = ExecutionEvent(
            event_id="evt-001",
            event_type="NODE_STARTED",
            timestamp=1000.0,
            source="test",
        )
        temp_store.append(event)
        temp_store.clear()
        events = temp_store.replay()
        assert events == []

    def test_persistence_across_instances(self, temp_store):
        event = ExecutionEvent(
            event_id="evt-persist",
            event_type="NODE_COMPLETED",
            timestamp=5000.0,
            source="test",
        )
        temp_store.append(event)

        store2 = EventStore(path=temp_store._path)
        events = store2.replay()
        assert len(events) == 1
        assert events[0].event_id == "evt-persist"

    def test_multiple_events_order(self, temp_store):
        for i in range(5):
            event = ExecutionEvent(
                event_id=f"evt-{i:03d}",
                event_type="STATE_TRANSITION",
                timestamp=float(i),
                source="test",
            )
            temp_store.append(event)

        events = temp_store.replay()
        assert [e.event_id for e in events] == [
            "evt-000", "evt-001", "evt-002", "evt-003", "evt-004"
        ]
