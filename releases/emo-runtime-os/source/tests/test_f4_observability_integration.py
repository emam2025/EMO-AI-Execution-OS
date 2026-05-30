"""Phase F4 — Observability Layer: Comprehensive Integration Tests.  # LAW-5 # LAW-12

Groups:
  G1 — TestTraceCorrelation        (5 tests) — span lifecycle, parent_id, propagation
  G2 — TestWindowingAndFlush        (4 tests) — windowing, flush, publish
  G3 — TestBackpressureProtection   (4 tests) — adaptive sampling, CRITICAL protection
  G4 — TestAlertSuppression         (4 tests) — threshold, suppress, acknowledge
  G5 — TestEventBusPropagation      (3 tests) — EventBus wiring, timeline events
  G6 — TestCanonCompliance          (3 tests) — LAW/RULE comments, imports

Total: ~23 tests

Ref: Canon LAW 5 (Observability), LAW 12 (Traceability), RULE 1-5
Ref: DEVELOPER.md §15.13
Ref: EXEC-DIRECTIVE-006
"""

import time
from unittest.mock import MagicMock

import pytest

from core.runtime.observability.trace_collector import TraceCollector
from core.runtime.observability.telemetry_aggregator import TelemetryAggregator
from core.runtime.observability.dashboard_data_provider import DashboardDataProvider
from core.runtime.observability.alert_router import AlertRouter
from core.runtime.observability.aggregation_state_machine import (
    AggregationState,
    AggregationStateMachine,
)
from core.runtime.observability.backpressure_sampler import BackpressureSampler
from core.runtime.models.observability_models import (
    AggregatedMetric,
    AlertRule,
    AlertPayload,
    ExecutionTimelineEvent,
    FailureExplorerResult,
    NodeStateTransition,
    Severity,
    TelemetryEventType,
    TraceSpan,
    WorkerHealthStatus,
    WorkerTopologySnapshot,
)


# ════════════════════════════════════════════════════════════════════
# G1 — TestTraceCorrelation (5 tests)
# ════════════════════════════════════════════════════════════════════


class TestTraceCorrelation:
    """LAW 12: Every span carries trace_id and parent_id."""

    def test_start_span_returns_span_id(self):
        tc = TraceCollector()
        span_id = tc.start_span("worker.execute", trace_id="trace-1")
        assert span_id
        assert len(span_id) > 0

    def test_span_has_trace_id_and_parent_id(self):
        tc = TraceCollector()
        parent = tc.start_span("parent", trace_id="trace-2")
        child = tc.start_span("child", trace_id="trace-2", parent_id=parent)
        assert tc._active_spans[child].parent_id == parent
        assert tc._active_spans[child].trace_id == "trace-2"

    def test_end_span_moves_to_completed(self):
        tc = TraceCollector()
        sid = tc.start_span("op", trace_id="t1")
        tc.end_span(sid)
        assert len(tc.completed_spans) == 1
        assert tc.completed_spans[0].span_id == sid

    def test_add_attribute_to_active_span(self):
        tc = TraceCollector()
        sid = tc.start_span("op", trace_id="t1")
        tc.add_attribute(sid, "key1", "value1")
        assert tc._active_spans[sid].attributes["key1"] == "value1"

    def test_propagate_context_returns_headers(self):
        tc = TraceCollector()
        headers = tc.propagate_context("trace-3", "span-5", "f3_scheduler")
        assert headers["trace_id"] == "trace-3"
        assert headers["parent_span_id"] == "span-5"
        assert headers["target_domain"] == "f3_scheduler"


# ════════════════════════════════════════════════════════════════════
# G2 — TestWindowingAndFlush (4 tests)
# ════════════════════════════════════════════════════════════════════


class TestWindowingAndFlush:
    """Windowing strategy and flush lifecycle."""

    def test_ingest_buffers_events(self):
        agg = TelemetryAggregator()
        agg.ingest_event(TelemetryEventType.SPAN_END, {"status": "ok"})
        total = sum(agg.buffer_snapshot.values())
        assert total == 1

    def test_compute_metrics_aggregates_window(self):
        agg = TelemetryAggregator()
        agg.ingest_event(TelemetryEventType.SPAN_END, {"status": "ok"}, trace_id="t1")
        agg.ingest_event(TelemetryEventType.ALERT_FIRED, {"alert": "a1"}, trace_id="t1")
        summary = agg.compute_metrics("session:t1")
        assert summary.span_count == 2
        assert summary.alert_count == 1

    def test_flush_evicts_and_returns_summary(self):
        agg = TelemetryAggregator()
        agg.ingest_event(TelemetryEventType.SPAN_END, {}, trace_id="t2")
        summary = agg.flush_window("session:t2")
        assert summary.span_count == 1
        assert "session:t2" not in agg.buffer_snapshot

    def test_publish_summary_to_event_bus(self):
        agg = TelemetryAggregator()
        mock_publish = MagicMock()
        agg.ingest_event(TelemetryEventType.SPAN_END, {}, trace_id="t3")
        summary = agg.flush_window("session:t3")
        agg.publish_summary(summary, event_bus_publish=mock_publish)
        mock_publish.assert_called_once()


# ════════════════════════════════════════════════════════════════════
# G3 — TestBackpressureProtection (4 tests)
# ════════════════════════════════════════════════════════════════════


class TestBackpressureProtection:
    """LAW 5: CRITICAL spans never dropped under backpressure."""

    def test_critical_never_dropped_at_any_level(self):
        sampler = BackpressureSampler()
        for pct in [0.1, 0.5, 0.7, 0.9, 0.99]:
            sampler.adaptive_sampling(pct)
            for _ in range(50):
                assert sampler.should_sample(Severity.CRITICAL)
        assert sampler.dropped_critical == 0

    def test_debug_dropped_at_high_load(self):
        sampler = BackpressureSampler()
        sampler.adaptive_sampling(0.90)
        results = [sampler.should_sample(Severity.DEBUG) for _ in range(500)]
        assert sampler.dropped_count > 0

    def test_adaptive_sampling_changes_with_load(self):
        sampler = BackpressureSampler()
        low = sampler.adaptive_sampling(0.30)
        assert low["debug"] == 1.0
        high = sampler.adaptive_sampling(0.90)
        assert high["debug"] == 0.0

    def test_reset_restores_default_rates(self):
        sampler = BackpressureSampler()
        sampler.adaptive_sampling(0.99)
        sampler.should_sample(Severity.DEBUG)
        assert sampler.dropped_count > 0
        sampler.reset()
        assert sampler.dropped_count == 0
        assert sampler.sample_rates["debug"] == 0.50


# ════════════════════════════════════════════════════════════════════
# G4 — TestAlertSuppression (4 tests)
# ════════════════════════════════════════════════════════════════════


class TestAlertSuppression:
    """RULE 3: Duplicate suppression prevents alert storms."""

    def test_evaluate_threshold_gt(self):
        router = AlertRouter()
        metric = AggregatedMetric(metric_name="events", window_key="w1", count=100)
        rule = AlertRule(alert_id="a1", metric_name="events", operator="gt", threshold=50, severity=Severity.WARNING)
        assert router.evaluate_threshold(metric, rule)

    def test_evaluate_threshold_lt(self):
        router = AlertRouter()
        metric = AggregatedMetric(metric_name="events", window_key="w1", count=10)
        rule = AlertRule(alert_id="a1", metric_name="events", operator="lt", threshold=50, severity=Severity.INFO)
        assert router.evaluate_threshold(metric, rule)

    def test_suppress_duplicate_blocks_within_cooldown(self):
        router = AlertRouter()
        assert not router.suppress_duplicate("alert:test", cooldown_sec=60.0)
        assert router.suppress_duplicate("alert:test", cooldown_sec=60.0)

    def test_acknowledge_removes_active_alert(self):
        router = AlertRouter()
        receipt = router.route_alert("a1", Severity.CRITICAL, {"suppression_key": ""})
        assert "a1" in router.active_alerts
        ack = router.acknowledge("a1", "investigated")
        assert "a1" not in router.active_alerts
        assert ack.acknowledgement == "investigated"

    def test_route_alert_critical_to_special_topic(self):
        router = AlertRouter()
        receipt = router.route_alert("a2", Severity.CRITICAL, {})
        assert receipt.routed_to == "runtime.alert.critical"

    def test_route_alert_idempotent(self):
        router = AlertRouter()
        r1 = router.route_alert("a3", Severity.WARNING, {})
        r2 = router.route_alert("a3", Severity.WARNING, {})
        assert r1.alert_id == r2.alert_id


# ════════════════════════════════════════════════════════════════════
# G5 — TestDashboardSnapshot (3 tests)
# ════════════════════════════════════════════════════════════════════


class TestDashboardSnapshot:
    """Dashboard data provider returns consistent snapshots."""

    def test_execution_timeline_empty(self):
        dp = DashboardDataProvider()
        seg = dp.get_execution_timeline("nonexistent")
        assert seg.execution_id == "nonexistent"
        assert seg.nodes == []

    def test_execution_timeline_with_events(self):
        dp = DashboardDataProvider()
        evt = ExecutionTimelineEvent(
            sequence_id=1,
            node_id="n1",
            state_transition=NodeStateTransition.PENDING_TO_RUNNING,
            timestamp_ns=time.time_ns(),
            worker_id="w1",
            span_id="s1",
        )
        dp.record_timeline_event(evt)
        seg = dp.get_execution_timeline("n1")
        assert len(seg.nodes) == 1
        assert seg.nodes[0]["node_id"] == "n1"

    def test_worker_topology_counts_health(self):
        dp = DashboardDataProvider()
        dp.update_worker(WorkerTopologySnapshot(worker_id="w1", status=WorkerHealthStatus.HEALTHY))
        dp.update_worker(WorkerTopologySnapshot(worker_id="w2", status=WorkerHealthStatus.DEGRADED))
        dp.update_worker(WorkerTopologySnapshot(worker_id="w3", status=WorkerHealthStatus.OFFLINE))
        view = dp.get_worker_topology()
        assert view.healthy_count == 1
        assert view.degraded_count == 1
        assert view.offline_count == 1


# ════════════════════════════════════════════════════════════════════
# G6 — TestCanonCompliance (3 tests)
# ════════════════════════════════════════════════════════════════════


class TestCanonCompliance:
    """LAW/RULE comment annotations and import hygiene."""

    def test_models_have_law_annotations(self):
        import inspect
        import core.runtime.models.observability_models as m
        source = inspect.getsource(m)
        assert "# LAW-5" in source
        assert "# LAW-12" in source

    def test_each_submodule_has_law_annotations(self):
        modules = [
            "core.runtime.observability.trace_collector",
            "core.runtime.observability.telemetry_aggregator",
            "core.runtime.observability.dashboard_data_provider",
            "core.runtime.observability.alert_router",
            "core.runtime.observability.aggregation_state_machine",
            "core.runtime.observability.backpressure_sampler",
        ]
        for mod_name in modules:
            import importlib
            mod = importlib.import_module(mod_name)
            import inspect
            source = inspect.getsource(mod)
            assert "# LAW" in source, f"{mod_name} missing LAW annotation"
            assert "# RULE" in source, f"{mod_name} missing RULE annotation"

    def test_composition_root_exposes_observability(self):
        from core.composition.root import CompositionRoot
        root = CompositionRoot()
        tc = root.trace_collector
        assert hasattr(tc, "start_span")
        assert hasattr(tc, "end_span")
        assert hasattr(tc, "add_attribute")
        assert hasattr(tc, "propagate_context")

        agg = root.telemetry_aggregator
        assert hasattr(agg, "ingest_event")
        assert hasattr(agg, "compute_metrics")
        assert hasattr(agg, "flush_window")
        assert hasattr(agg, "publish_summary")

        dp = root.dashboard_data_provider
        assert hasattr(dp, "get_execution_timeline")
        assert hasattr(dp, "get_dag_visualization")
        assert hasattr(dp, "get_worker_topology")
        assert hasattr(dp, "get_failure_explorer")

        ar = root.alert_router
        assert hasattr(ar, "evaluate_threshold")
        assert hasattr(ar, "route_alert")
        assert hasattr(ar, "suppress_duplicate")
        assert hasattr(ar, "acknowledge")
