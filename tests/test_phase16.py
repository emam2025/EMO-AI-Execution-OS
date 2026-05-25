"""Tests for Phase 16: DAG Replay Engine."""
import sys, os, tempfile, json, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import warnings
warnings.filterwarnings("ignore")
import logging
logging.disable(logging.CRITICAL)

from core.execution_memory import ExecutionMemory
from core.execution_engine import (
    DependencyGraph, PlanNode, PlanEdge, NodeState,
    ExecutionEngine, ToolSpec, RetryPolicy, RollbackStrategy,
)
from core.dag_replay import DAGReplayEngine


# ── helpers ───────────────────────────────────────────────────────

def make_memory():
    tmp = tempfile.mktemp(suffix=".db")
    return ExecutionMemory(tmp)


def make_sample_dag() -> DependencyGraph:
    dag = DependencyGraph()
    dag.add_node(PlanNode(id="n1", tool="test_tool", inputs={"x": 1}))
    dag.add_node(PlanNode(id="n2", tool="test_tool", inputs={"x": 2}))
    dag.add_node(PlanNode(id="n3", tool="test_tool", inputs={"x": 3}))
    dag.add_edge("n1", "n2")
    return dag


def sample_runner(node):
    return {"result": f"ran_{node.tool}", "node_id": node.id}


# ── tests ─────────────────────────────────────────────────────────

def test_replay_available_sessions_empty():
    mem = make_memory()
    replay = DAGReplayEngine(mem)
    assert replay.available_sessions(limit=10) == []


def test_replay_available_sessions_with_trace():
    mem = make_memory()
    sid = mem.create_session("test query", strategy="balanced")

    engine = ExecutionEngine(memory=mem)
    dag = make_sample_dag()
    engine.execute(dag, session_id=sid, tool_runner=sample_runner)

    replay = DAGReplayEngine(mem)
    sessions = replay.available_sessions(limit=10)
    assert len(sessions) >= 1
    assert sessions[0]["session_id"] == sid
    assert sessions[0]["query"] == "test query"
    assert sessions[0]["node_count"] == 3


def test_replay_rebuild_steps():
    mem = make_memory()
    sid = mem.create_session("rebuild test", strategy="balanced")

    engine = ExecutionEngine(memory=mem)
    dag = make_sample_dag()
    engine.execute(dag, session_id=sid, tool_runner=sample_runner)

    replay = DAGReplayEngine(mem)
    rebuilt = replay.rebuild(sid)
    assert rebuilt is not None
    assert rebuilt.session_id == sid
    assert rebuilt.query == "rebuild test"
    assert rebuilt.node_count == 3
    assert len(rebuilt.steps) == 3
    assert rebuilt.steps[0].tool == "test_tool"
    assert rebuilt.steps[0].state == "completed"
    assert rebuilt.steps[0].duration_ms >= 0


def test_replay_rebuild_missing_session():
    mem = make_memory()
    replay = DAGReplayEngine(mem)
    assert replay.rebuild("nonexistent") is None


def test_replay_step_through():
    mem = make_memory()
    sid = mem.create_session("step through", strategy="balanced")

    mem = make_memory()
    sid = mem.create_session("step through", strategy="balanced")

    engine = ExecutionEngine(memory=mem)
    dag = make_sample_dag()
    engine.execute(dag, session_id=sid, tool_runner=sample_runner)
    mem.complete_session(sid, {"ok": True})

    replay = DAGReplayEngine(mem)
    narrative = replay.step_through(sid)
    assert len(narrative) >= 2  # START + at least 1 step
    assert narrative[0]["time"] == "START"
    assert narrative[0]["query"] == "step through"
    assert narrative[-1]["time"] == "END"

    # Each step has tool and state
    for entry in narrative[1:-1]:
        assert "tool" in entry
        assert "state" in entry
    # The last entry should show status from DAG trace
    assert narrative[-1].get("status") is not None


def test_replay_step_through_missing():
    mem = make_memory()
    replay = DAGReplayEngine(mem)
    result = replay.step_through("nonexistent")
    assert "error" in result[0]


def test_replay_visualize():
    mem = make_memory()
    sid = mem.create_session("viz test", strategy="balanced")

    engine = ExecutionEngine(memory=mem)
    dag = make_sample_dag()
    engine.execute(dag, session_id=sid, tool_runner=sample_runner)

    replay = DAGReplayEngine(mem)
    viz = replay.visualize(sid)
    assert "DAG Execution" in viz
    assert "viz test" in viz
    assert "L1" in viz  # topological level 1
    assert "L2" in viz  # topological level 2
    assert "test_tool" in viz
    assert "Edges:" in viz
    assert "n1 → n2" in viz


def test_replay_visualize_no_trace():
    mem = make_memory()
    replay = DAGReplayEngine(mem)
    viz = replay.visualize("nonexistent")
    assert "No trace" in viz


def test_replay_compare_same():
    mem = make_memory()
    sid1 = mem.create_session("compare a", strategy="balanced")
    sid2 = mem.create_session("compare b", strategy="balanced")

    engine = ExecutionEngine(memory=mem)
    dag = make_sample_dag()

    engine.execute(dag, session_id=sid1, tool_runner=sample_runner)
    engine.execute(dag, session_id=sid2, tool_runner=sample_runner)

    replay = DAGReplayEngine(mem)
    comp = replay.compare(sid1, sid2)
    assert comp.session_a == sid1
    assert comp.session_b == sid2
    assert comp.query_a == "compare a"
    assert comp.query_b == "compare b"
    assert comp.node_count_delta == 0
    assert comp.status_match is True


def test_replay_compare_different():
    mem = make_memory()
    sid1 = mem.create_session("fast", strategy="balanced")
    sid2 = mem.create_session("slow", strategy="balanced")

    engine = ExecutionEngine(memory=mem)
    dag_a = make_sample_dag()

    dag_b = DependencyGraph()
    dag_b.add_node(PlanNode(id="n1", tool="test_tool", inputs={"limit": 10}))

    engine.execute(dag_a, session_id=sid1, tool_runner=sample_runner)
    engine.execute(dag_b, session_id=sid2, tool_runner=sample_runner)

    replay = DAGReplayEngine(mem)
    comp = replay.compare(sid1, sid2)
    assert comp.node_count_delta != 0  # 3 vs 1
    assert comp.status_match is True


def test_replay_compare_missing():
    mem = make_memory()
    replay = DAGReplayEngine(mem)
    sid = mem.create_session("only", strategy="balanced")
    try:
        replay.compare(sid, "nonexistent")
        assert False, "Expected LookupError"
    except LookupError:
        pass


def test_replay_store_trace_after_execution():
    """Verify that dag_trace is stored by the engine after execute()."""
    mem = make_memory()
    sid = mem.create_session("trace storage", strategy="balanced")

    engine = ExecutionEngine(memory=mem)
    dag = make_sample_dag()
    engine.execute(dag, session_id=sid, tool_runner=sample_runner)

    trace = mem.get_dag_trace(sid)
    assert trace is not None
    assert "nodes" in trace
    assert "edges" in trace
    assert "status" in trace
    assert len(trace["nodes"]) == 3
    assert len(trace["edges"]) == 1
    assert trace["status"] == "completed"

    # Each node has execution metadata
    for nid, ndata in trace["nodes"].items():
        assert "state" in ndata
        assert "tool" in ndata
        assert ndata["state"] == "completed"


# ── run ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        ("empty sessions", test_replay_available_sessions_empty),
        ("sessions with trace", test_replay_available_sessions_with_trace),
        ("rebuild steps", test_replay_rebuild_steps),
        ("rebuild missing", test_replay_rebuild_missing_session),
        ("step through", test_replay_step_through),
        ("step through missing", test_replay_step_through_missing),
        ("visualize", test_replay_visualize),
        ("visualize no trace", test_replay_visualize_no_trace),
        ("compare same", test_replay_compare_same),
        ("compare different", test_replay_compare_different),
        ("compare missing", test_replay_compare_missing),
        ("trace storage", test_replay_store_trace_after_execution),
    ]

    passed = 0
    failed = 0
    for desc, fn in tests:
        try:
            fn()
            print(f"  ✓ {desc}")
            passed += 1
        except Exception as e:
            print(f"  ✗ {desc}: {e}")
            failed += 1

    print(f"\n{passed}/{passed + failed} passed")
    if failed:
        exit(1)
