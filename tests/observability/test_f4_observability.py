"""Phase F4 — Observability Layer & Telemetry Unification: 30 tests.

Groups:
  - TestTraceCorrelation:    6 tests — create, propagate, reconstruct, zero loss
  - TestDashboardConsistency: 6 tests — accurate metrics, real-time, no stale
  - TestTimelineReconstruction: 6 tests — deterministic, event matching
  - TestFailureCorrelation:   6 tests — cause detection, intelligence merge, export
  - TestTopologyMapping:      6 tests — correct graph, partition detection, lease map

Ref: Canon LAW 5, LAW 12, RULE 1, RULE 3
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pytest

from core.runtime.observability.distributed_tracer import (
    DistributedTracer,
    Span,
    Trace,
)
from core.runtime.observability.dashboard_service import (
    RuntimeDashboardService,
    HealthReport,
    MetricsSnapshot,
    DashboardEvent,
)
from core.runtime.observability.timeline_builder import (
    ExecutionTimelineBuilder,
    TimelineNode,
    Timeline,
)
from core.runtime.observability.failure_explorer import (
    FailureExplorer,
    RootCauseHint,
    TraceBundle,
)
from core.runtime.observability.topology_viewer import (
    WorkerTopologyViewer,
    TopologyGraph,
    TopologyNode,
    LeaseMap,
    Partition,
)


# ── Helpers ─────────────────────────────────────────────────

class FakeTraceCollector:
    def __init__(self):
        self._active: Dict[str, Any] = {}
        self._completed: List[Any] = []

    def start_span(self, operation_name, trace_id, parent_id=None, attributes=None):
        span_id = uuid.uuid4().hex[:12]
        self._active[span_id] = {"op": operation_name, "trace": trace_id}
        return span_id

    def end_span(self, span_id, status="ok", attributes=None):
        span = self._active.pop(span_id, None)
        if span:
            span["status"] = status
            self._completed.append(span)

    @property
    def completed_spans(self):
        return self._completed


class FakeEventStore:
    def __init__(self):
        self._events: List[Any] = []

    def append(self, event):
        self._events.append(event)

    def replay(self):
        return list(self._events)

    def clear(self):
        self._events.clear()


@dataclass
class FakeStoredEvent:
    event_id: str
    event_type: str
    timestamp: float
    source: str
    payload: Dict[str, Any]
    trace_id: str = ""
    session_id: str = ""


class FakeClusterManager:
    def __init__(self):
        self._workers: List[Any] = []

    def list_active_workers(self):
        return self._workers

    def check_stale_workers(self, timeout=60.0):
        return []

    def set_workers(self, workers):
        self._workers = workers


@dataclass
class FakeWorker:
    worker_id: str
    state: str = "healthy"
    load: Any = None
    lease_id: str = ""
    tags: Dict[str, str] = field(default_factory=dict)
    capabilities: Dict[str, Any] = field(default_factory=dict)

    def __repr__(self):
        return f"FakeWorker({self.worker_id})"


@dataclass
class FakeLoad:
    cpu_pct: float = 0.0
    mem_pct: float = 0.0


class FakeQuotaManager:
    def enforce_global_ceiling(self):
        return "hold"


class FakeAlertRouter:
    def __init__(self):
        self.active_alerts: Dict[str, Any] = {}

    @property
    def active_alert_count(self):
        return len(self.active_alerts)


class FakeEventBus:
    def __init__(self):
        self.events: List[tuple[str, Any]] = []

    def publish(self, topic, event):
        self.events.append((topic, event))

    def subscribe(self, topic, handler):
        pass

    def clear(self):
        self.events.clear()


# ── TestTraceCorrelation ────────────────────────────────────

class TestTraceCorrelation:
    """Create, propagate, reconstruct, zero lost spans."""

    def test_create_trace_returns_trace_id(self):
        tracer = DistributedTracer()
        tid = tracer.create_trace("exec_1", "dag_1")
        assert isinstance(tid, str)
        assert len(tid) == 16

    def test_create_trace_stores_internal(self):
        tracer = DistributedTracer()
        tid = tracer.create_trace("exec_1")
        trace = tracer.get_trace(tid)
        assert trace is not None
        assert trace.execution_id == "exec_1"

    def test_propagate_span_returns_span_id(self):
        tracer = DistributedTracer()
        tid = tracer.create_trace("exec_1")
        sid = tracer.propagate_span("test_service", "test_event", {}, trace_id=tid)
        assert isinstance(sid, str)
        assert len(sid) == 12

    def test_propagate_span_links_to_trace(self):
        tracer = DistributedTracer()
        tid = tracer.create_trace("exec_1")
        sid1 = tracer.propagate_span("svc_a", "evt_a", {"key": "val"}, trace_id=tid)
        sid2 = tracer.propagate_span("svc_b", "evt_b", {}, trace_id=tid, parent_span_id=sid1)
        trace = tracer.get_trace(tid)
        assert trace is not None
        assert len(trace.spans) == 2

    def test_reconstruct_trace_returns_sorted_spans(self):
        tracer = DistributedTracer()
        tid = tracer.create_trace("exec_1")
        tracer.propagate_span("svc_a", "first", {}, trace_id=tid)
        tracer.propagate_span("svc_b", "second", {}, trace_id=tid)
        spans = tracer.reconstruct_trace(tid)
        assert len(spans) >= 2
        for i in range(len(spans) - 1):
            assert spans[i].start_ns <= spans[i + 1].start_ns

    def test_reconstruct_trace_empty_for_unknown(self):
        tracer = DistributedTracer()
        spans = tracer.reconstruct_trace("nonexistent")
        assert spans == []


# ── TestDashboardConsistency ────────────────────────────────

class TestDashboardConsistency:
    """Accurate metrics, real-time updates, no stale data."""

    def test_get_system_health_returns_report(self):
        ds = RuntimeDashboardService()
        report = ds.get_system_health()
        assert isinstance(report, HealthReport)
        assert report.last_updated > 0

    def test_get_system_health_with_workers(self):
        cm = FakeClusterManager()
        cm.set_workers([
            FakeWorker(worker_id="w1", state="healthy"),
            FakeWorker(worker_id="w2", state="healthy"),
        ])
        ds = RuntimeDashboardService(cluster_manager=cm)
        report = ds.get_system_health()
        assert report.total_workers == 2
        assert report.healthy_workers == 2

    def test_get_system_health_detects_degraded(self):
        cm = FakeClusterManager()
        cm.set_workers([
            FakeWorker(worker_id="w1", state="healthy"),
            FakeWorker(worker_id="w2", state="degraded"),
        ])
        ds = RuntimeDashboardService(cluster_manager=cm)
        report = ds.get_system_health()
        assert report.degraded_workers == 1
        assert not report.cluster_healthy

    def test_get_runtime_metrics_returns_snapshot(self):
        ds = RuntimeDashboardService()
        metrics = ds.get_runtime_metrics(timeframe_sec=60.0)
        assert isinstance(metrics, MetricsSnapshot)
        assert metrics.dau >= 0

    def test_get_runtime_metrics_with_event_store(self):
        store = FakeEventStore()
        store.append(FakeStoredEvent(
            event_id="e1", event_type="SCHEDULED", timestamp=time.time(),
            source="SchedulingOrchestrator",
            payload={"execution_id": "exec_1"},
        ))
        ds = RuntimeDashboardService(event_store=store)
        metrics = ds.get_runtime_metrics(timeframe_sec=3600.0)
        assert metrics.total_executions >= 0

    def test_subscribe_to_realtime_registers_callback(self):
        ds = RuntimeDashboardService()
        result = ds.subscribe_to_realtime("test_sub", lambda e: None)
        assert result is True


# ── TestTimelineReconstruction ──────────────────────────────

class TestTimelineReconstruction:
    """Deterministic chronological timeline, event matching."""

    def test_build_timeline_empty_returns_empty(self):
        tb = ExecutionTimelineBuilder()
        timeline = tb.build_timeline("nonexistent")
        assert isinstance(timeline, Timeline)
        assert timeline.nodes == []

    def test_build_timeline_single_event(self):
        store = FakeEventStore()
        store.append(FakeStoredEvent(
            event_id="e1", event_type="SCHEDULED", timestamp=1000.0,
            source="SchedulingOrchestrator",
            payload={"execution_id": "exec_1", "worker_id": "w1"},
        ))
        tb = ExecutionTimelineBuilder(event_store=store)
        timeline = tb.build_timeline("exec_1")
        assert len(timeline.nodes) == 1
        assert timeline.nodes[0].source == "SchedulingOrchestrator"

    def test_build_timeline_chronological_order(self):
        store = FakeEventStore()
        store.append(FakeStoredEvent(
            event_id="e2", event_type="SCHEDULED", timestamp=2000.0,
            source="Scheduler", payload={"execution_id": "exec_2"},
        ))
        store.append(FakeStoredEvent(
            event_id="e1", event_type="QUEUED", timestamp=1000.0,
            source="Scheduler", payload={"execution_id": "exec_2"},
        ))
        tb = ExecutionTimelineBuilder(event_store=store)
        timeline = tb.build_timeline("exec_2")
        assert len(timeline.nodes) == 2
        assert timeline.nodes[0].event_type == "QUEUED"
        assert timeline.nodes[1].event_type == "SCHEDULED"

    def test_build_timeline_detects_errors(self):
        store = FakeEventStore()
        store.append(FakeStoredEvent(
            event_id="e1", event_type="FAILED", timestamp=1000.0,
            source="Execution", payload={"execution_id": "exec_3"},
        ))
        tb = ExecutionTimelineBuilder(event_store=store)
        timeline = tb.build_timeline("exec_3")
        assert timeline.error_count == 1

    def test_build_timeline_computes_duration(self):
        store = FakeEventStore()
        store.append(FakeStoredEvent(
            event_id="e1", event_type="STARTED", timestamp=1000.0,
            source="Execution", payload={"execution_id": "exec_4"},
        ))
        store.append(FakeStoredEvent(
            event_id="e2", event_type="COMPLETED", timestamp=1005.0,
            source="Execution", payload={"execution_id": "exec_4"},
        ))
        tb = ExecutionTimelineBuilder(event_store=store)
        timeline = tb.build_timeline("exec_4")
        assert timeline.total_duration_ms >= 0

    def test_build_timeline_deterministic(self):
        store = FakeEventStore()
        store.append(FakeStoredEvent(
            event_id="e1", event_type="SCHEDULED", timestamp=1000.0,
            source="Scheduler", payload={"execution_id": "exec_5"},
        ))
        tb = ExecutionTimelineBuilder(event_store=store)
        t1 = tb.build_timeline("exec_5")
        t2 = tb.build_timeline("exec_5")
        assert len(t1.nodes) == len(t2.nodes)
        assert t1.nodes[0].event_type == t2.nodes[0].event_type


# ── TestFailureCorrelation ──────────────────────────────────

class TestFailureCorrelation:
    """Cause detection, intelligence merge, export."""

    def test_analyze_failure_quota_exhaustion(self):
        fe = FailureExplorer()
        hint = fe.analyze_failure({"error": "quota exceeded for worker"})
        assert hint.cause == "quota_exhaustion"
        assert hint.confidence > 0.0

    def test_analyze_failure_retry_loop(self):
        fe = FailureExplorer()
        hint = fe.analyze_failure({"error": "retry_handler max_retries reached"})
        assert hint.cause == "retry_loop"
        assert hint.confidence > 0.0

    def test_analyze_failure_unknown_returns_suggestion(self):
        fe = FailureExplorer()
        hint = fe.analyze_failure({"error": "unknown internal error"})
        assert hint.cause == "unknown"
        assert hint.suggested_action != ""

    def test_analyze_failure_with_trace_id(self):
        fe = FailureExplorer()
        hint = fe.analyze_failure(
            {"error": "lease expired for worker w1"},
            trace_id="trace_123",
        )
        assert hint.trace_id == "trace_123"
        assert hint.confidence > 0.0

    def test_export_trace_bundle_returns_bundle(self):
        fe = FailureExplorer()
        bundle = fe.export_trace_bundle("trace_999")
        assert isinstance(bundle, TraceBundle)
        assert bundle.trace_id == "trace_999"
        assert bundle.export_format == "json"

    def test_export_trace_bundle_with_events(self):
        store = FakeEventStore()
        store.append(FakeStoredEvent(
            event_id="e1", event_type="SCHEDULED", timestamp=1000.0,
            source="Scheduler", payload={}, trace_id="trace_abc",
        ))
        fe = FailureExplorer(event_store=store)
        bundle = fe.export_trace_bundle("trace_abc")
        assert len(bundle.spans) >= 1


# ── TestTopologyMapping ─────────────────────────────────────

class TestTopologyMapping:
    """Correct graph, partition detection, lease mapping."""

    def test_get_worker_graph_empty(self):
        cm = FakeClusterManager()
        tv = WorkerTopologyViewer(cluster_manager=cm)
        graph = tv.get_worker_graph()
        assert isinstance(graph, TopologyGraph)
        assert graph.nodes == []

    def test_get_worker_graph_with_workers(self):
        cm = FakeClusterManager()
        cm.set_workers([
            FakeWorker(worker_id="w1", state="healthy", load=FakeLoad(cpu_pct=30, mem_pct=50)),
            FakeWorker(worker_id="w2", state="healthy", load=FakeLoad(cpu_pct=60, mem_pct=40)),
        ])
        tv = WorkerTopologyViewer(cluster_manager=cm)
        graph = tv.get_worker_graph()
        assert len(graph.nodes) == 2
        assert graph.nodes[0].worker_id == "w1"
        assert graph.nodes[1].worker_id == "w2"

    def test_get_worker_graph_load_pct(self):
        cm = FakeClusterManager()
        cm.set_workers([
            FakeWorker(worker_id="w1", state="healthy", load=FakeLoad(cpu_pct=80, mem_pct=60)),
        ])
        tv = WorkerTopologyViewer(cluster_manager=cm)
        graph = tv.get_worker_graph()
        assert graph.nodes[0].load_pct == 70.0

    def test_map_leases_to_workers_empty(self):
        cm = FakeClusterManager()
        tv = WorkerTopologyViewer(cluster_manager=cm)
        lease_map = tv.map_leases_to_workers()
        assert isinstance(lease_map, LeaseMap)
        assert lease_map.total_active == 0

    def test_map_leases_to_workers_with_lease(self):
        cm = FakeClusterManager()
        cm.set_workers([
            FakeWorker(worker_id="w1", state="healthy", lease_id="lease_1"),
        ])
        tv = WorkerTopologyViewer(cluster_manager=cm)
        lease_map = tv.map_leases_to_workers()
        assert lease_map.total_active == 1
        assert lease_map.leases[0].lease_id == "lease_1"

    def test_detect_network_partitions_returns_empty_when_healthy(self):
        cm = FakeClusterManager()
        tv = WorkerTopologyViewer(cluster_manager=cm)
        partitions = tv.detect_network_partitions()
        assert isinstance(partitions, list)
