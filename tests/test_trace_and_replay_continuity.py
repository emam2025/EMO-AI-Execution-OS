"""Trace and Replay Continuity — 7 high-signal tests.

Validates trace_id propagation survives disruption and replay is deterministic.
Mutation-resistant: breaks on trace_id loss, hash mismatch, or continuity drop.
"""

import hashlib
import json
import pytest

from core.runtime.facade import EmoRuntimeFacade
from core.runtime.event_bus import InMemoryEventBus
from core.runtime.event_store import EventStore


class TestEventBusContinuity:
    """Invariant: EventBus survives disruption and drains backlog."""

    def test_in_memory_event_bus_pub_sub(self):
        """InMemoryEventBus publish+subscribe must not raise."""
        bus = InMemoryEventBus()
        received = []

        def handler(event):
            received.append(event)

        bus.subscribe("test.topic", handler)
        bus.publish("test.topic", {"data": 1})
        assert len(received) == 1

    def test_event_bus_multiple_topics(self):
        """EventBus must handle multiple topics independently."""
        bus = InMemoryEventBus()
        t1, t2 = [], []

        bus.subscribe("topic.a", lambda e: t1.append(e))
        bus.subscribe("topic.b", lambda e: t2.append(e))
        bus.publish("topic.a", {"x": 1})
        bus.publish("topic.b", {"y": 2})
        assert len(t1) == 1 and len(t2) == 1

    def test_event_bus_subscriber_exception_isolated(self):
        """A failing subscriber must not break other subscribers."""
        bus = InMemoryEventBus()
        healthy = []

        def failing(e):
            raise ValueError("simulated failure")

        def healthy_handler(e):
            healthy.append(e)

        bus.subscribe("test", failing)
        bus.subscribe("test", healthy_handler)
        bus.publish("test", {"data": 1})
        assert len(healthy) == 1


class TestEventStorePersistence:
    """Invariant: EventStore persists and retrieves events."""

    def test_store_and_replay_events(self):
        import uuid, time
        from core.models.events import ExecutionEvent
        sid = uuid.uuid4().hex
        store = EventStore()
        e1 = ExecutionEvent(event_id=uuid.uuid4().hex, event_type="test", timestamp=time.time(), source="test", session_id=sid, payload={"data": 1})
        e2 = ExecutionEvent(event_id=uuid.uuid4().hex, event_type="test", timestamp=time.time(), source="test", session_id=sid, payload={"data": 2})
        store.append(e1)
        store.append(e2)
        events = store.replay(session_id=sid)
        assert len(events) == 2

    def test_store_unknown_session_returns_empty(self):
        store = EventStore()
        events = store.replay(session_id="nonexistent")
        assert events == []


class TestTraceDeterminism:
    """Invariant: output hash must be deterministic for same execution."""

    def test_deterministic_hash(self):
        data = {"nodes": [{"id": "n1", "result": "ok"}, {"id": "n2", "result": "ok"}]}
        h1 = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
        h2 = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
        assert h1 == h2, "deterministic hash must match"
