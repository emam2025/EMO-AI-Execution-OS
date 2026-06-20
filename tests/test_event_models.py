"""Tests for Event Domain Models and EventBus Protocol.

Ref: P6.1 — Event Domain Models & EventBus Protocol
"""

import pytest

from core.models.event import EventMetadata, EventTopic, ExecutionEvent
from core.interfaces.event_bus import IEventBus


class TestEventTopic:
    def test_event_topic_values(self):
        assert EventTopic.NODE_STARTED.value == "node_started"
        assert EventTopic.NODE_COMPLETED.value == "node_completed"
        assert EventTopic.STATE_TRANSITION.value == "state_transition"
        assert EventTopic.ARCHITECTURE_DRIFT.value == "architecture_drift"

    def test_event_topic_member_count(self):
        assert len(EventTopic.__members__) >= 8


class TestEventMetadata:
    def test_create_metadata_minimal(self):
        meta = EventMetadata(source="test")
        assert meta.source == "test"
        assert meta.worker_id is None
        assert meta.custom_tags == {}

    def test_create_metadata_full(self):
        meta = EventMetadata(
            source="agent",
            worker_id="w-001",
            custom_tags={"env": "prod", "region": "us-east"},
        )
        assert meta.source == "agent"
        assert meta.worker_id == "w-001"
        assert meta.custom_tags["env"] == "prod"

    def test_metadata_is_frozen(self):
        meta = EventMetadata(source="test")
        with pytest.raises(AttributeError):
            meta.source = "other"


class TestExecutionEvent:
    def test_create_event_defaults(self):
        event = ExecutionEvent()
        assert event.event_id is not None
        assert event.topic == EventTopic.NODE_STARTED
        assert event.trace_id == ""
        assert event.metadata is None

    def test_create_event_with_trace_id(self):
        event = ExecutionEvent(
            trace_id="trace-abc-123",
            topic=EventTopic.NODE_COMPLETED,
            payload={"node": "A", "duration_ms": 42},
        )
        assert event.trace_id == "trace-abc-123"
        assert event.topic == EventTopic.NODE_COMPLETED
        assert event.payload["node"] == "A"

    def test_create_event_with_metadata(self):
        meta = EventMetadata(source="scheduler", worker_id="w-1")
        event = ExecutionEvent(
            trace_id="t-1",
            topic=EventTopic.STATE_TRANSITION,
            metadata=meta,
        )
        assert event.metadata.source == "scheduler"
        assert event.metadata.worker_id == "w-1"

    def test_event_is_frozen(self):
        event = ExecutionEvent(trace_id="t-1")
        with pytest.raises(AttributeError):
            event.trace_id = "t-2"

    def test_event_has_timestamp(self):
        event = ExecutionEvent()
        assert event.timestamp is not None
        assert event.timestamp.tzinfo is not None


class TestEventBusProtocol:
    def test_protocol_exists(self):
        assert hasattr(IEventBus, "publish")
        assert hasattr(IEventBus, "subscribe")
        assert hasattr(IEventBus, "unsubscribe")

    def test_protocol_signature_publish(self):
        import inspect
        sig = inspect.signature(IEventBus.publish)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "topic" in params
        assert "event" in params

    def test_protocol_signature_subscribe(self):
        import inspect
        sig = inspect.signature(IEventBus.subscribe)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "topic" in params
        assert "handler" in params

    def test_protocol_signature_unsubscribe(self):
        import inspect
        sig = inspect.signature(IEventBus.unsubscribe)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "subscription_id" in params
