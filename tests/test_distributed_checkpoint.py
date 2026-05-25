"""Tests for DistributedCheckpointManager and DistributedRecoveryManager."""
import sys, os, time, threading
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import warnings
warnings.filterwarnings("ignore")
import logging
logging.disable(logging.CRITICAL)

import tempfile
from pathlib import Path

from core.distributed_checkpoint import (
    DistributedCheckpointManager,
    DistributedRecoveryManager,
    DistributedCheckpoint,
    RecoveryResult,
    DISTRIBUTED_CHECKPOINT_VERSION,
)
from core.memory_pressure import CheckpointManager
from core.ownership_manager import OwnershipManager, LeaseStore
from core.worker_registry import WorkerRegistry
from core.distributed_types import WorkerNode, WorkerStatus


# ── Helpers ─────────────────────────────────────────────────────

def _make_worker(wid: str, tool: str = "agent.explain") -> WorkerNode:
    from core.execution_engine import ToolSpec
    return WorkerNode(
        id=wid,
        url=f"http://{wid}:9001",
        tools=[ToolSpec(name=tool)],
        capacity=2,
    )


def _make_dag():
    from core.execution_engine import DependencyGraph, PlanNode
    dag = DependencyGraph()
    n1 = PlanNode(id="node_1", tool="agent.explain", inputs={"q": "hello"})
    n2 = PlanNode(id="node_2", tool="graph_retrieval.ranked_hotspots", inputs={"path": "/"})
    dag.add_node(n1)
    dag.add_node(n2)
    dag.add_edge("node_1", "node_2", "success")
    return dag


def _lease_and_cleanup():
    """Return (LeaseStore, cleanup_fn) backed by a temp file."""
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    store = LeaseStore(db_path=Path(f.name))
    return store, lambda: os.unlink(f.name)


# ── DistributedCheckpointManager ────────────────────────────────

def test_dcp_version():
    dcp = DistributedCheckpointManager()
    assert dcp.version == DISTRIBUTED_CHECKPOINT_VERSION


def test_dcp_save_and_get():
    dcp = DistributedCheckpointManager()
    dag = _make_dag()

    dcp.save_node(
        session_id="sess_1",
        node_id="node_1",
        result={"status": "completed", "data": 42},
        dag=dag,
        worker_id="worker_1",
        lease_id="lease_1",
        execution_id="exec_1",
        attempt_number=0,
        completed_nodes=set(),
        current_node="node_2",
    )

    cp = dcp.get_checkpoint("sess_1")
    assert cp is not None
    assert cp.worker_id == "worker_1"
    assert cp.lease_id == "lease_1"
    assert cp.execution_id == "exec_1"
    assert cp.attempt_number == 0
    assert "node_1" in cp.completed_nodes
    assert cp.current_node == "node_2"


def test_dcp_save_multiple_nodes():
    dcp = DistributedCheckpointManager()
    dag = _make_dag()

    dcp.save_node("sess_1", "node_1", {"status": "ok"}, dag=dag,
                  completed_nodes=set(), worker_id="w1")
    dcp.save_node("sess_1", "node_2", {"status": "ok"}, dag=dag,
                  completed_nodes={"node_1"}, worker_id="w1")

    cp = dcp.get_checkpoint("sess_1")
    assert cp is not None
    assert len(cp.completed_nodes) == 2


def test_dcp_save_failure():
    dcp = DistributedCheckpointManager()
    dag = _make_dag()

    dcp.save_node("sess_1", "node_1", {"status": "ok"}, dag=dag,
                  completed_nodes=set(), worker_id="w1")
    dcp.save_failure("sess_1", "node_2", "Something broke", dag=dag,
                     worker_id="w1", completed_nodes={"node_1"})

    cp = dcp.get_checkpoint("sess_1")
    assert cp is not None
    assert cp.current_node == "node_2"
    assert cp.failure_reason == "Something broke"


def test_dcp_get_nonexistent():
    dcp = DistributedCheckpointManager()
    assert dcp.get_checkpoint("nonexistent") is None


def test_dcp_get_completed():
    dcp = DistributedCheckpointManager()
    dag = _make_dag()
    dcp.save_node("sess_1", "node_1", {"x": 1}, dag=dag)
    completed = dcp.get_completed("sess_1")
    assert "node_1" in completed


def test_dcp_clear():
    dcp = DistributedCheckpointManager()
    dag = _make_dag()
    dcp.save_node("sess_1", "node_1", {"x": 1}, dag=dag)
    assert dcp.get_checkpoint("sess_1") is not None
    dcp.clear()
    assert dcp.get_checkpoint("sess_1") is None


# ── DistributedRecoveryManager ─────────────────────────────────

def test_recover_success():
    store, cleanup = _lease_and_cleanup()
    try:
        om = OwnershipManager(lease_store=store)
        wr = WorkerRegistry()
        wr.register(_make_worker("worker_1"))
        wr.register(_make_worker("worker_2"))
        dcp = DistributedCheckpointManager()
        dag = _make_dag()

        lease = om.claim("sess_1", "worker_1", 60.0)
        assert lease is not None
        dcp.save_node("sess_1", "node_1", {"status": "ok"}, dag=dag,
                      worker_id="worker_1", lease_id=lease,
                      completed_nodes=set(), current_node="node_2")

        rm = DistributedRecoveryManager(om, wr, dcp)
        result = rm.recover("sess_1", "worker_1", "agent.explain")

        assert result.success is True
        assert result.original_worker == "worker_1"
        assert result.new_worker != ""
        assert result.new_lease_id != ""
        assert result.new_execution_id != ""
        assert result.attempt_number == 1
        assert "node_1" in result.completed_nodes
        assert result.current_node == "node_2"
    finally:
        cleanup()


def test_recover_no_checkpoint():
    store, cleanup = _lease_and_cleanup()
    try:
        om = OwnershipManager(lease_store=store)
        wr = WorkerRegistry()
        dcp = DistributedCheckpointManager()
        rm = DistributedRecoveryManager(om, wr, dcp)

        result = rm.recover("nonexistent", "worker_1")
        assert result.success is False
        assert "No checkpoint" in result.reason
    finally:
        cleanup()


def test_recover_no_available_worker():
    store, cleanup = _lease_and_cleanup()
    try:
        om = OwnershipManager(lease_store=store)
        wr = WorkerRegistry()
        dcp = DistributedCheckpointManager()
        dag = _make_dag()

        lease = om.claim("sess_1", "worker_1", 60.0)
        dcp.save_node("sess_1", "node_1", {"ok": True}, dag=dag,
                      worker_id="worker_1", lease_id=lease,
                      completed_nodes=set())

        rm = DistributedRecoveryManager(om, wr, dcp)
        result = rm.recover("sess_1", "worker_1")
        assert result.success is False
        assert "No available worker" in result.reason
    finally:
        cleanup()


def test_recover_ownership_changed():
    store, cleanup = _lease_and_cleanup()
    try:
        om = OwnershipManager(lease_store=store)
        wr = WorkerRegistry()
        wr.register(_make_worker("worker_2"))
        dcp = DistributedCheckpointManager()
        dag = _make_dag()

        lease = om.claim("sess_1", "worker_2", 60.0)
        dcp.save_node("sess_1", "node_1", {"ok": True}, dag=dag,
                      worker_id="worker_2", lease_id=lease,
                      completed_nodes=set())

        rm = DistributedRecoveryManager(om, wr, dcp)
        result = rm.recover("sess_1", "worker_1")
        assert result.success is False
        assert "now owned by" in result.reason
    finally:
        cleanup()


def test_recover_increments_attempt():
    store, cleanup = _lease_and_cleanup()
    try:
        om = OwnershipManager(lease_store=store)
        wr = WorkerRegistry()
        wr.register(_make_worker("worker_1"))
        wr.register(_make_worker("worker_2"))
        dcp = DistributedCheckpointManager()
        dag = _make_dag()

        lease = om.claim("sess_1", "worker_1", 60.0, attempt_number=0)
        dcp.save_node("sess_1", "node_1", {"ok": True}, dag=dag,
                      worker_id="worker_1", lease_id=lease,
                      attempt_number=0, completed_nodes=set())

        rm = DistributedRecoveryManager(om, wr, dcp)
        result = rm.recover("sess_1", "worker_1")
        assert result.success is True
        assert result.attempt_number == 1
    finally:
        cleanup()


def test_can_recover():
    store, cleanup = _lease_and_cleanup()
    try:
        om = OwnershipManager(lease_store=store)
        wr = WorkerRegistry()
        wr.register(_make_worker("worker_1"))
        dcp = DistributedCheckpointManager()
        dag = _make_dag()

        lease = om.claim("sess_1", "worker_1", 60.0)
        dcp.save_node("sess_1", "node_1", {"ok": True}, dag=dag,
                      worker_id="worker_1", lease_id=lease,
                      completed_nodes=set())

        rm = DistributedRecoveryManager(om, wr, dcp)
        assert rm.can_recover("sess_1", "worker_1") is True
        assert rm.can_recover("sess_1", "other_worker") is False
        assert rm.can_recover("nonexistent", "worker_1") is False
    finally:
        cleanup()
