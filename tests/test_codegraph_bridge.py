"""Tests for 3.6.4 — CodeGraph Event Bridge.

Verifies that execution events are translated into CodeGraph
runtime stats and can be merged back into the static graph.
"""

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.codegraph import (
    CodeGraph,
    CodeGraphEventSubscriber,
    Node,
    NodeType,
    RuntimeStats,
    build_codegraph,
)
from core.codegraph.bridge import RuntimeAwareQueryEngine
from core.models.events import ExecutionEvent, make_trace_id
from core.runtime.event_bus import InMemoryEventBus


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def event_bus():
    return InMemoryEventBus()


@pytest.fixture
def subscriber(event_bus):
    return CodeGraphEventSubscriber(event_bus)


@pytest.fixture
def sample_graph():
    graph = CodeGraph()
    graph.add_node(Node(
        id="n1", type=NodeType.FILE, name="hybrid_retrieval.py",
        path="core/hybrid_retrieval.py", risk_score=0.5,
    ))
    graph.add_node(Node(
        id="n2", type=NodeType.FILE, name="execution_engine.py",
        path="core/execution_engine.py", risk_score=0.3,
    ))
    graph.add_node(Node(
        id="n3", type=NodeType.FILE, name="event_bus.py",
        path="core/event_bus.py", risk_score=0.1,
    ))
    return graph


def make_event(event_type, tool="mock_tool",
               session="test-session", duration=0.0, error=None):
    payload = {"tool": tool}
    if duration:
        payload["duration"] = duration
    if error:
        payload["error"] = error
    return ExecutionEvent(
        event_id=f"evt-{int(time.time()*1e6)}",
        event_type=event_type,
        timestamp=time.time(),
        source="execution_engine",
        payload=payload,
        trace_id=make_trace_id(),
        session_id=session,
    )


# ── RuntimeStats Tests ───────────────────────────────────────────────────────

class TestRuntimeStats:

    def test_record_completed(self):
        stats = RuntimeStats()
        stats.record_node_completed("tool_a", duration=1.5)
        assert stats.execution_count["tool_a"] == 1
        assert stats.total_duration["tool_a"] == 1.5
        assert stats.last_status["tool_a"] == "completed"

    def test_record_failed(self):
        stats = RuntimeStats()
        stats.record_node_failed("tool_a")
        assert stats.execution_count["tool_a"] == 1
        assert stats.failure_count["tool_a"] == 1
        assert stats.last_status["tool_a"] == "failed"

    def test_failure_rate(self):
        stats = RuntimeStats()
        assert stats.get_failure_rate("tool_a") == 0.0
        stats.record_node_completed("tool_a")
        stats.record_node_failed("tool_a")
        assert stats.get_failure_rate("tool_a") == 0.5
        stats.record_node_completed("tool_a")
        assert stats.get_failure_rate("tool_a") == pytest.approx(0.333, abs=0.01)

    def test_avg_duration(self):
        stats = RuntimeStats()
        stats.record_node_completed("tool_a", duration=2.0)
        stats.record_node_completed("tool_a", duration=4.0)
        assert stats.get_avg_duration("tool_a") == 3.0

    def test_snapshot(self):
        stats = RuntimeStats()
        stats.record_node_completed("tool_a")
        stats.record_node_failed("tool_b")
        snap = stats.snapshot()
        assert "tool_a" in snap
        assert "tool_b" in snap
        assert snap["tool_a"]["runtime_execution_count"] == 1
        assert snap["tool_b"]["runtime_failure_count"] == 1

    def test_multiple_tools_isolated(self):
        stats = RuntimeStats()
        stats.record_node_completed("tool_a")
        stats.record_node_completed("tool_b")
        stats.record_node_failed("tool_b")
        assert stats.execution_count["tool_a"] == 1
        assert stats.execution_count["tool_b"] == 2
        assert stats.failure_count["tool_b"] == 1
        assert stats.failure_count["tool_a"] == 0


# ── CodeGraphEventSubscriber Tests ────────────────────────────────────────────

class TestCodeGraphEventSubscriber:

    def test_subscriber_receives_events(self, event_bus):
        sub = CodeGraphEventSubscriber(event_bus)
        event = make_event("NODE_COMPLETED", tool="tool_a")
        event_bus.publish("execution", event)
        assert sub.event_count == 1

    def test_subscriber_tracks_completed(self, event_bus):
        sub = CodeGraphEventSubscriber(event_bus)
        event_bus.publish("execution", make_event(
            "NODE_COMPLETED", tool="hybrid_retrieval", duration=2.5))
        stats = sub.stats_snapshot()
        assert stats["hybrid_retrieval"]["runtime_execution_count"] == 1
        assert stats["hybrid_retrieval"]["runtime_last_status"] == "completed"

    def test_subscriber_tracks_failed(self, event_bus):
        sub = CodeGraphEventSubscriber(event_bus)
        event_bus.publish("execution", make_event(
            "NODE_FAILED", tool="execution_engine"))
        stats = sub.stats_snapshot()
        assert stats["execution_engine"]["runtime_execution_count"] == 1
        assert stats["execution_engine"]["runtime_failure_count"] == 1

    def test_subscriber_tracks_sessions(self, event_bus):
        sub = CodeGraphEventSubscriber(event_bus)
        event_bus.publish("execution", make_event("NODE_COMPLETED", session="s1"))
        event_bus.publish("execution", make_event("NODE_COMPLETED", session="s1"))
        event_bus.publish("execution", make_event("NODE_COMPLETED", session="s2"))
        assert sub.session_count == 2

    def test_subscriber_ignores_unknown_events(self, event_bus):
        sub = CodeGraphEventSubscriber(event_bus)
        event = make_event("STATE_TRANSITION", tool="tool_a")
        event_bus.publish("execution", event)
        assert sub.event_count == 1
        assert len(sub.stats_snapshot()) == 0

    def test_multiple_events_accumulate(self, event_bus):
        sub = CodeGraphEventSubscriber(event_bus)
        for i in range(5):
            event_bus.publish("execution", make_event(
                "NODE_COMPLETED", tool="tool_a", duration=1.0))
        stats = sub.stats_snapshot()
        assert stats["tool_a"]["runtime_execution_count"] == 5
        assert stats["tool_a"]["runtime_avg_duration"] == 1.0

    def test_empty_tool_ignored(self, event_bus):
        sub = CodeGraphEventSubscriber(event_bus)
        event = make_event("NODE_COMPLETED", tool="")
        event_bus.publish("execution", event)
        assert sub.event_count == 1
        assert len(sub.stats_snapshot()) == 0


# ── Merge Runtime Stats Into CodeGraph Tests ──────────────────────────────────

class TestMergeIntoCodeGraph:

    def test_merge_adds_metadata(self, event_bus, sample_graph):
        sub = CodeGraphEventSubscriber(event_bus)
        event_bus.publish("execution", make_event(
            "NODE_COMPLETED", tool="hybrid_retrieval", duration=3.0))
        event_bus.publish("execution", make_event(
            "NODE_FAILED", tool="hybrid_retrieval"))
        merged = sub.merge_into(sample_graph)
        n1 = merged.get_node("n1")
        assert n1 is not None
        assert n1.metadata["runtime_execution_count"] == 2
        assert n1.metadata["runtime_failure_rate"] == 0.5

    def test_merge_updates_risk_score(self, event_bus, sample_graph):
        sub = CodeGraphEventSubscriber(event_bus)
        event_bus.publish("execution", make_event(
            "NODE_COMPLETED", tool="hybrid_retrieval"))
        event_bus.publish("execution", make_event(
            "NODE_FAILED", tool="hybrid_retrieval"))
        merged = sub.merge_into(sample_graph)
        n1 = merged.get_node("n1")
        assert n1 is not None
        assert n1.risk_score == pytest.approx(0.6, abs=0.01)

    def test_merge_only_affects_matched_nodes(self, event_bus, sample_graph):
        sub = CodeGraphEventSubscriber(event_bus)
        event_bus.publish("execution", make_event(
            "NODE_COMPLETED", tool="hybrid_retrieval"))
        merged = sub.merge_into(sample_graph)
        n2 = merged.get_node("n2")
        assert n2 is not None
        assert "runtime_execution_count" not in n2.metadata
        assert n2.risk_score == 0.3  # unchanged

    def test_merge_preserves_unmatched_nodes(self, event_bus, sample_graph):
        sub = CodeGraphEventSubscriber(event_bus)
        merged = sub.merge_into(sample_graph)
        assert len(merged.nodes) == 3
        n3 = merged.get_node("n3")
        assert n3 is not None
        assert n3.risk_score == 0.1

    def test_merge_large_failure_rate_caps_risk(self, event_bus, sample_graph):
        sub = CodeGraphEventSubscriber(event_bus)
        for _ in range(10):
            event_bus.publish("execution", make_event(
                "NODE_FAILED", tool="execution_engine"))
        merged = sub.merge_into(sample_graph)
        n2 = merged.get_node("n2")
        assert n2 is not None
        assert n2.risk_score <= 1.0  # capped

    def test_merge_matches_by_path_similarity(self, event_bus, sample_graph):
        """Tool 'hybrid_retrieval' should match node path 'hybrid_retrieval.py'."""
        sub = CodeGraphEventSubscriber(event_bus)
        event_bus.publish("execution", make_event(
            "NODE_COMPLETED", tool="hybrid_retrieval"))
        merged = sub.merge_into(sample_graph)
        n1 = merged.get_node("n1")
        assert n1 is not None
        assert n1.metadata.get("runtime_execution_count", 0) == 1


# ── RuntimeAwareQueryEngine Tests ─────────────────────────────────────────────

class TestRuntimeAwareQueryEngine:

    @pytest.fixture
    def engine(self, sample_graph):
        stats = RuntimeStats()
        stats.record_node_completed("hybrid_retrieval")
        stats.record_node_completed("hybrid_retrieval")
        stats.record_node_completed("execution_engine")
        stats.record_node_failed("execution_engine")
        return RuntimeAwareQueryEngine(sample_graph, stats)

    def test_get_hotspots(self, engine):
        hotspots = engine.get_hotspots(min_executions=2)
        assert len(hotspots) >= 1
        ee = [h for h in hotspots if "execution_engine" in h["path"]]
        assert len(ee) == 1
        assert ee[0]["failure_rate"] == 0.5

    def test_get_most_executed(self, engine):
        ranked = engine.get_most_executed(limit=2)
        assert len(ranked) == 2
        assert ranked[0]["executions"] == 2  # hybrid_retrieval

    def test_get_hotspots_empty(self):
        stats = RuntimeStats()
        graph = CodeGraph()
        qe = RuntimeAwareQueryEngine(graph, stats)
        assert qe.get_hotspots() == []


# ── Full Integration Test ─────────────────────────────────────────────────────

class TestIntegration:

    def test_event_to_graph_pipeline(self, event_bus):
        """End-to-end: ExecutionEngine emits → bridge receives → graph merged."""
        from core.execution_engine import DAGBuilder, ExecutionEngine

        engine = ExecutionEngine(event_bus=event_bus)
        sub = CodeGraphEventSubscriber(event_bus)

        dag = (
            DAGBuilder()
            .add("step1", tool="mock_tool")
            .build()
        )
        engine.execute(dag, session_id="integ-test")

        assert sub.event_count > 0
        assert sub.session_count == 1

        # Build a graph and merge runtime data
        graph = build_codegraph("core")
        merged = sub.merge_into(graph)
        # The bridge tracks by tool name and matches by path;
        # "mock_tool" won't match any real file, but the pipeline
        # should complete without errors and preserve existing nodes.
        assert len(merged.nodes) > 0
