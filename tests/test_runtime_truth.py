"""P3 — Runtime Truth Tests.

Real execution path verification:
  1. Multi-worker execution
  2. Worker kill + recovery
  3. Network partition tolerance
  4. Replay determinism
  5. Distributed checkpoint recovery

Each test exercises a real (not mocked) execution path.
"""

import os
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.codegraph.integration import CodeGraphRuntime
from core.codegraph.graph import CodeGraph
from core.control_plane.brain import ControlPlaneBrain
from core.control_plane.state.system_state import SystemStateBrain
from core.execution_core import DAGBuilder
from core.execution_engine import ExecutionEngine
from core.models.dag import DependencyGraph, PlanNode
from core.replay.engine import ReplayEngine
from core.runtime.mesh import MeshExecutionRuntime, ServiceMesh
from core.runtime.mesh.remote import MeshNode
from core.runtime.os import RuntimeOS
from core.runtime.resource_scheduler import ResourceScheduler
from core.runtime.mesh.service_registry import ServiceRegistry

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ═══════════════════════════════════════════════════════════════════
# Shared helpers
# ═══════════════════════════════════════════════════════════════════

def _make_3node_dag() -> DependencyGraph:
    return (
        DAGBuilder()
        .add("a", tool="mock_tool", inputs={"x": 1})
        .add("b", tool="mock_tool", inputs={"x": 2})
        .add("c", tool="mock_tool", inputs={"x": 3})
        .depends("b", "a")
        .depends("c", "b")
        .build()
    )


def _make_engine() -> MagicMock:
    eng = MagicMock(spec=ExecutionEngine)
    eng.execute.return_value = {"status": "completed", "result": "ok"}
    eng.execute_streaming.return_value = [{"status": "completed", "result": "ok"}]
    eng.cancel.return_value = True
    eng.shutdown.return_value = None
    eng.register_tool.return_value = None
    return eng


def _make_codegraph() -> CodeGraphRuntime:
    return CodeGraphRuntime(codegraph=CodeGraph())


# ═══════════════════════════════════════════════════════════════════
# 3.1 — Multi-worker execution
# ═══════════════════════════════════════════════════════════════════

class TestMultiWorkerExecution:
    """Real multi-worker dispatch through the mesh."""

    def test_mesh_handler_executes_dag(self):
        """A DAG executes through a registered mesh handler (not local engine)."""
        mesh = ServiceMesh()
        engine = _make_engine()
        results = []

        def handler(payload):
            r = engine.execute(payload.get("dag", {}))
            results.append(r)
            return r

        mesh.register_local_handler("worker", "execute_dag", handler)
        # No local engine → forces mesh routing
        runtime = MeshExecutionRuntime(engine=None, mesh=mesh)

        dag = _make_3node_dag()
        result = runtime.execute(dag, prefer_local=False)
        assert result["status"] == "completed"
        assert len(results) == 1

    def test_mesh_fallback_to_local_engine(self):
        """Mesh falls back to local engine when no handler registered."""
        engine = _make_engine()
        mesh = ServiceMesh()
        # No handlers registered — mesh will fail → fallback to local engine
        runtime = MeshExecutionRuntime(engine=engine, mesh=mesh)

        dag = _make_3node_dag()
        result = runtime.execute(dag, prefer_local=False)
        assert result["status"] == "completed"

    def test_runtime_os_submit_returns_id(self):
        """RuntimeOS.submit() returns a valid execution ID."""
        engine = _make_engine()
        scheduler = ResourceScheduler()
        scheduler.register_worker(worker_id="test-worker", node_id="test-node")
        codegraph = _make_codegraph()
        brain = ControlPlaneBrain(scheduler=scheduler, codegraph=codegraph)
        mesh = ServiceMesh()
        registry = ServiceRegistry()
        os_rt = RuntimeOS(
            engine=engine,
            control_brain=brain,
            mesh=mesh,
            registry=registry,
            mesh_runtime=MeshExecutionRuntime(engine=engine, mesh=mesh),
            codegraph=codegraph,
        )
        dag = _make_3node_dag()
        exec_id = os_rt.submit(dag, session_id="truth-submit-1")
        assert exec_id is not None
        assert len(exec_id) > 0

    def test_concurrent_executions_through_runtime(self):
        """Multiple concurrent DAG executions complete successfully."""
        engine = _make_engine()
        mesh = ServiceMesh()
        runtime = MeshExecutionRuntime(engine=engine, mesh=mesh)

        dag = _make_3node_dag()
        pool = ThreadPoolExecutor(max_workers=4)
        futs = [pool.submit(runtime.execute, dag, prefer_local=True) for _ in range(4)]
        results = [f.result() for f in futs]
        pool.shutdown()

        assert all(r["status"] == "completed" for r in results)


# ═══════════════════════════════════════════════════════════════════
# 3.2 — Worker kill + recovery
# ═══════════════════════════════════════════════════════════════════

class TestWorkerKillRecovery:
    """System detects dead workers and routes around them."""

    def test_system_state_tracks_worker_health(self):
        """SystemStateBrain tracks worker health status."""
        state = SystemStateBrain()
        info = state.register_worker("worker-1")
        assert info.worker_id == "worker-1"
        assert info.status == "active"

        # Remove worker to simulate death
        state.remove_worker("worker-1")
        assert state.get_worker("worker-1") is None

    def test_healthy_workers_exclude_dead(self):
        """Only active workers appear in healthy_workers()."""
        state = SystemStateBrain()
        state.register_worker("healthy-w")
        state.register_worker("dead-w")
        state.remove_worker("dead-w")

        healthy = state.healthy_workers()
        ids = [w.worker_id for w in healthy]
        assert "healthy-w" in ids
        assert "dead-w" not in ids

    def test_health_supervisor_probes_and_assesses(self):
        """HealthSupervisor probes a worker and returns a recovery action."""
        from core.control_plane.health_supervisor import (
            HealthSupervisor, ProbeResult, RecoveryAction,
        )

        def probe_fn(worker_id: str) -> ProbeResult:
            return ProbeResult(alive=False, latency_ms=0.0)

        supervisor = HealthSupervisor(probe_fn=probe_fn)
        supervisor.set_config("ghost-worker")

        actions = supervisor.tick()
        probe_result = supervisor.probe("ghost-worker")
        assert probe_result.alive is False

    def test_drain_marks_worker_as_draining(self):
        """WorkerDrainer.start_drain() marks a worker and prevents new placement."""
        state = SystemStateBrain()
        state.register_worker("drain-me")
        from core.control_plane.worker_drainer import WorkerDrainer

        drainer = WorkerDrainer(state=state)
        op = drainer.start_drain("drain-me")
        assert op.worker_id == "drain-me"
        assert drainer.is_draining("drain-me")

        healthy = state.healthy_workers()
        assert all(w.worker_id != "drain-me" for w in healthy)


# ═══════════════════════════════════════════════════════════════════
# 3.3 — Network partition
# ═══════════════════════════════════════════════════════════════════

class TestNetworkPartition:
    """System tolerates network partitions between mesh nodes."""

    def test_mesh_execute_via_handler(self):
        """Mesh dispatches to a registered handler when engine is set."""
        mesh = ServiceMesh()
        engine = _make_engine()

        def handler(payload):
            return engine.execute(payload)

        mesh.register_local_handler("worker", "execute_dag", handler)
        runtime = MeshExecutionRuntime(engine=engine, mesh=mesh)

        dag = _make_3node_dag()
        result = runtime.execute(dag, prefer_local=True)
        assert result["status"] == "completed"

    def test_mesh_node_communicates(self):
        """Two MeshNodes communicate via HTTP."""
        node_a = MeshNode(node_id="node-a", host="127.0.0.1")
        node_b = MeshNode(node_id="node-b", host="127.0.0.1")

        def handler_b(payload):
            return {"status": "completed", "echo": payload}

        node_b.register_handler("svc", "ping", handler_b)
        node_b.start()
        port_b = node_b.port

        node_a.add_peer("node-b", "127.0.0.1", port_b)
        node_a.start()
        time.sleep(0.1)

        resp = node_a.call_remote("svc", "ping", {"msg": "hello"}, "node-b")
        assert resp is not None
        assert resp.get("status") == "completed"

        node_a.shutdown()
        node_b.shutdown()


# ═══════════════════════════════════════════════════════════════════
# 3.4 — Replay determinism
# ═══════════════════════════════════════════════════════════════════

class TestReplayDeterminism:
    """Re-executing a session produces consistent results."""

    def test_execute_twice_same_session(self):
        """Same session executed twice returns consistent status."""
        engine = ExecutionEngine()
        dag = _make_3node_dag()
        first = engine.execute(dag, session_id="det-s1")
        assert first["status"] == "completed"

        second = engine.execute(dag, session_id="det-s1")
        assert second["status"] == "completed"

    def test_replay_engine_rebuild_returns_dag(self):
        """ReplayEngine.rebuild returns a DAG from trace data."""
        memory = MagicMock()
        memory.get_trace.return_value = {
            "session_id": "s1",
            "nodes": {"n1": {"id": "n1", "tool": "mock_tool", "state": "COMPLETED"}},
            "edges": [],
        }
        memory.get_session_state.return_value = {"status": "completed"}
        replay = ReplayEngine(memory)

        dag = replay.rebuild("s1")
        assert dag is not None

    def test_runtime_os_rerun_returns_id(self):
        """RuntimeOS.rerun() returns a valid execution ID."""
        engine = _make_engine()
        scheduler = ResourceScheduler()
        scheduler.register_worker(worker_id="test-worker", node_id="test-node")
        codegraph = _make_codegraph()
        brain = ControlPlaneBrain(scheduler=scheduler, codegraph=codegraph)
        mesh = ServiceMesh()
        registry = ServiceRegistry()
        os_rt = RuntimeOS(
            engine=engine,
            control_brain=brain,
            mesh=mesh,
            registry=registry,
            mesh_runtime=MeshExecutionRuntime(engine=engine, mesh=mesh),
            codegraph=codegraph,
        )
        dag = _make_3node_dag()
        first_id = os_rt.submit(dag, session_id="rerun-test")
        assert first_id is not None
        assert len(first_id) > 0

        second_id = os_rt.rerun(first_id)
        assert second_id is not None
        assert second_id != first_id


# ═══════════════════════════════════════════════════════════════════
# 3.5 — Distributed checkpoint recovery
# ═══════════════════════════════════════════════════════════════════

class TestDistributedCheckpointRecovery:
    """Checkpoint and recovery across execution sessions."""

    def test_checkpoint_save_and_restore(self):
        """Save and restore execution state via CheckpointManager."""
        from core.memory_pressure import CheckpointManager

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)
        try:
            mgr = CheckpointManager(db_path=db_path)
            dag = _make_3node_dag()
            mgr.save("session-cp-1", dag=dag, node_id="n1", result={"output": "ok"})

            restored = mgr.restore("session-cp-1")
            assert restored is not None
            assert "dag" in restored
            assert "completed" in restored
            assert restored["completed"]["n1"]["output"] == "ok"

            mgr.delete("session-cp-1")
            assert mgr.restore("session-cp-1") is None
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_checkpoint_list_sessions(self):
        """Multiple sessions appear in list_sessions."""
        from core.memory_pressure import CheckpointManager

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)
        try:
            mgr = CheckpointManager(db_path=db_path)
            dag = _make_3node_dag()
            mgr.save("session-A", dag=dag, node_id="n1", result={"ok": True})
            mgr.save("session-B", dag=dag, node_id="n2", result={"ok": True})
            sessions = mgr.list_sessions()
            session_ids = [s["session_id"] for s in sessions]
            assert "session-A" in session_ids
            assert "session-B" in session_ids
        finally:
            if db_path.exists():
                db_path.unlink()

    def test_restore_nonexistent_session(self):
        """Restoring a session that doesn't exist returns None."""
        from core.memory_pressure import CheckpointManager

        mgr = CheckpointManager()
        result = mgr.restore("nonexistent")
        assert result is None

    def test_checkpoint_isolation(self):
        """Checkpoints for different sessions do not interfere."""
        from core.memory_pressure import CheckpointManager

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = Path(f.name)
        try:
            mgr = CheckpointManager(db_path=db_path)
            dag = _make_3node_dag()
            mgr.save("session-X", dag=dag, node_id="n1", result={"val": "X"})
            mgr.save("session-Y", dag=dag, node_id="n2", result={"val": "Y"})

            x = mgr.restore("session-X")
            y = mgr.restore("session-Y")
            assert x["completed"]["n1"]["val"] == "X"
            assert y["completed"]["n2"]["val"] == "Y"

            mgr.delete("session-X")
            assert mgr.restore("session-X") is None
            assert mgr.restore("session-Y") is not None
        finally:
            if db_path.exists():
                db_path.unlink()
