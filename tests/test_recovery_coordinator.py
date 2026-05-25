"""Tests for RecoveryCoordinator, ResumeToken, and DeterministicResume."""
import sys, os, json, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import warnings
warnings.filterwarnings("ignore")
import logging
logging.disable(logging.CRITICAL)

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

# Reusable mock engine for RecoveryCoordinator tests
# (RecoveryCoordinator stores but does not use the engine during detection/recovery)
_mock_engine = MagicMock()

from core.recovery_coordinator import (
    RecoveryCoordinator,
    ResumeToken,
    DeterministicResume,
    FailedTask,
    RECOVERY_COORDINATOR_VERSION,
)
from core.ownership_manager import OwnershipManager, LeaseStore
from core.worker_registry import WorkerRegistry
from core.distributed_checkpoint import (
    DistributedCheckpointManager,
    DistributedCheckpoint,
)
from core.distributed_types import WorkerNode, WorkerStatus
from core.execution_engine import (
    ExecutionEngine, DependencyGraph, PlanNode,
    NodeConfig, NodeState, ToolSpec,
)
from core.execution_cache import ExecutionCache


# ── Helpers ─────────────────────────────────────────────────────

def _lease_store():
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    return LeaseStore(db_path=Path(f.name)), lambda: os.unlink(f.name)


def _make_worker(wid: str, tool: str = "agent.explain") -> WorkerNode:
    from core.execution_engine import ToolSpec as TS
    return WorkerNode(
        id=wid,
        url=f"http://{wid}:9001",
        tools=[TS(name=tool)],
        capacity=2,
    )


def _make_dag() -> DependencyGraph:
    dag = DependencyGraph()
    dag.add_node(PlanNode(id="n1", tool="agent.explain", inputs={"q": "hi"}))
    dag.add_node(PlanNode(id="n2", tool="graph_retrieval.ranked_hotspots", inputs={"p": "/"}))
    dag.add_edge("n1", "n2", "success")
    return dag


# ── ResumeToken ─────────────────────────────────────────────────

def test_resume_token_basic():
    token = ResumeToken(
        execution_id="exec_1",
        session_id="sess_1",
        completed_nodes=["n1"],
        pending_nodes=["n2"],
        node_results={"n1": {"status": "ok"}},
    )
    assert token.execution_id == "exec_1"
    assert token.completed_nodes == ["n1"]
    assert token.pending_nodes == ["n2"]
    assert token.node_results == {"n1": {"status": "ok"}}


def test_resume_token_serialization():
    token = ResumeToken(
        execution_id="exec_1",
        session_id="sess_1",
        completed_nodes=["n1"],
        pending_nodes=["n2"],
        node_results={"n1": {"x": 1}},
    )
    d = token.to_dict()
    assert d["execution_id"] == "exec_1"

    json_str = token.to_json()
    restored = ResumeToken.from_json(json_str)
    assert restored.execution_id == "exec_1"
    assert restored.completed_nodes == ["n1"]
    assert restored.pending_nodes == ["n2"]


def test_resume_token_is_empty():
    assert ResumeToken(execution_id="e1").is_empty is True
    t = ResumeToken(execution_id="e1", completed_nodes=["n1"])
    assert t.is_empty is False


def test_resume_token_is_complete():
    t1 = ResumeToken(execution_id="e1")
    assert t1.is_complete is True

    t2 = ResumeToken(execution_id="e1", pending_nodes=["n2"])
    assert t2.is_complete is False

    t3 = ResumeToken(execution_id="e1", completed_nodes=["n1"])
    assert t3.is_complete is True


# ── DistributedCheckpoint compatibility ─────────────────────────

def test_dcp_to_resume_token():
    dcp = DistributedCheckpoint(
        task_id="t1",
        session_id="sess_1",
        worker_id="w1",
        lease_id="l1",
        execution_id="exec_1",
        attempt_number=0,
        completed_nodes={"n1"},
        node_results={"n1": {"status": "ok"}},
        current_node="n2",
        failure_reason="",
    )
    token = ResumeToken(
        execution_id=dcp.execution_id,
        session_id=dcp.session_id,
        completed_nodes=list(dcp.completed_nodes),
        pending_nodes=[dcp.current_node] if dcp.current_node else [],
        node_results=dict(dcp.node_results),
    )
    assert token.completed_nodes == ["n1"]
    assert token.pending_nodes == ["n2"]


# ── RecoveryCoordinator ─────────────────────────────────────────

def test_coordinator_version():
    om = OwnershipManager()
    wr = WorkerRegistry()
    dcp = DistributedCheckpointManager()
    rc = RecoveryCoordinator(_mock_engine, om, wr, dcp)
    assert rc.version == RECOVERY_COORDINATOR_VERSION


def test_detect_expired_leases():
    store, cleanup = _lease_store()
    try:
        om = OwnershipManager(lease_store=store)
        wr = WorkerRegistry()
        wr.register(_make_worker("w1"))
        dcp = DistributedCheckpointManager()

        # Claim with very short duration so it expires
        lease = om.claim("task_1", "w1", lease_duration=0.01)
        assert lease is not None

        # Save a checkpoint
        from core.execution_engine import DependencyGraph as DG, PlanNode as PN
        dag = DG()
        dag.add_node(PN(id="n1", tool="agent.explain"))
        dcp.save_node("task_1", "n1", {"status": "ok"}, dag=dag,
                      worker_id="w1", lease_id=lease)

        time.sleep(0.05)  # let lease expire

        rc = RecoveryCoordinator(_mock_engine, om, wr, dcp)
        failures = rc.detect_failures()
        assert len(failures) > 0
        assert failures[0].failure_type == "lease_expired"
    finally:
        cleanup()


def test_detect_incomplete_executions():
    store, cleanup = _lease_store()
    try:
        om = OwnershipManager(lease_store=store)
        wr = WorkerRegistry()
        dcp = DistributedCheckpointManager()
        from core.execution_engine import DependencyGraph as DG, PlanNode as PN
        dag = DG()
        dag.add_node(PN(id="n1", tool="agent.explain"))

        # Save a checkpoint with completed nodes and current_node
        dcp.save_node("sess_1", "n1", {"status": "ok"}, dag=dag,
                      worker_id="w1", lease_id="l1",
                      completed_nodes=set(), current_node="n2")

        rc = RecoveryCoordinator(_mock_engine, om, wr, dcp)
        failures = rc.detect_failures()
        # Should detect as incomplete
        has_incomplete = any(
            f.failure_type == "incomplete" for f in failures
        )
        assert has_incomplete is True
    finally:
        cleanup()


def test_recover_returns_token():
    store, cleanup = _lease_store()
    try:
        om = OwnershipManager(lease_store=store)
        wr = WorkerRegistry()
        wr.register(_make_worker("w1"))
        wr.register(_make_worker("w2"))
        dcp = DistributedCheckpointManager()
        from core.execution_engine import DependencyGraph as DG, PlanNode as PN
        dag = DG()
        dag.add_node(PN(id="n1", tool="agent.explain"))

        lease = om.claim("task_1", "w1", lease_duration=60.0)
        dcp.save_node("task_1", "n1", {"status": "ok"}, dag=dag,
                      worker_id="w1", lease_id=lease,
                      completed_nodes=set(), current_node="n2")

        rc = RecoveryCoordinator(_mock_engine, om, wr, dcp)
        failed = FailedTask(
            task_id="task_1",
            worker_id="w1",
            failure_type="worker_dead",
        )
        token = rc.recover(failed)
        assert token is not None
        assert token.execution_id != ""
        assert token.attempt_number == 1  # incremented
        assert "n1" in token.completed_nodes
    finally:
        cleanup()


def test_recover_no_checkpoint():
    store, cleanup = _lease_store()
    try:
        om = OwnershipManager(lease_store=store)
        wr = WorkerRegistry()
        dcp = DistributedCheckpointManager()
        rc = RecoveryCoordinator(_mock_engine, om, wr, dcp)

        failed = FailedTask(
            task_id="nonexistent",
            worker_id="w1",
            failure_type="worker_dead",
        )
        token = rc.recover(failed)
        assert token is None
    finally:
        cleanup()


def test_recover_concurrent_guard():
    store, cleanup = _lease_store()
    try:
        om = OwnershipManager(lease_store=store)
        wr = WorkerRegistry()
        dcp = DistributedCheckpointManager()
        rc = RecoveryCoordinator(_mock_engine, om, wr, dcp)

        # Same task twice should return None second time
        failed = FailedTask(task_id="t1", worker_id="w1", failure_type="lease_expired")
        rc._recovering.add("t1")
        token = rc.recover(failed)
        assert token is None
    finally:
        cleanup()


# ── DeterministicResume ─────────────────────────────────────────

def test_resume_marks_completed():
    engine = ExecutionEngine(tool_registry={}, cache=ExecutionCache())
    dr = DeterministicResume(engine)
    dag = _make_dag()

    token = ResumeToken(
        execution_id="exec_1",
        completed_nodes=["n1"],
        pending_nodes=["n2"],
        node_results={"n1": {"result": 42}},
    )

    dr.resume(token, dag)

    # n1 should be COMPLETED with result
    n1 = dag.nodes["n1"]
    assert n1.state == NodeState.COMPLETED
    assert n1.result == {"result": 42}


def test_resume_marks_failed_as_pending():
    engine = ExecutionEngine(tool_registry={}, cache=ExecutionCache())
    dr = DeterministicResume(engine)
    dag = _make_dag()

    token = ResumeToken(
        execution_id="exec_1",
        completed_nodes=["n1"],
        pending_nodes=[],
        failed_nodes=["n2"],
        node_results={
            "n1": {"result": 42},
            "n2": {"error": "timeout"},
        },
    )

    dr.resume(token, dag)

    # n2 should be PENDING (reset for retry)
    n2 = dag.nodes["n2"]
    assert n2.state == NodeState.PENDING
    assert n2.error is None


def test_build_dag_from_token():
    token = ResumeToken(
        execution_id="exec_1",
        completed_nodes=["n1"],
        pending_nodes=["n2"],
        node_results={"n1": {"result": 42}},
    )

    dag = DeterministicResume.build_dag_from_token(token, tool="agent.explain")
    assert dag is not None
    assert "n1" in dag.nodes
    assert "n2" in dag.nodes
    assert dag.nodes["n1"].state == NodeState.COMPLETED
    assert dag.nodes["n2"].state == NodeState.PENDING
