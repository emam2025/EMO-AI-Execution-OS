"""Tests for F4 — ObservabilityLayer."""

from __future__ import annotations

import time
import pytest
from core.observability.trace import TraceStore, ExecutionTrace, Span, SpanStatus
from core.observability.timeline import TimelineStore, Timeline, TimelineEvent, EventType
from core.observability.failure_explorer import FailureExplorer, FailureRecord, FailurePattern
from core.observability.topology_viewer import TopologyViewer, TopologyNode, TopologyEdge


# ── ExecutionTrace Tests ─────────────────────────────────────

class TestExecutionTrace:
    def test_create_trace(self):
        ts = TraceStore()
        trace = ts.create_trace("e1", "dag-1", "balanced")
        assert trace.execution_id == "e1"
        assert trace.dag_id == "dag-1"
        assert trace.strategy == "balanced"

    def test_start_span(self):
        trace = ExecutionTrace(execution_id="e1")
        span = trace.start_span("submit", "control_plane")
        assert span.span_id in trace.spans
        assert trace.root_span_id == span.span_id
        assert span.parent_span_id is None

    def test_start_child_span(self):
        trace = ExecutionTrace(execution_id="e1")
        parent = trace.start_span("parent", "svc")
        child = trace.start_span("child", "svc", parent_span_id=parent.span_id)
        assert child.parent_span_id == parent.span_id

    def test_end_span(self):
        trace = ExecutionTrace(execution_id="e1")
        span = trace.start_span("work", "worker")
        trace.end_span(span.span_id, SpanStatus.OK)
        assert trace.spans[span.span_id].is_complete
        assert trace.spans[span.span_id].duration_ms > 0

    def test_end_span_with_error(self):
        trace = ExecutionTrace(execution_id="e1")
        span = trace.start_span("fail", "worker")
        trace.end_span(span.span_id, SpanStatus.ERROR, "something broke")
        assert trace.error_spans() == [trace.spans[span.span_id]]

    def test_get_span(self):
        trace = ExecutionTrace(execution_id="e1")
        span = trace.start_span("test", "svc")
        assert trace.get_span(span.span_id) == span
        assert trace.get_span("nonexistent") is None

    def test_spans_by_service(self):
        trace = ExecutionTrace(execution_id="e1")
        trace.start_span("s1", "svc_a")
        trace.start_span("s2", "svc_b")
        trace.start_span("s3", "svc_a")
        assert len(trace.spans_by_service("svc_a")) == 2
        assert len(trace.spans_by_service("svc_b")) == 1

    def test_span_tree(self):
        trace = ExecutionTrace(execution_id="e1")
        root = trace.start_span("root", "svc")
        child1 = trace.start_span("c1", "svc", root.span_id)
        child2 = trace.start_span("c2", "svc", root.span_id)
        grandchild = trace.start_span("gc", "svc", child1.span_id)

        tree = trace.span_tree()
        assert len(tree) == 4

    def test_to_dict(self):
        trace = ExecutionTrace(execution_id="e1", dag_id="dag-1")
        d = trace.to_dict()
        assert d["execution_id"] == "e1"
        assert d["dag_id"] == "dag-1"
        assert d["status"] == "pending"

    def test_complete_trace(self):
        ts = TraceStore()
        trace = ts.create_trace("e1")
        time.sleep(0.01)
        ts.complete_trace("e1", SpanStatus.OK)
        completed = ts.get_trace("e1")
        assert completed.status == SpanStatus.OK
        assert completed.ended_at > 0
        assert completed.total_duration_ms > 0

    def test_recent_errors(self):
        ts = TraceStore()
        ts.create_trace("e1")
        ts.create_trace("e2")
        ts.complete_trace("e1", SpanStatus.ERROR, "fail")
        ts.complete_trace("e2", SpanStatus.OK)
        errors = ts.recent_errors(minutes=5)
        assert len(errors) == 1
        assert errors[0].execution_id == "e1"

    def test_all_traces_limit(self):
        ts = TraceStore()
        for i in range(10):
            ts.create_trace(f"e{i}")
        assert len(ts.all_traces(limit=5)) == 5
        assert len(ts.all_traces(limit=20)) == 10

    def test_max_traces_eviction(self):
        ts = TraceStore(max_traces=5)
        for i in range(10):
            ts.create_trace(f"e{i}")
        assert len(ts._traces) <= 5

    def test_clear_traces(self):
        ts = TraceStore()
        ts.create_trace("e1")
        ts.clear()
        assert len(ts._traces) == 0


# ── Timeline Tests ───────────────────────────────────────────

class TestTimeline:
    def test_create_timeline(self):
        store = TimelineStore()
        tl = store.get_or_create("e1")
        assert tl.execution_id == "e1"
        assert store.get("e1") is tl

    def test_add_event(self):
        store = TimelineStore()
        event = store.add_event("e1", EventType.SUBMITTED, "svc", "started")
        assert event is not None
        assert event.event_type == EventType.SUBMITTED
        assert event.service == "svc"
        assert event.message == "started"

    def test_events_since(self):
        tl = Timeline("e1")
        tl.add_event(EventType.SUBMITTED)
        time.sleep(0.01)
        tl.add_event(EventType.SCHEDULED)
        cutoff = time.time()
        tl.add_event(EventType.DISPATCHED)
        recent = tl.events_since(cutoff)
        assert len(recent) == 1

    def test_filter_by_type(self):
        tl = Timeline("e1")
        tl.add_event(EventType.SUBMITTED)
        tl.add_event(EventType.SCHEDULED)
        filtered = tl.filter(event_type=EventType.SCHEDULED)
        assert len(filtered) == 1

    def test_filter_by_service(self):
        tl = Timeline("e1")
        tl.add_event(EventType.SUBMITTED, service="svc_a")
        tl.add_event(EventType.WORKER_STARTED, service="svc_b")
        filtered = tl.filter(service="svc_a")
        assert len(filtered) == 1

    def test_summary(self):
        tl = Timeline("e1")
        tl.add_event(EventType.SUBMITTED, "svc", "hello")
        summary = tl.summary()
        assert len(summary) == 1
        assert summary[0]["event"] == "submitted"
        assert summary[0]["message"] == "hello"

    def test_query_global(self):
        store = TimelineStore()
        store.add_event("e1", EventType.SUBMITTED, "svc_a")
        store.add_event("e2", EventType.WORKER_FAILED, "svc_b")
        failures = store.query(event_type=EventType.WORKER_FAILED)
        assert len(failures) == 1

    def test_execution_summary(self):
        store = TimelineStore()
        store.add_event("e1", EventType.SUBMITTED)
        summary = store.execution_summary("e1")
        assert summary is not None
        assert len(summary) == 1
        assert store.execution_summary("nonexistent") is None

    def test_max_eviction(self):
        store = TimelineStore(max_executions=3)
        for i in range(5):
            store.add_event(f"e{i}", EventType.SUBMITTED)
        assert len(store._timelines) <= 3

    def test_clear(self):
        store = TimelineStore()
        store.add_event("e1", EventType.SUBMITTED)
        store.clear()
        assert len(store._timelines) == 0


# ── FailureExplorer Tests ─────────────────────────────────────

class TestFailureExplorer:
    def test_record_failure(self):
        fe = FailureExplorer()
        rec = fe.record_failure("e1", "timeout", "svc_a", "w1", "n1")
        assert rec.execution_id == "e1"
        assert rec.error == "timeout"
        assert len(fe._records) == 1

    def test_top_errors(self):
        fe = FailureExplorer()
        fe.record_failure("e1", "timeout")
        fe.record_failure("e2", "timeout")
        fe.record_failure("e3", "oom")
        top = fe.top_errors()
        assert top[0]["error"] == "timeout"
        assert top[0]["count"] == 2

    def test_top_error_types(self):
        fe = FailureExplorer()
        fe.record_failure("e1", "err", error_type="network")
        fe.record_failure("e2", "err", error_type="network")
        fe.record_failure("e3", "err", error_type="compute")
        top = fe.top_error_types()
        assert top[0]["type"] == "network"

    def test_top_failing_services(self):
        fe = FailureExplorer()
        fe.record_failure("e1", "err", service="svc_a")
        fe.record_failure("e2", "err", service="svc_a")
        fe.record_failure("e3", "err", service="svc_b")
        top = fe.top_failing_services()
        assert top[0]["service"] == "svc_a"

    def test_top_failing_workers(self):
        fe = FailureExplorer()
        fe.record_failure("e1", "err", worker_id="w1")
        fe.record_failure("e2", "err", worker_id="w1")
        fe.record_failure("e3", "err", worker_id="w2")
        top = fe.top_failing_workers()
        assert top[0]["worker"] == "w1"

    def test_top_failing_nodes(self):
        fe = FailureExplorer()
        fe.record_failure("e1", "err", node_id="n1")
        fe.record_failure("e2", "err", node_id="n1")
        top = fe.top_failing_nodes()
        assert top[0]["node"] == "n1"

    def test_failure_patterns(self):
        fe = FailureExplorer()
        fe.record_failure("e1", "connection timeout on port 8080")
        fe.record_failure("e2", "connection timeout on port 9090")
        fe.record_failure("e3", "random error")
        patterns = fe.failure_patterns(min_count=2)
        assert len(patterns) >= 1
        timeout_patterns = [p for p in patterns if "timeout" in p.error_substring]
        assert len(timeout_patterns) >= 1
        assert timeout_patterns[0].count >= 2

    def test_failure_trend(self):
        fe = FailureExplorer()
        fe.record_failure("e1", "err")
        trend = fe.failure_trend(minutes=1)
        assert trend["total_failures"] >= 1

    def test_cascade_analysis(self):
        fe = FailureExplorer()
        fe.record_failure("e1", "err", node_id="n1")
        time.sleep(0.01)
        fe.record_failure("e2", "err", node_id="n1")
        cascades = fe.cascade_analysis(window_seconds=60.0)
        if cascades:
            assert cascades[0]["trigger"] == "e1"

    def test_retry_effectiveness(self):
        fe = FailureExplorer()
        fe.record_failure("e1", "err", retry_count=1, recovered=True)
        fe.record_failure("e2", "err", retry_count=2, recovered=False)
        eff = fe.retry_effectiveness()
        assert eff["total_retried"] == 2
        assert eff["recovered_after_retry"] == 1

    def test_summary(self):
        fe = FailureExplorer()
        fe.record_failure("e1", "timeout", service="svc_a", recovered=True)
        s = fe.summary()
        assert s["total_failures"] == 1
        assert s["top_errors"][0]["error"] == "timeout"

    def test_max_records_eviction(self):
        fe = FailureExplorer(max_records=5)
        for i in range(10):
            fe.record_failure(f"e{i}", f"err{i}")
        assert len(fe._records) <= 5

    def test_clear(self):
        fe = FailureExplorer()
        fe.record_failure("e1", "err")
        fe.clear()
        assert len(fe._records) == 0


# ── TopologyViewer Tests ──────────────────────────────────────

class TestTopologyViewer:
    def test_add_node(self):
        tv = TopologyViewer()
        node = tv.add_node("n1", "Node 1", "online")
        assert node.node_id == "n1"
        assert node.label == "Node 1"
        assert node.status == "online"
        assert tv.get_node("n1") is node

    def test_add_worker(self):
        tv = TopologyViewer()
        tv.add_node("n1", "Node 1")
        worker = tv.add_worker("w1", "n1", "Worker 1", "active")
        assert worker.node_id == "w1"
        assert worker.node_type == "worker"
        assert len(tv._edges) == 1
        assert tv._edges[0].edge_type == "hosts"

    def test_add_service(self):
        tv = TopologyViewer()
        svc = tv.add_service("mesh", "Mesh Service", "running")
        assert svc.node_type == "service"
        # Adding again should update
        tv.add_service("mesh", status="degraded")
        assert tv.get_node("mesh").status == "degraded"

    def test_update_status(self):
        tv = TopologyViewer()
        tv.add_node("n1", status="online")
        tv.update_status("n1", "offline")
        assert tv.get_node("n1").status == "offline"

    def test_remove_node(self):
        tv = TopologyViewer()
        tv.add_node("n1")
        tv.add_worker("w1", "n1")
        tv.remove_node("w1")
        assert tv.get_node("w1") is None
        # Edge should also be removed
        assert not any(e.target_id == "w1" for e in tv._edges)

    def test_connect(self):
        tv = TopologyViewer()
        tv.add_service("svc1")
        tv.add_service("svc2")
        edge = tv.connect("svc1", "svc2", "depends_on", "depends")
        assert edge.edge_type == "depends_on"
        assert edge.label == "depends"

    def test_nodes_by_type(self):
        tv = TopologyViewer()
        tv.add_node("n1")
        tv.add_worker("w1", "n1")
        tv.add_service("svc1")
        assert len(tv.nodes_by_type("node")) == 1
        assert len(tv.nodes_by_type("worker")) == 1
        assert len(tv.nodes_by_type("service")) == 1

    def test_nodes_by_status(self):
        tv = TopologyViewer()
        tv.add_node("n1", status="online")
        tv.add_node("n2", status="offline")
        assert len(tv.nodes_by_status("online")) == 1

    def test_workers_on_node(self):
        tv = TopologyViewer()
        tv.add_node("n1")
        tv.add_worker("w1", "n1")
        tv.add_worker("w2", "n1")
        workers = tv.workers_on_node("n1")
        assert len(workers) == 2

    def test_connections_from_and_to(self):
        tv = TopologyViewer()
        tv.add_service("svc1")
        tv.add_service("svc2")
        tv.connect("svc1", "svc2")
        assert len(tv.connections_from("svc1")) == 1
        assert len(tv.connections_to("svc2")) == 1

    def test_to_graph(self):
        tv = TopologyViewer()
        tv.add_node("n1")
        tv.add_worker("w1", "n1")
        g = tv.to_graph()
        assert len(g["nodes"]) == 2
        assert len(g["edges"]) == 1

    def test_summary(self):
        tv = TopologyViewer()
        tv.add_node("n1")
        tv.add_worker("w1", "n1")
        s = tv.summary()
        assert s["total_nodes"] == 2
        assert s["total_edges"] == 1

    def test_clear(self):
        tv = TopologyViewer()
        tv.add_node("n1")
        tv.clear()
        assert len(tv._nodes) == 0
        assert len(tv._edges) == 0
