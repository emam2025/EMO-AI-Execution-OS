"""Tests for InMemoryEventBus Implementation.

Ref: P6.2 — InMemoryEventBus Implementation
"""

import asyncio

import pytest

from core.runtime.events.memory_bus import InMemoryEventBus
from core.models.event import EventTopic, ExecutionEvent


@pytest.fixture
def bus():
    return InMemoryEventBus()


@pytest.fixture
def event():
    return ExecutionEvent(
        trace_id="test-trace",
        topic=EventTopic.NODE_STARTED,
        payload={"node": "A"},
    )


@pytest.mark.asyncio
async def test_publish_no_subscribers(bus, event):
    """Publishing with no subscribers should not raise."""
    await bus.publish(EventTopic.NODE_STARTED, event)


@pytest.mark.asyncio
async def test_subscribe_and_publish(bus, event):
    """Subscribe and receive event."""
    received = []

    async def handler(e):
        received.append(e)

    bus.subscribe(EventTopic.NODE_STARTED, handler)
    await bus.publish(EventTopic.NODE_STARTED, event)

    assert len(received) == 1
    assert received[0].trace_id == "test-trace"


@pytest.mark.asyncio
async def test_multiple_subscribers(bus, event):
    """Multiple subscribers receive the same event."""
    received1 = []
    received2 = []

    async def handler1(e):
        received1.append(e)

    async def handler2(e):
        received2.append(e)

    bus.subscribe(EventTopic.NODE_STARTED, handler1)
    bus.subscribe(EventTopic.NODE_STARTED, handler2)
    await bus.publish(EventTopic.NODE_STARTED, event)

    assert len(received1) == 1
    assert len(received2) == 1


@pytest.mark.asyncio
async def test_topic_routing(bus, event):
    """Events are routed only to subscribers of the correct topic."""
    received_started = []
    received_completed = []

    async def handler_started(e):
        received_started.append(e)

    async def handler_completed(e):
        received_completed.append(e)

    bus.subscribe(EventTopic.NODE_STARTED, handler_started)
    bus.subscribe(EventTopic.NODE_COMPLETED, handler_completed)

    await bus.publish(EventTopic.NODE_STARTED, event)

    assert len(received_started) == 1
    assert len(received_completed) == 0


@pytest.mark.asyncio
async def test_unsubscribe(bus, event):
    """Unsubscribe stops receiving events."""
    received = []

    async def handler(e):
        received.append(e)

    sub_id = bus.subscribe(EventTopic.NODE_STARTED, handler)
    await bus.publish(EventTopic.NODE_STARTED, event)
    assert len(received) == 1

    bus.unsubscribe(sub_id)
    await bus.publish(EventTopic.NODE_STARTED, event)
    assert len(received) == 1


@pytest.mark.asyncio
async def test_unsubscribe_nonexistent(bus):
    """Unsubscribing non-existent ID should not raise."""
    bus.unsubscribe("nonexistent-id")


@pytest.mark.asyncio
async def test_multiple_events(bus):
    """Multiple events are delivered in order."""
    received = []

    async def handler(e):
        received.append(e.trace_id)

    bus.subscribe(EventTopic.NODE_STARTED, handler)

    for i in range(3):
        event = ExecutionEvent(trace_id=f"trace-{i}", topic=EventTopic.NODE_STARTED)
        await bus.publish(EventTopic.NODE_STARTED, event)

    assert received == ["trace-0", "trace-1", "trace-2"]


@pytest.mark.asyncio
async def test_handler_exception_does_not_break_bus(bus, event):
    """Handler exception should not prevent other handlers from running."""
    received = []

    async def bad_handler(e):
        raise ValueError("Handler error")

    async def good_handler(e):
        received.append(e)

    bus.subscribe(EventTopic.NODE_STARTED, bad_handler)
    bus.subscribe(EventTopic.NODE_STARTED, good_handler)

    await bus.publish(EventTopic.NODE_STARTED, event)

    assert len(received) == 1


@pytest.mark.asyncio
async def test_subscribe_returns_unique_ids(bus):
    """Each subscribe call returns a unique subscription_id."""
    async def handler(e):
        pass

    id1 = bus.subscribe(EventTopic.NODE_STARTED, handler)
    id2 = bus.subscribe(EventTopic.NODE_STARTED, handler)

    assert id1 != id2


@pytest.mark.asyncio
async def test_different_topics_independent(bus):
    """Different topics have independent subscriber lists."""
    received_started = []
    received_completed = []

    async def handler_started(e):
        received_started.append(e)

    async def handler_completed(e):
        received_completed.append(e)

    sub1 = bus.subscribe(EventTopic.NODE_STARTED, handler_started)
    sub2 = bus.subscribe(EventTopic.NODE_COMPLETED, handler_completed)

    bus.unsubscribe(sub1)

    event_started = ExecutionEvent(trace_id="t1", topic=EventTopic.NODE_STARTED)
    event_completed = ExecutionEvent(trace_id="t2", topic=EventTopic.NODE_COMPLETED)

    await bus.publish(EventTopic.NODE_STARTED, event_started)
    await bus.publish(EventTopic.NODE_COMPLETED, event_completed)

    assert len(received_started) == 0
    assert len(received_completed) == 1


@pytest.mark.asyncio
async def test_concurrent_publish(bus):
    """Concurrent publishes should not corrupt state."""
    received = []

    async def handler(e):
        received.append(e.trace_id)

    bus.subscribe(EventTopic.NODE_STARTED, handler)

    async def publish_event(i):
        event = ExecutionEvent(trace_id=f"trace-{i}", topic=EventTopic.NODE_STARTED)
        await bus.publish(EventTopic.NODE_STARTED, event)

    await asyncio.gather(*[publish_event(i) for i in range(10)])

    assert len(received) == 10


@pytest.mark.asyncio
async def test_empty_topic_cleanup(bus, event):
    """Empty topics are cleaned up after unsubscribe."""
    async def handler(e):
        pass

    sub_id = bus.subscribe(EventTopic.NODE_STARTED, handler)
    bus.unsubscribe(sub_id)

    assert "node_started" not in bus._subscribers


@pytest.mark.asyncio
async def test_handler_receives_correct_event(bus):
    """Handler receives the exact event published."""
    received = []

    async def handler(e):
        received.append(e)

    bus.subscribe(EventTopic.STATE_TRANSITION, handler)

    event = ExecutionEvent(
        trace_id="trace-xyz",
        topic=EventTopic.STATE_TRANSITION,
        payload={"from": "PENDING", "to": "RUNNING"},
    )

    await bus.publish(EventTopic.STATE_TRANSITION, event)

    assert len(received) == 1
    assert received[0].trace_id == "trace-xyz"
    assert received[0].payload["from"] == "PENDING"


@pytest.mark.asyncio
async def test_subscribe_same_handler_twice(bus, event):
    """Subscribing the same handler twice should create two subscriptions."""
    received = []

    async def handler(e):
        received.append(e)

    sub1 = bus.subscribe(EventTopic.NODE_STARTED, handler)
    sub2 = bus.subscribe(EventTopic.NODE_STARTED, handler)

    await bus.publish(EventTopic.NODE_STARTED, event)

    assert len(received) == 2

    bus.unsubscribe(sub1)
    await bus.publish(EventTopic.NODE_STARTED, event)

    assert len(received) == 3


@pytest.mark.asyncio
async def test_publish_with_no_subscribers_for_topic(bus, event):
    """Publishing to a topic with no subscribers should not raise."""
    await bus.publish(EventTopic.ARCHITECTURE_DRIFT, event)
