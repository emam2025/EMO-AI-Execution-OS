"""Tests for SQLiteEventStore Implementation.

Ref: P6.3 — EventStore Implementation
"""

import os
import time

import pytest

from core.runtime.events.store import SQLiteEventStore
from core.models.event import EventMetadata, EventTopic, ExecutionEvent


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test_events.db")


@pytest.fixture
def store(db_path):
    return SQLiteEventStore(db_path)


@pytest.fixture
def event():
    return ExecutionEvent(
        trace_id="trace-001",
        topic=EventTopic.NODE_STARTED,
        payload={"node": "A"},
    )


def test_append_and_replay(store, event):
    """Append an event and replay it."""
    store.append(event)
    results = store.replay(EventTopic.NODE_STARTED)
    assert len(results) == 1
    assert results[0].trace_id == "trace-001"
    assert results[0].payload == {"node": "A"}


def test_append_is_idempotent_on_event_id(store, event):
    """Appending same event_id raises UNIQUE constraint error."""
    store.append(event)
    with pytest.raises(Exception):
        store.append(event)


def test_replay_with_time_window(store):
    """Replay with start_time and end_time filters."""
    from datetime import datetime, timedelta, timezone

    base_time = datetime.now(timezone.utc)

    event1 = ExecutionEvent(
        trace_id="t1",
        topic=EventTopic.NODE_STARTED,
        timestamp=base_time - timedelta(hours=1),
        payload={"step": 1},
    )
    event2 = ExecutionEvent(
        trace_id="t2",
        topic=EventTopic.NODE_STARTED,
        timestamp=base_time,
        payload={"step": 2},
    )
    event3 = ExecutionEvent(
        trace_id="t3",
        topic=EventTopic.NODE_STARTED,
        timestamp=base_time + timedelta(hours=1),
        payload={"step": 3},
    )

    store.append(event1)
    store.append(event2)
    store.append(event3)

    start_t = (base_time - timedelta(minutes=30)).timestamp()
    end_t = (base_time + timedelta(minutes=30)).timestamp()

    results = store.replay(EventTopic.NODE_STARTED, start_time=start_t, end_time=end_t)
    assert len(results) == 1
    assert results[0].trace_id == "t2"


def test_replay_with_limit(store):
    """Replay with limit returns only N events."""
    for i in range(5):
        store.append(
            ExecutionEvent(trace_id=f"t{i}", topic=EventTopic.NODE_COMPLETED, payload={})
        )

    results = store.replay(EventTopic.NODE_COMPLETED, limit=3)
    assert len(results) == 3


def test_get_latest_orders_descending(store):
    """get_latest returns most recent events first (descending)."""
    for i in range(3):
        store.append(
            ExecutionEvent(trace_id=f"t{i}", topic=EventTopic.STATE_TRANSITION, payload={})
        )

    results = store.get_latest(EventTopic.STATE_TRANSITION, limit=10)
    assert len(results) == 3
    assert results[0].trace_id == "t2"
    assert results[1].trace_id == "t1"
    assert results[2].trace_id == "t0"


def test_trace_id_preserved(store):
    """trace_id is preserved through append and replay."""
    event = ExecutionEvent(
        trace_id="trace-xyz-123",
        topic=EventTopic.AGENT_STATE_CHANGED,
        payload={},
    )
    store.append(event)

    results = store.replay(EventTopic.AGENT_STATE_CHANGED)
    assert results[0].trace_id == "trace-xyz-123"


def test_metadata_serialization(store):
    """Metadata is serialized and deserialized correctly."""
    meta = EventMetadata(source="scheduler", worker_id="w-1", custom_tags={"env": "prod"})
    event = ExecutionEvent(
        trace_id="t-meta",
        topic=EventTopic.POLICY_EVALUATED,
        payload={},
        metadata=meta,
    )
    store.append(event)

    results = store.replay(EventTopic.POLICY_EVALUATED)
    assert results[0].metadata.source == "scheduler"
    assert results[0].metadata.worker_id == "w-1"
    assert results[0].metadata.custom_tags["env"] == "prod"


def test_empty_replay_returns_empty_list(store):
    """Replay on empty store returns empty list."""
    results = store.replay(EventTopic.NODE_FAILED)
    assert results == []


def test_wal_mode_enabled(db_path):
    """WAL mode is enabled in the database."""
    store = SQLiteEventStore(db_path)
    import sqlite3

    with sqlite3.connect(db_path) as conn:
        result = conn.execute("PRAGMA journal_mode").fetchone()
        assert result[0] == "wal"


def test_multiple_topics_isolation(store):
    """Events from different topics are isolated."""
    store.append(ExecutionEvent(trace_id="t1", topic=EventTopic.NODE_STARTED, payload={}))
    store.append(ExecutionEvent(trace_id="t2", topic=EventTopic.NODE_COMPLETED, payload={}))
    store.append(ExecutionEvent(trace_id="t3", topic=EventTopic.NODE_STARTED, payload={}))

    started = store.replay(EventTopic.NODE_STARTED)
    completed = store.replay(EventTopic.NODE_COMPLETED)

    assert len(started) == 2
    assert len(completed) == 1
    assert completed[0].trace_id == "t2"
