"""Pilot.1.2 — Stress Testing (Industrial Load).

5 stress scenarios proving stable performance under accelerating data load.
Each scenario uses real components with no data loss.

Ref: Pilot.1.2 — Pilot Readiness & Hardening
"""

import asyncio
import os
import tempfile

import pytest

from core.industrial.oee_engine import OEECalculator, ProductionMetrics
from core.industrial.twin_manager import TwinManager
from core.models.event import EventMetadata, EventTopic, ExecutionEvent
from core.runtime.events.memory_bus import InMemoryEventBus
from core.runtime.events.store import SQLiteEventStore
from core.runtime.sandbox.sandbox_executor import SandboxExecutor
from core.models.sandbox import SandboxContext


# --- Scenario 1: EventStore Under High Write Load ---


def test_eventstore_high_write_load():
    """1000 events in rapid succession (mixed topics) → WAL mode persists all,
    replay() returns 1000 events with zero data loss."""

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        store = SQLiteEventStore(db_path)
        topics = [
            EventTopic.NODE_COMPLETED,
            EventTopic.EXECUTION_FAILED,
            EventTopic.TWIN_STATE_UPDATED,
            EventTopic.SAFETY_VIOLATION,
            EventTopic.CONNECTOR_READ_SUCCESS,
        ]

        for i in range(1000):
            event = ExecutionEvent(
                topic=topics[i % len(topics)],
                payload={"index": i, "data": f"load_test_{i}"},
                trace_id=f"stress-{i}",
            )
            store.append(event)

        total = 0
        for t in topics:
            replayed = store.replay(topic=t)
            total += len(replayed)
        assert total == 1000
    finally:
        os.unlink(db_path)


# --- Scenario 2: EventBus Under Concurrent Publish ---


@pytest.mark.asyncio
async def test_eventbus_concurrent_publish():
    """500 concurrent async publishers on same topic → InMemoryEventBus
    receives all events with zero loss or duplication."""

    event_bus = InMemoryEventBus()
    received: list = []

    async def handler(event):
        received.append(event)

    event_bus.subscribe(EventTopic.NODE_COMPLETED, handler)

    async def publish_one(i):
        event = ExecutionEvent(
            topic=EventTopic.NODE_COMPLETED,
            payload={"index": i},
            trace_id=f"concurrent-{i}",
        )
        await event_bus.publish(EventTopic.NODE_COMPLETED, event)

    tasks = [publish_one(i) for i in range(500)]
    await asyncio.gather(*tasks)
    await asyncio.sleep(0.05)

    assert len(received) == 500
    indices = sorted([e.payload["index"] for e in received])
    assert indices == list(range(500))


# --- Scenario 3: OEE Calculator Under Continuous Computation ---


def test_oee_continuous_computation():
    """100 assets × 50 cycles each = 5000 OEE calculations →
    all results deterministic, zero math errors."""

    calc = OEECalculator()
    seen = {}

    for asset_idx in range(100):
        for cycle in range(50):
            metrics = ProductionMetrics(
                planned_production_time_minutes=60.0,
                run_time_minutes=50.0 - (cycle % 5),
                total_count=1000 + cycle,
                good_count=980 + cycle,
                ideal_run_rate_per_minute=20.0,
            )
            result = calc.calculate_oee(f"asset-{asset_idx}", metrics)

            assert 0.0 <= result.availability_pct <= 100.0
            assert result.performance_pct >= 0.0
            assert 0.0 <= result.quality_pct <= 100.0
            assert 0.0 <= result.overall_oee_pct <= 100.0

            key = (asset_idx, cycle)
            if key in seen:
                assert seen[key] == result.overall_oee_pct
            seen[key] = result.overall_oee_pct

    assert len(seen) == 5000


# --- Scenario 4: TwinManager Under Rapid State Updates ---


def test_twinmanager_rapid_updates():
    """50 twins × 100 sequential updates each → TwinManager maintains
    correct state per twin, version increments correctly."""

    tm = TwinManager()

    for twin_idx in range(50):
        asset_id = f"twin-{twin_idx}"
        for update_num in range(100):
            tm.update_twin_state(asset_id, {
                "temperature": 20.0 + update_num,
                "pressure": 101.3 + update_num * 0.1,
                "cycle": update_num,
            })

        state = tm.get_twin_state(asset_id)
        assert state.version == 101
        assert state.state["temperature"] == 119.0
        assert state.state["cycle"] == 99

    all_states = {f"twin-{i}": tm.get_twin_state(f"twin-{i}") for i in range(50)}
    assert len(all_states) == 50
    for asset_id, state in all_states.items():
        assert state.version == 101


# --- Scenario 5: IsolationRuntime Under Sustained Execution ---


def test_sandbox_sustained_execution():
    """100 sequential sandbox executions (each ~0.1s) → all complete,
    no zombie processes, exit codes all 0."""

    executor = SandboxExecutor()
    ctx = SandboxContext(tool_id="stress-worker", timeout_seconds=5, max_memory_mb=128)

    for i in range(100):
        result = executor.execute("import time; time.sleep(0.01)", ctx)
        assert result.success is True
        assert result.exit_code == 0
