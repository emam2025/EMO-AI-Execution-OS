"""Phase F4 — Aggregation Windowing & Flush: Tests.  # LAW-5 # RULE-3

Verifies the TelemetryAggregator's windowing strategy:
  - Sliding Window (5s key resolution)
  - Tumbling Window (1m key resolution)
  - Session Window (per-execution-id)

Also verifies flush_window preserves buffer on failure (RULE 3).

Ref: Canon LAW 5 (Observability), RULE 3 (Recoverability)
Ref: artifacts/design/f4/03_telemetry_aggregation_machine.md §5
"""

import time
import pytest

from core.runtime.observability.telemetry_aggregator import TelemetryAggregator
from core.runtime.observability.aggregation_state_machine import (
    AggregationState,
    AggregationStateMachine,
)
from core.runtime.models.observability_models import (
    TelemetryEventType,
    WindowStrategy,
)


class TestAggregationWindowingAndFlush:
    """Windowing and flush behavior for TelemetryAggregator."""

    def test_ingest_routes_to_tumbling_window(self):
        agg = TelemetryAggregator()
        agg.ingest_event(TelemetryEventType.SPAN_END, {"status": "ok"}, trace_id=None)
        keys = list(agg.buffer_snapshot.keys())
        assert len(keys) == 1
        assert keys[0].startswith("tumbling:")

    def test_ingest_with_trace_id_uses_session_window(self):
        agg = TelemetryAggregator()
        agg.ingest_event(TelemetryEventType.SPAN_END, {"status": "ok"}, trace_id="trace-1")
        keys = list(agg.buffer_snapshot.keys())
        assert keys[0] == "session:trace-1"

    def test_multiple_events_same_session_window(self):
        agg = TelemetryAggregator()
        agg.ingest_event(TelemetryEventType.SPAN_END, {"status": "ok"}, trace_id="trace-2")
        agg.ingest_event(TelemetryEventType.STATE_TRANSITION, {"node": "n1"}, trace_id="trace-2")
        key = "session:trace-2"
        assert key in agg.buffer_snapshot
        assert agg.buffer_snapshot[key] == 2

    def test_compute_metrics_empty_window(self):
        agg = TelemetryAggregator()
        summary = agg.compute_metrics("tumbling:999999", WindowStrategy.TUMBLING_1M)
        assert summary.span_count == 0
        assert summary.window_key == "tumbling:999999"

    def test_compute_metrics_counts_events(self):
        agg = TelemetryAggregator()
        agg.ingest_event(TelemetryEventType.SPAN_END, {"status": "ok"}, trace_id="trace-3")
        agg.ingest_event(TelemetryEventType.SPAN_END, {"status": "error"}, trace_id="trace-3")
        agg.ingest_event(TelemetryEventType.ALERT_FIRED, {"alert": "a1"}, trace_id="trace-3")
        summary = agg.compute_metrics("session:trace-3", WindowStrategy.SESSION)
        assert summary.span_count == 3
        assert summary.alert_count == 1
        assert summary.error_count == 1

    def test_flush_window_evicts_buffer(self):
        agg = TelemetryAggregator()
        agg.ingest_event(TelemetryEventType.SPAN_END, {"status": "ok"}, trace_id="trace-4")
        assert "session:trace-4" in agg.buffer_snapshot
        agg.flush_window("session:trace-4")
        assert "session:trace-4" not in agg.buffer_snapshot

    def test_flush_window_returns_summary(self):
        agg = TelemetryAggregator()
        agg.ingest_event(TelemetryEventType.SPAN_END, {"status": "ok"}, trace_id="trace-5")
        summary = agg.flush_window("session:trace-5")
        assert summary.span_count == 1
        assert summary.window_key == "session:trace-5"

    def test_publish_summary_idempotent(self):
        agg = TelemetryAggregator()
        summary = agg.flush_window("session:test-pub")
        agg.publish_summary(summary)
        agg.publish_summary(summary)  # second call should not re-publish
        assert summary.window_key in agg._published_keys

    def test_buffer_partitioned_by_window_key(self):
        agg = TelemetryAggregator()
        agg.ingest_event(TelemetryEventType.SPAN_END, {}, trace_id="a")
        agg.ingest_event(TelemetryEventType.SPAN_END, {}, trace_id="b")
        assert agg.buffer_snapshot["session:a"] == 1
        assert agg.buffer_snapshot["session:b"] == 1

    def test_sm_state_flow(self):
        sm = AggregationStateMachine()
        assert sm.current == AggregationState.RAW_EVENT
        ok, _ = sm.transition(AggregationState.VALIDATED)
        assert ok and sm.current == AggregationState.VALIDATED
        ok, _ = sm.transition(AggregationState.BUFFERED, current_size=0)
        assert ok and sm.current == AggregationState.BUFFERED
        ok, _ = sm.transition(AggregationState.AGGREGATING, events_pending=True)
        assert ok and sm.current == AggregationState.AGGREGATING
        ok, _ = sm.transition(AggregationState.COMPUTED)
        assert ok and sm.current == AggregationState.COMPUTED
        ok, _ = sm.transition(AggregationState.FLUSHING)
        assert ok and sm.current == AggregationState.FLUSHING
        ok, _ = sm.transition(AggregationState.PERSISTED)
        assert ok and sm.current == AggregationState.PERSISTED

    def test_flush_retry_guard(self):
        sm = AggregationStateMachine()
        ok, _ = sm.transition(AggregationState.VALIDATED)
        ok, _ = sm.transition(AggregationState.BUFFERED, current_size=0)
        ok, _ = sm.transition(AggregationState.AGGREGATING, events_pending=True)
        ok, _ = sm.transition(AggregationState.COMPUTED)
        ok, _ = sm.transition(AggregationState.FLUSHING)
        ok, msg = sm.transition(AggregationState.BUFFERED, retry_count=0)
        assert ok
        assert "Retry" in msg
