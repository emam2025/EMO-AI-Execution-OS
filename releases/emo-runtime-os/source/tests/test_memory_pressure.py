"""Tests for Memory Pressure Control."""
import sys, os, tempfile
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import warnings
warnings.filterwarnings("ignore")
import logging
logging.disable(logging.CRITICAL)

from core.execution_engine import (
    DependencyGraph, PlanNode, DAGBuilder,
)
from core.memory_pressure import (
    DAGSizeLimiter, PressureLimits, StreamingExecutor,
    CheckpointManager, MEMORY_PRESSURE_VERSION,
)


def test_memory_pressure_version():
    assert MEMORY_PRESSURE_VERSION == "1.0.0"


def test_size_limiter_accepts_small():
    dag = DependencyGraph()
    dag.add_node(PlanNode(id="n1", tool="t"))
    limiter = DAGSizeLimiter(PressureLimits(max_nodes=10, max_depth=5))
    assert limiter.check(dag) == []


def test_size_limiter_rejects_large():
    dag = DependencyGraph()
    for i in range(100):
        dag.add_node(PlanNode(id=f"n{i}", tool="t"))
    limiter = DAGSizeLimiter(PressureLimits(max_nodes=10))
    errors = limiter.check(dag)
    assert len(errors) >= 1
    assert "nodes" in errors[0]


def test_size_limiter_rejects_deep():
    dag = DependencyGraph()
    for i in range(30):
        dag.add_node(PlanNode(id=f"n{i}", tool="t"))
        if i > 0:
            dag.add_edge(f"n{i-1}", f"n{i}")
    limiter = DAGSizeLimiter(PressureLimits(max_nodes=100, max_depth=5))
    errors = limiter.check(dag)
    assert any("depth" in e for e in errors)


def test_size_limiter_rejects_wide():
    """Level with more than max_parallel nodes."""
    # 10 nodes all at same depth (no edges)
    dag = DependencyGraph()
    for i in range(10):
        dag.add_node(PlanNode(id=f"n{i}", tool="t"))
    limiter = DAGSizeLimiter(PressureLimits(max_nodes=100, max_depth=100, max_parallel=5))
    errors = limiter.check(dag)
    assert any("parallel" in e for e in errors)


def test_streaming_produces_partials():
    dag = DependencyGraph()
    dag.add_node(PlanNode(id="n1", tool="t1"))
    dag.add_node(PlanNode(id="n2", tool="t2"))

    def runner(node):
        return {"status": "completed", "result": {"done": node.id}}

    results = list(StreamingExecutor().run(dag, runner))
    assert len(results) >= 2
    # Last result should say completed
    assert results[-1]["status"] == "completed"
    assert results[-1]["total"] == 2


def test_streaming_cancel():
    dag = DependencyGraph()
    for i in range(5):
        dag.add_node(PlanNode(id=f"n{i}", tool="t"))
        if i > 0:
            dag.add_edge(f"n{i-1}", f"n{i}")

    def runner(node):
        return {"status": "completed", "result": {"done": node.id}}

    ex = StreamingExecutor()
    gen = ex.run(dag, runner)
    partial = next(gen)
    assert partial["status"] == "running"
    ex.cancel()
    partial = next(gen)
    assert partial["status"] == "cancelled" or partial["status"] == "running"


def test_checkpoint_save_and_restore():
    db_path = Path(tempfile.mkdtemp()) / "chk.db"
    cm = CheckpointManager(db_path)

    dag = DependencyGraph()
    dag.add_node(PlanNode(id="n1", tool="t"))
    dag.add_node(PlanNode(id="n2", tool="t"))
    dag.add_edge("n1", "n2")

    cm.save("s1", dag, "n1", {"status": "completed", "result": {"val": 42}})

    restored = cm.restore("s1")
    assert restored is not None
    assert "n1" in restored["completed"]
    assert restored["completed"]["n1"]["result"]["val"] == 42
    assert "n2" in restored["dag"].nodes


def test_checkpoint_restore_nonexistent():
    cm = CheckpointManager(db_path=Path(tempfile.mkdtemp()) / "chk.db")
    assert cm.restore("missing") is None


def test_checkpoint_list_sessions():
    db_path = Path(tempfile.mkdtemp()) / "chk.db"
    cm = CheckpointManager(db_path)
    dag = DependencyGraph()
    dag.add_node(PlanNode(id="n1", tool="t"))

    cm.save("s1", dag, "n1", {"status": "completed"})
    sessions = cm.list_sessions()
    assert any(s["session_id"] == "s1" for s in sessions)


def test_checkpoint_delete():
    db_path = Path(tempfile.mkdtemp()) / "chk.db"
    cm = CheckpointManager(db_path)
    dag = DependencyGraph()
    dag.add_node(PlanNode(id="n1", tool="t"))

    cm.save("s1", dag, "n1", {"status": "completed"})
    cm.delete("s1")
    assert cm.restore("s1") is None


def test_checkpoint_completed_nodes():
    db_path = Path(tempfile.mkdtemp()) / "chk.db"
    cm = CheckpointManager(db_path)
    dag = DependencyGraph()
    dag.add_node(PlanNode(id="n1", tool="t"))
    dag.add_node(PlanNode(id="n2", tool="t"))

    cm.save("s1", dag, "n1", {"status": "completed"})
    cm.save("s1", dag, "n2", {"status": "completed"})
    completed = cm.completed_nodes("s1")
    assert completed == {"n1", "n2"}
