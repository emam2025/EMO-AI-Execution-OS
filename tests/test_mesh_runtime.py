"""Service Mesh Runtime — integration tests.

Tests that the mesh actually routes and executes DAGs through workers.
"""

import time
from unittest.mock import MagicMock, patch

import pytest

from core.models.dag import DependencyGraph
from core.runtime.mesh import (
    ServiceMesh,
    MeshExecutionRuntime,
    MeshWorker,
)
from core.runtime.os import RuntimeOS


# ═══════════════════════════════════════════════════════════════════
# MeshExecutionRuntime
# ═══════════════════════════════════════════════════════════════════

class TestMeshExecutionRuntime:
    def test_execute_local_preferred(self):
        engine = MagicMock()
        engine.execute.return_value = {"status": "completed", "result": "ok"}
        runtime = MeshExecutionRuntime(engine=engine)
        dag = DependencyGraph()
        result = runtime.execute(dag, strategy="fast")
        assert result["status"] == "completed"
        engine.execute.assert_called_once()

    def test_execute_falls_back_when_no_engine(self):
        mesh = ServiceMesh()
        runtime = MeshExecutionRuntime(engine=None, mesh=mesh)
        dag = DependencyGraph()
        with pytest.raises(Exception):
            runtime.execute(dag)

    def test_execute_local_false_with_no_workers_falls_back(self):
        engine = MagicMock()
        engine.execute.return_value = {"status": "completed"}
        mesh = ServiceMesh()
        runtime = MeshExecutionRuntime(engine=engine, mesh=mesh)
        dag = DependencyGraph()
        result = runtime.execute(dag, prefer_local=False)
        assert result["status"] == "completed"

    def test_execute_remote_unknown_worker_raises(self):
        engine = MagicMock()
        mesh = ServiceMesh()
        runtime = MeshExecutionRuntime(engine=engine, mesh=mesh)
        with pytest.raises(Exception):
            runtime.execute_remote(DependencyGraph(), "nonexistent")

    def test_execute_via_mesh_with_registered_worker(self):
        engine = MagicMock()
        engine.execute.return_value = {"status": "completed", "data": "from_engine"}

        mesh = ServiceMesh()

        # Register a local handler for the worker service
        def execute_dag_handler(payload):
            return engine.execute(
                dag=payload["dag"],
                session_id=payload.get("session_id"),
                strategy=payload.get("strategy", "balanced"),
            )

        mesh.register_local_handler("worker", "execute_dag", execute_dag_handler)

        runtime = MeshExecutionRuntime(engine=engine, mesh=mesh)
        dag = DependencyGraph()
        result = runtime.execute(dag, prefer_local=False)
        assert result["data"] == "from_engine"
        engine.execute.assert_called()


# ═══════════════════════════════════════════════════════════════════
# MeshWorker
# ═══════════════════════════════════════════════════════════════════

class TestMeshWorker:
    def test_create_worker_registers_in_mesh(self):
        mesh = ServiceMesh()
        worker = MeshWorker(worker_id="w1", mesh=mesh)
        assert worker.worker_id == "w1"
        instances = mesh.registry.discover("worker")
        assert len(instances) == 1
        assert instances[0].metadata["worker_id"] == "w1"
        worker.deregister()

    def test_worker_deregister_removes_from_mesh(self):
        mesh = ServiceMesh()
        worker = MeshWorker(worker_id="w2", mesh=mesh)
        assert worker.deregister() is True
        assert len(mesh.registry.discover("worker")) == 0

    def test_worker_with_capabilities(self):
        mesh = ServiceMesh()
        worker = MeshWorker(worker_id="w3", mesh=mesh, capabilities=["read", "write"])
        instances = mesh.registry.discover("worker")
        assert "read" in instances[0].capabilities
        worker.deregister()

    def test_worker_heartbeat(self):
        mesh = ServiceMesh()
        worker = MeshWorker(worker_id="w4", mesh=mesh)
        assert worker.heartbeat() is True
        worker.deregister()

    def test_multiple_workers_registered(self):
        mesh = ServiceMesh()
        w1 = MeshWorker(worker_id="w1", mesh=mesh)
        w2 = MeshWorker(worker_id="w2", mesh=mesh)
        assert len(mesh.registry.discover("worker")) == 2
        w1.deregister()
        w2.deregister()


# ═══════════════════════════════════════════════════════════════════
# RuntimeOS Mesh Integration
# ═══════════════════════════════════════════════════════════════════

class TestRuntimeOSMeshIntegration:
    def test_runtime_os_creates_mesh_runtime(self):
        os = RuntimeOS()
        assert os.mesh_runtime is not None
        assert os.mesh is not None

    def test_submit_routes_through_mesh(self):
        engine = MagicMock()
        engine.execute.return_value = {"status": "completed"}

        mesh = ServiceMesh()

        def execute_handler(payload):
            return engine.execute(dag=payload["dag"])

        mesh.register_local_handler("worker", "execute_dag", execute_handler)

        os = RuntimeOS(engine=engine, mesh=mesh)
        dag = DependencyGraph()
        eid = os.submit(dag)
        assert os.observe(eid)["status"] == "completed"

    def test_submit_with_mesh_worker_integration(self):
        """End-to-end: submit DAG → mesh routes to registered worker."""
        engine = MagicMock()
        engine.execute.return_value = {"status": "completed", "data": "mesh_ok"}

        mesh = ServiceMesh()

        # Create a mesh worker that wraps the engine
        def worker_execute(payload):
            return engine.execute(
                dag=payload["dag"],
                session_id=payload.get("session_id"),
            )

        mesh.register_local_handler("worker", "execute_dag", worker_execute)
        worker = MeshWorker(worker_id="test-worker", mesh=mesh)

        os = RuntimeOS(engine=engine, mesh=mesh)
        dag = DependencyGraph()
        eid = os.submit(dag)
        assert os.observe(eid)["status"] == "completed"
        engine.execute.assert_called()
        worker.deregister()

    def test_submit_no_mesh_falls_back_to_engine(self):
        engine = MagicMock()
        engine.execute.return_value = {"status": "completed", "data": "direct"}

        os = RuntimeOS(engine=engine)
        dag = DependencyGraph()
        eid = os.submit(dag, use_mesh_routing=False)
        assert os.observe(eid)["status"] == "completed"
        engine.execute.assert_called_once()

    def test_mesh_worker_discoverable_by_control_plane(self):
        mesh = ServiceMesh()
        worker = MeshWorker(worker_id="cp-worker", mesh=mesh)

        # Control plane can discover workers via the mesh registry
        workers = mesh.registry.discover("worker")
        assert len(workers) == 1
        assert workers[0].metadata["worker_id"] == "cp-worker"

        worker.deregister()

    def test_multiple_submits_go_through_mesh(self):
        engine = MagicMock()
        engine.execute.return_value = {"status": "completed"}

        mesh = ServiceMesh()

        def handler(payload):
            return engine.execute(dag=payload["dag"])

        mesh.register_local_handler("worker", "execute_dag", handler)

        os = RuntimeOS(engine=engine, mesh=mesh)
        dag = DependencyGraph()

        eid1 = os.submit(dag)
        eid2 = os.submit(dag)
        eid3 = os.submit(dag)

        assert os.observe(eid1)["status"] == "completed"
        assert os.observe(eid2)["status"] == "completed"
        assert os.observe(eid3)["status"] == "completed"
        assert engine.execute.call_count == 3
