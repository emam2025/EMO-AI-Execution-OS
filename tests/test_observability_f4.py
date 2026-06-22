"""Tests for F4 — ObservabilityLayer: DAGVisualizer and RuntimeDashboard."""

from __future__ import annotations

import time
import pytest
from core.observability.dag_visualizer import DAGVisualizer
from core.observability.dashboard import RuntimeDashboard
from core.observability.trace import TraceStore, SpanStatus
from core.observability.timeline import TimelineStore, EventType
from core.observability.failure_explorer import FailureExplorer
from core.observability.topology_viewer import TopologyViewer


# ── DAGVisualizer Tests ─────────────────────────────────────────

class TestDAGVisualizer:
    def test_graph_structure(self):
        class FakeNode:
            def __init__(self, nid, deps, tool="test"):
                self.id = nid
                self.label = nid
                self.tool = tool
                self.depends_on = deps
                self.node_type = type("NT", (), {"value": "task"})()

        class FakeDAG:
            nodes = [
                FakeNode("n1", []),
                FakeNode("n2", ["n1"]),
                FakeNode("n3", ["n2"]),
            ]
            def get_node(self, nid):
                for n in self.nodes:
                    if n.id == nid:
                        return n
                return None

        dag = FakeDAG()
        graph = DAGVisualizer.graph_structure(dag)
        assert len(graph["nodes"]) == 3
        assert len(graph["edges"]) == 2
        assert graph["edges"][0]["source"] == "n1"

    def test_execution_path(self):
        class FakeNode:
            def __init__(self, nid, deps):
                self.id = nid
                self.label = nid
                self.tool = "test"
                self.depends_on = deps
                self.node_type = type("NT", (), {"value": "task"})()

        class FakeDAG:
            nodes = [
                FakeNode("n1", []),
                FakeNode("n2", ["n1"]),
            ]
            def get_node(self, nid):
                for n in self.nodes:
                    if n.id == nid:
                        return n
                return None

        dag = FakeDAG()
        status = {"n1": "completed", "n2": "completed"}
        path = DAGVisualizer.execution_path(dag, status)
        assert path["critical_path"] == ["n1", "n2"]
        for node in path["nodes"]:
            if node["id"] == "n1":
                assert node["status"] == "completed"
                assert node["critical"]

    def test_critical_path_partial(self):
        class FakeNode:
            def __init__(self, nid, deps):
                self.id = nid
                self.label = nid
                self.tool = "test"
                self.depends_on = deps
                self.node_type = type("NT", (), {"value": "task"})()

        class FakeDAG:
            nodes = [
                FakeNode("n1", []),
                FakeNode("n2", ["n1"]),
                FakeNode("n3", ["n1"]),
            ]
            def get_node(self, nid):
                for n in self.nodes:
                    if n.id == nid:
                        return n
                return None

        dag = FakeDAG()
        status = {"n1": "completed", "n2": "failed", "n3": "completed"}
        path = DAGVisualizer.execution_path(dag, status)
        # Critical path is the longest completed path
        assert "n1" in path["critical_path"]

    def test_timeline_view(self):
        class FakeNode:
            def __init__(self, nid, deps):
                self.id = nid
                self.label = nid
                self.tool = "test"
                self.depends_on = deps
                self.node_type = type("NT", (), {"value": "task"})()

        class FakeDAG:
            nodes = [
                FakeNode("n1", []),
                FakeNode("n2", ["n1"]),
            ]
            def get_node(self, nid):
                for n in self.nodes:
                    if n.id == nid:
                        return n
                return None

        dag = FakeDAG()
        timings = {
            "n1": {"started_at": 100.0, "completed_at": 101.0, "duration_ms": 1000.0},
            "n2": {"started_at": 101.0, "completed_at": 103.0, "duration_ms": 2000.0},
        }
        view = DAGVisualizer.timeline_view(dag, timings)
        assert len(view["items"]) == 2
        assert view["items"][0]["level"] == 0
        assert view["items"][1]["level"] == 1

    def test_graph_structure_truncates_at_500_nodes(self):
        class FakeNode:
            def __init__(self, nid, deps):
                self.id = nid
                self.label = nid
                self.tool = "test"
                self.depends_on = deps
                self.node_type = type("NT", (), {"value": "task"})()

        class BigDAG:
            nodes = [FakeNode(f"n{i}", []) for i in range(600)]
            def get_node(self, nid):
                for n in self.nodes:
                    if n.id == nid:
                        return n
                return None

        dag = BigDAG()
        graph = DAGVisualizer.graph_structure(dag)
        assert graph.get("truncated") is True
        assert graph.get("total_node_count") == 600
        assert len(graph["nodes"]) == 500
        assert graph.get("edge_count") == 0

    def test_graph_structure_normal_under_limit(self):
        class FakeNode:
            def __init__(self, nid, deps):
                self.id = nid
                self.label = nid
                self.tool = "test"
                self.depends_on = deps
                self.node_type = type("NT", (), {"value": "task"})()

        class SmallDAG:
            nodes = [FakeNode(f"n{i}", []) for i in range(10)]
            def get_node(self, nid):
                for n in self.nodes:
                    if n.id == nid:
                        return n
                return None

        dag = SmallDAG()
        graph = DAGVisualizer.graph_structure(dag)
        assert graph.get("truncated") is None or graph.get("truncated") is False
        assert len(graph["nodes"]) == 10


# ── RuntimeDashboard Tests ──────────────────────────────────────

class TestRuntimeDashboard:
    def test_create_dashboard(self):
        db = RuntimeDashboard()
        assert db.traces is not None
        assert db.timelines is not None
        assert db.failures is not None
        assert db.topology is not None

    def test_snapshot(self):
        db = RuntimeDashboard()
        snap = db.snapshot()
        assert "overview" in snap
        assert "topology" in snap
        assert "failure_analysis" in snap
        assert "recent_events" in snap

    def test_snapshot_with_data(self):
        db = RuntimeDashboard()
        db.traces.create_trace("e1")
        db.traces.complete_trace("e1", SpanStatus.ERROR, "timeout")
        db.timelines.add_event("e1", EventType.WORKER_FAILED, "svc", "failed")
        db.failures.record_failure("e1", "timeout", "svc_a", "w1", "n1")
        db.topology.add_node("n1")
        db.topology.add_worker("w1", "n1")

        snap = db.snapshot()
        assert len(snap["recent_errors"]) >= 1
        assert len(snap["topology"]["nodes"]) == 2

    def test_execution_detail(self):
        db = RuntimeDashboard()
        db.traces.create_trace("e1", "dag-1")
        detail = db.execution_detail("e1")
        assert detail["execution_id"] == "e1"
        assert "trace" in detail

    def test_execution_detail_not_found(self):
        db = RuntimeDashboard()
        detail = db.execution_detail("nonexistent")
        assert detail["execution_id"] == "nonexistent"

    def test_system_overview(self):
        db = RuntimeDashboard()
        overview = db.system_overview()
        assert "traces" in overview
        assert "topology" in overview
        assert "failures" in overview

    def test_search_executions(self):
        db = RuntimeDashboard()
        db.traces.create_trace("abc-123")
        db.traces.complete_trace("abc-123", SpanStatus.ERROR, "timeout on port 8080")
        results = db.search_executions("abc")
        assert len(results) >= 1
        error_results = db.search_executions("timeout")
        assert len(error_results) >= 1

    def test_failure_trends(self):
        db = RuntimeDashboard()
        db.failures.record_failure("e1", "timeout")
        trends = db.failure_trends(minutes=1)
        assert trends["total_failures"] >= 1

    def test_dashboard_with_custom_stores(self):
        ts = TraceStore()
        tl = TimelineStore()
        fe = FailureExplorer()
        tv = TopologyViewer()
        db = RuntimeDashboard(ts, tl, fe, tv)
        assert db.traces is ts
        assert db.timelines is tl
        assert db.failures is fe
        assert db.topology is tv
