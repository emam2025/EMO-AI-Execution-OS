"""Mesh Worker — wraps workers with mesh registration + dispatch.

Each worker in the system registers itself as a mesh service,
so the MeshExecutionRuntime can discover and dispatch to it.

This is the bridge between:
  - WorkerOrchestrator (creates/destroys workers)
  - ServiceMesh (routes calls to workers)
  - ExecutionEngine (actually executes DAGs)
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Optional

from core.runtime.mesh.service_mesh import ServiceMesh
from core.runtime.mesh.service_registry import ServiceRegistry

logger = logging.getLogger("emo_ai.mesh.worker")


class MeshWorker:
    """A mesh-registered worker that can accept and execute tasks.

    Each MeshWorker registers as a 'worker' service in the mesh
    when created, and deregisters when destroyed.

    The worker service exposes:
      - execute_dag: Execute a DAG and return results
      - health: Return worker health status
      - capabilities: List supported tool types
    """

    def __init__(
        self,
        worker_id: str,
        mesh: ServiceMesh,
        execute_fn: Optional[Callable] = None,
        capabilities: Optional[list] = None,
    ):
        self._worker_id = worker_id
        self._mesh = mesh
        self._execute_fn = execute_fn
        self._capabilities = capabilities or ["*"]

        # Register worker as a mesh service
        self._instance_id = self._mesh.registry.register(
            service_name="worker",
            host="127.0.0.1",
            port=0,
            capabilities=self._capabilities,
            metadata={"worker_id": worker_id},
        )
        logger.info(
            "MeshWorker %s registered (instance=%s, capabilities=%s)",
            worker_id, self._instance_id, self._capabilities,
        )

    @property
    def worker_id(self) -> str:
        return self._worker_id

    @property
    def instance_id(self) -> str:
        return self._instance_id

    def heartbeat(self) -> bool:
        """Send a heartbeat through the mesh registry."""
        return self._mesh.registry.heartbeat("worker", self._instance_id)

    def deregister(self) -> bool:
        """Deregister from the mesh."""
        result = self._mesh.registry.deregister("worker", self._instance_id)
        if result:
            logger.info("MeshWorker %s deregistered", self._worker_id)
        return result
