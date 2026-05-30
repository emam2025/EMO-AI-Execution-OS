"""Tests for DistributedReplayEngine — deterministic distributed replay."""
import sys, os, json, time, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import warnings
warnings.filterwarnings("ignore")
import logging
logging.disable(logging.CRITICAL)
from pathlib import Path

from core.distributed_replay import (
    DistributedReplayEngine,
    DistributedReplaySession,
    DistributedReplayStep,
    DistributedRunComparison,
    LeaseEvent, LeaseEventType,
    TimingClass, classify_timing,
    DISTRIBUTED_REPLAY_VERSION,
)
from core.execution_memory import ExecutionMemory
from core.execution_engine import (
    DependencyGraph, PlanNode, NodeState,
)


# ── Helpers ─────────────────────────────────────────────────────

def _memory():
    """Create an ExecutionMemory backed by a temp file."""
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    mem = ExecutionMemory(db_path=f.name)
    return mem, lambda: os.unlink(f.name)


def _make_trace(**overrides) -> dict:
    """Build a minimal distributed execution trace."""
    trace = {
        "nodes": {
            "node_1": {
                "id": "node_1",
                "tool": "agent.explain",
                "inputs": {"q": "hello"},
                "state": "completed",
                "started_at": 1000.0,
                "completed_at": 1000.05,
                "retry_count": 0,
                "attempt_number": 0,
                "execution_id": "exec_1",
                "worker_id": "w1",
                "error": None,
                "result": {"explanation": "hello world"},
            },
            "node_2": {
                "id": "node_2",
                "tool": "graph_retrieval.ranked_hotspots",
                "inputs": {"path": "/"},
                "state": "completed",
                "started_at": 1000.1,
                "completed_at": 1000.5,
                "retry_count": 1,
                "attempt_number": 0,
                "execution_id": "exec_2",
                "worker_id": "w2",
                "error": None,
                "result": {"hotspots": ["a", "b"]},
            },
        },
        "edges": [
            {"source": "node_1", "target": "node_2", "condition": "success"},
        ],
        "status": "completed",
        "distributed": {
            "workers": {"w1": "http://w1:9001", "w2": "http://w2:9001"},
            "leases": [
                {
                    "event_type": "claim",
                    "task_id": "node_1",
                    "worker_id": "w1",
                    "lease_id": "lease_1",
                    "execution_id": "exec_1",
                    "attempt_number": 0,
                    "timestamp": 1000.0,
                    "duration_ms": 0.0,
                },
                {
                    "event_type": "claim",
                    "task_id": "node_2",
                    "worker_id": "w2",
                    "lease_id": "lease_2",
                    "execution_id": "exec_2",
                    "attempt_number": 0,
                    "timestamp": 1000.1,
                    "duration_ms": 0.0,
                },
                {
                    "event_type": "release",
                    "task_id": "node_1",
                    "worker_id": "w1",
                    "lease_id": "lease_1",
                    "execution_id": "exec_1",
                    "attempt_number": 0,
                    "timestamp": 1000.06,
                    "duration_ms": 0.0,
                },
            ],
            "total_retries": 1,
            "timing_classes": {"fast": 1, "medium": 1},
        },
    }
    trace.update(overrides)
    return trace


def _seed_memory(memory, session_id: str, trace: dict) -> None:
    """Store a session and trace in ExecutionMemory."""
    # Use a fixed session_id by manipulating internal state
    memory._insert_session(session_id, "test query", "test", 1000.0, {})
    memory._update_session(session_id, "completed", 1000.6,
                           {"test": True}, None)
    memory.store_dag_trace(session_id, trace)


# ── classify_timing ────────────────────────────────────────────

def test_classify_timing_fast():
    assert classify_timing(50) == TimingClass.FAST


def test_classify_timing_medium():
    assert classify_timing(500) == TimingClass.MEDIUM


def test_classify_timing_slow():
    assert classify_timing(5000) == TimingClass.SLOW


def test_classify_timing_timeout():
    assert classify_timing(60000) == TimingClass.TIMEOUT


# ── DistributedReplayEngine ────────────────────────────────────

def test_version():
    mem, _ = _memory()
    engine = DistributedReplayEngine(mem)
    assert engine.version == DISTRIBUTED_REPLAY_VERSION


def test_rebuild_full_session():
    mem, _ = _memory()
    trace = _make_trace()
    _seed_memory(mem, "sess_1", trace)

    engine = DistributedReplayEngine(mem)
    session = engine.rebuild("sess_1")

    assert session is not None
    assert session.session_id == "sess_1"
    assert session.node_count == 2
    assert session.edge_count == 1
    assert session.status == "completed"
    assert session.total_retries == 1
    assert session.worker_count == 2


def test_rebuild_missing_session():
    mem, _ = _memory()
    engine = DistributedReplayEngine(mem)
    assert engine.rebuild("nonexistent") is None


def test_rebuild_returns_steps():
    mem, _ = _memory()
    trace = _make_trace()
    _seed_memory(mem, "sess_1", trace)

    engine = DistributedReplayEngine(mem)
    session = engine.rebuild("sess_1")

    assert len(session.steps) == 2
    n1 = session.steps[0]
    assert n1.node_id == "node_1"
    assert n1.tool == "agent.explain"
    assert n1.worker_id == "w1"
    assert n1.timing_class == "fast"
    assert n1.attempt_number == 0

    n2 = session.steps[1]
    assert n2.node_id == "node_2"
    assert n2.tool == "graph_retrieval.ranked_hotspots"
    assert n2.worker_id == "w2"
    assert n2.timing_class == "medium"
    assert n2.retry_count == 1


def test_rebuild_includes_lease_events():
    mem, _ = _memory()
    trace = _make_trace()
    _seed_memory(mem, "sess_1", trace)

    engine = DistributedReplayEngine(mem)
    session = engine.rebuild("sess_1")

    assert len(session.ownership_timeline) == 3
    assert session.ownership_timeline[0].event_type == LeaseEventType.CLAIM
    assert session.ownership_timeline[0].worker_id == "w1"


def test_rebuild_timing_distribution():
    mem, _ = _memory()
    trace = _make_trace()
    _seed_memory(mem, "sess_1", trace)

    engine = DistributedReplayEngine(mem)
    session = engine.rebuild("sess_1")

    assert session.timing_distribution == {"fast": 1, "medium": 1}


def test_rebuild_without_distributed_key():
    """Should still work if no 'distributed' key in trace."""
    mem, _ = _memory()
    trace = _make_trace()
    del trace["distributed"]
    _seed_memory(mem, "sess_1", trace)

    engine = DistributedReplayEngine(mem)
    session = engine.rebuild("sess_1")

    assert session is not None
    assert session.worker_count == 0
    assert session.ownership_timeline == []


def test_available_sessions():
    mem, _ = _memory()
    trace = _make_trace()
    _seed_memory(mem, "sess_1", trace)

    engine = DistributedReplayEngine(mem)
    sessions = engine.available_sessions()
    assert len(sessions) == 1
    assert sessions[0]["session_id"] == "sess_1"
    assert sessions[0]["worker_count"] == 2
    assert sessions[0]["total_retries"] == 1


def test_timing_report():
    mem, _ = _memory()
    trace = _make_trace()
    _seed_memory(mem, "sess_1", trace)

    engine = DistributedReplayEngine(mem)
    report = engine.timing_report("sess_1")

    assert report is not None
    assert report["session_id"] == "sess_1"
    assert report["total_retries"] == 1
    assert len(report["steps"]) == 2
    assert report["steps"][0]["timing_class"] == "fast"
    assert report["steps"][1]["timing_class"] == "medium"


def test_timing_report_missing():
    mem, _ = _memory()
    engine = DistributedReplayEngine(mem)
    assert engine.timing_report("nonexistent") is None


def test_ownership_timeline():
    mem, _ = _memory()
    trace = _make_trace()
    _seed_memory(mem, "sess_1", trace)

    engine = DistributedReplayEngine(mem)
    timeline = engine.ownership_timeline("sess_1")

    assert timeline is not None
    assert len(timeline) == 3
    assert timeline[0]["event_type"] == "claim"
    assert timeline[2]["event_type"] == "release"


def test_ownership_timeline_missing():
    mem, _ = _memory()
    engine = DistributedReplayEngine(mem)
    assert engine.ownership_timeline("nonexistent") is None


def test_compare_same():
    mem, _ = _memory()
    trace = _make_trace()
    _seed_memory(mem, "sess_1", trace)
    _seed_memory(mem, "sess_2", trace)

    engine = DistributedReplayEngine(mem)
    comp = engine.compare("sess_1", "sess_2")

    assert comp is not None
    assert comp.status_match is True
    assert comp.ownership_match is True
    assert comp.retry_count_delta == 0
    assert comp.total_duration_delta_ms == 0


def test_compare_different():
    mem, _ = _memory()
    trace_a = _make_trace()
    trace_b = _make_trace(
        nodes={
            "node_1": {
                "id": "node_1",
                "tool": "agent.explain",
                "inputs": {"q": "hello"},
                "state": "failed",
                "started_at": 1000.0,
                "completed_at": 1000.5,
                "retry_count": 2,
                "attempt_number": 0,
                "execution_id": "exec_1",
                "worker_id": "w1",
                "error": "timeout",
                "result": None,
            },
        },
        edges=[],
        distributed={
            "workers": {"w1": "http://w1:9001"},
            "leases": [],
            "total_retries": 2,
            "timing_classes": {"medium": 1},
        },
    )
    _seed_memory(mem, "sess_a", trace_a)
    _seed_memory(mem, "sess_b", trace_b)

    engine = DistributedReplayEngine(mem)
    comp = engine.compare("sess_a", "sess_b")

    assert comp is not None
    assert comp.tool_diff is not None
    # node_count differs: sess_a has 2, sess_b has 1
    assert comp.node_count_delta == -1
    # Different state, different tools, different workers
    assert comp.status_match is True  # both "completed" overall
    assert comp.ownership_match is False


def test_compare_missing():
    mem, _ = _memory()
    engine = DistributedReplayEngine(mem)
    assert engine.compare("missing_a", "missing_b") is None
