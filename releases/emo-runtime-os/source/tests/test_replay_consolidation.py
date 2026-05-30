"""Tests for P1 — Replay Consolidation."""

from __future__ import annotations

import time
import pytest
from core.replay.engine import ReplayEngine, QueryReplayEngine, ReplayStep, ReplaySession


class FakeMemory:
    def __init__(self):
        self._traces = {}

    def store_trace(self, session_id, trace):
        self._traces[session_id] = trace

    def get_dag_trace(self, session_id):
        return self._traces.get(session_id)

    def list_sessions(self, limit=20):
        return list(self._traces.keys())[:limit]


class TestReplayEngine:
    def test_available_sessions_empty(self):
        mem = FakeMemory()
        engine = ReplayEngine(mem)
        assert engine.available_sessions() == []

    def test_available_sessions_with_data(self):
        mem = FakeMemory()
        mem.store_trace("s1", {
            "dag_id": "dag-1", "status": "completed",
            "nodes": [{"id": "n1", "tool": "echo"}],
            "started_at": 100.0, "completed_at": 200.0,
        })
        engine = ReplayEngine(mem)
        sessions = engine.available_sessions()
        assert len(sessions) == 1
        assert sessions[0]["session_id"] == "s1"
        assert sessions[0]["node_count"] == 1

    def test_rebuild_simple(self):
        mem = FakeMemory()
        mem.store_trace("s1", {
            "dag_id": "dag-1", "status": "completed",
            "nodes": [{"id": "n1", "tool": "echo"}, {"id": "n2", "tool": "format"}],
            "edges": [{"source": "n1", "target": "n2"}],
            "node_results": {
                "n1": {"status": "completed", "duration_ms": 100.0},
                "n2": {"status": "completed", "duration_ms": 200.0},
            },
            "started_at": 100.0, "completed_at": 200.0,
        })
        engine = ReplayEngine(mem)
        session = engine.rebuild("s1")
        assert session is not None
        assert session.session_id == "s1"
        assert session.node_count == 2
        assert len(session.steps) == 2
        assert session.steps[0].tool == "echo"
        assert session.steps[1].tool == "format"

    def test_rebuild_not_found(self):
        engine = ReplayEngine(FakeMemory())
        assert engine.rebuild("nonexistent") is None

    def test_rebuild_distributed(self):
        mem = FakeMemory()
        mem.store_trace("s1", {
            "dag_id": "dag-1", "status": "completed",
            "nodes": [{"id": "n1", "tool": "echo"}],
            "edges": [],
            "node_results": {
                "n1": {"status": "completed", "duration_ms": 100.0, "worker_id": "w1"},
            },
            "started_at": 100.0, "completed_at": 200.0,
            "distributed": {
                "worker_id": "w1",
                "execution_id": "exec-1",
                "lease_events": [{"node_id": "n1", "worker_id": "w1", "event": "leased", "timestamp": 150.0}],
                "timing_classes": {"n1": "fast"},
            },
        })
        engine = ReplayEngine(mem)
        session = engine.rebuild_distributed("s1")
        assert session is not None
        assert len(session.steps) == 1
        assert session.steps[0].worker_id == "w1"
        assert session.steps[0].timing_class == "fast"
        assert session.worker_count == 1
        assert session.unique_workers == ["w1"]

    def test_rebuild_distributed_no_distributed_key(self):
        mem = FakeMemory()
        mem.store_trace("s1", {
            "dag_id": "dag-1", "status": "completed",
            "nodes": [{"id": "n1", "tool": "echo"}],
            "edges": [],
            "node_results": {"n1": {"status": "completed", "duration_ms": 50.0}},
            "started_at": 100.0, "completed_at": 200.0,
        })
        engine = ReplayEngine(mem)
        session = engine.rebuild_distributed("s1")
        assert session is not None
        assert len(session.steps) == 1

    def test_compare_identical(self):
        mem = FakeMemory()
        trace = {
            "dag_id": "dag-1", "status": "completed",
            "nodes": [{"id": "n1", "tool": "echo"}],
            "edges": [],
            "node_results": {"n1": {"status": "completed", "duration_ms": 100.0}},
            "started_at": 100.0, "completed_at": 200.0,
        }
        mem.store_trace("s1", trace)
        mem.store_trace("s2", trace)
        engine = ReplayEngine(mem)
        result = engine.compare("s1", "s2")
        assert result["differences"] == 0

    def test_compare_different(self):
        mem = FakeMemory()
        mem.store_trace("s1", {
            "dag_id": "dag-1", "status": "completed",
            "nodes": [{"id": "n1", "tool": "echo"}], "edges": [],
            "node_results": {"n1": {"status": "completed", "duration_ms": 100.0}},
            "started_at": 100.0, "completed_at": 200.0,
        })
        mem.store_trace("s2", {
            "dag_id": "dag-1", "status": "failed",
            "nodes": [{"id": "n1", "tool": "echo"}], "edges": [],
            "node_results": {"n1": {"status": "failed", "duration_ms": 50.0, "error": "timeout"}},
            "started_at": 100.0, "completed_at": 150.0,
        })
        engine = ReplayEngine(mem)
        result = engine.compare("s1", "s2")
        assert result["differences"] >= 1

    def test_compare_not_found(self):
        engine = ReplayEngine(FakeMemory())
        result = engine.compare("nonexistent", "also-missing")
        assert "error" in result

    def test_topo_sort(self):
        nodes = [{"id": "n1"}, {"id": "n2"}, {"id": "n3"}]
        edges = [{"source": "n1", "target": "n2"}, {"source": "n2", "target": "n3"}]
        sorted_ids = ReplayEngine._topo_sort(nodes, edges)
        assert sorted_ids == ["n1", "n2", "n3"]

    def test_topo_sort_with_branches(self):
        nodes = [{"id": "n1"}, {"id": "n2"}, {"id": "n3"}]
        edges = [{"source": "n1", "target": "n2"}, {"source": "n1", "target": "n3"}]
        sorted_ids = ReplayEngine._topo_sort(nodes, edges)
        assert sorted_ids[0] == "n1"


class TestQueryReplayEngine:
    def test_log_and_get(self):
        qr = QueryReplayEngine()
        qid = qr.log("test query", "balanced", [{"id": 1}])
        log = qr.get_log(qid)
        assert log is not None
        assert log.query_text == "test query"
        assert log.strategy == "balanced"

    def test_recent(self):
        qr = QueryReplayEngine()
        qr.log("q1", "fast", [])
        qr.log("q2", "deep", [])
        recent = qr.recent()
        assert len(recent) == 2

    def test_find_similar(self):
        qr = QueryReplayEngine()
        qr.log("find the answer", "balanced", [])
        qr.log("something else", "balanced", [])
        matches = qr.find_similar("find")
        assert len(matches) == 1

    def test_compare_runs(self):
        qr = QueryReplayEngine()
        qr.log("how to sort", "fast", [], weights={"bm25": 0.5})
        qr.log("how to sort", "deep", [], weights={"bm25": 0.7})
        result = qr.compare_runs("how to sort")
        assert "weight_deltas" in result
        assert result["weight_deltas"]["bm25"] == 0.2

    def test_compare_runs_insufficient(self):
        qr = QueryReplayEngine()
        result = qr.compare_runs("rare query")
        assert "error" in result

    def test_feedback(self):
        qr = QueryReplayEngine()
        qid = qr.log("test", "balanced", [])
        assert qr.update_feedback(qid, 0.8)
        assert qr.get_log(qid).feedback == 0.8
        assert not qr.update_feedback("nonexistent", 0.5)

    def test_import_logs(self):
        qr = QueryReplayEngine()
        from core.replay.engine import QueryLog
        count = qr.import_logs([QueryLog(query_text="imported")])
        assert count == 1
        assert len(qr.recent()) == 1

    def test_log_with_weights_and_context(self):
        qr = QueryReplayEngine()
        qid = qr.log("weighted query", "hybrid", [{"id": 1}, {"id": 2}],
                      weights={"vector": 0.8}, context="repo context")
        log = qr.get_log(qid)
        assert log.weights["vector"] == 0.8
        assert log.context == "repo context"
        assert len(log.results) == 2
