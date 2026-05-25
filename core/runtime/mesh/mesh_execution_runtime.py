"""Service Mesh Runtime — mesh-aware DAG execution routing.

Routes execution tasks through the service mesh to registered workers.
This is the RUNTIME layer that makes the mesh actually execute work.

Flow:
  RuntimeOS.submit(dag)
    → MeshExecutionRuntime.execute(dag)
      → Find capable worker in mesh
      → Dispatch to local worker or remote node
      → Return result

This is what makes the mesh a real execution fabric,
not just a registry + protocol.
"""

from __future__ import annotations

import copy
import logging
from typing import Any, Callable, Dict, List, Optional

from core.interfaces.execution_engine import IExecutionEngine
from core.models.dag import DependencyGraph
from core.runtime.mesh.service_mesh import ServiceMesh, ServiceNotAvailable

logger = logging.getLogger("emo_ai.mesh.runtime")


class MeshExecutionRuntime:
    """Mesh-aware execution layer.

    Wraps an execution engine and routes work through the mesh.
    Each worker registers as a service in the mesh, and tasks
    are dispatched to the best available worker.
    """

    def __init__(
        self,
        engine: Optional[IExecutionEngine] = None,
        mesh: Optional[ServiceMesh] = None,
    ):
        self._engine = engine
        self._mesh = mesh or ServiceMesh()

    @property
    def engine(self) -> Optional[IExecutionEngine]:
        return self._engine

    @property
    def mesh(self) -> ServiceMesh:
        return self._mesh

    def execute(
        self,
        dag: DependencyGraph,
        session_id: Optional[str] = None,
        strategy: str = "balanced",
        tool_runner: Optional[Callable] = None,
        prefer_local: bool = True,
    ) -> Dict[str, Any]:
        """Execute a DAG through the mesh.

        Routing logic:
          1. If local engine available and prefer_local, execute locally
          2. If no local engine, find a worker in the mesh
          3. Dispatch to the selected worker via mesh call
          4. Return result

        Args:
            dag: The DAG to execute.
            session_id: Optional session identifier.
            strategy: Execution strategy.
            tool_runner: Optional tool runner callable.
            prefer_local: Whether to prefer local execution.

        Returns:
            Execution result dict.
        """
        if self._engine is not None and prefer_local:
            logger.debug("Executing DAG locally (prefer_local=True)")
            return self._engine.execute(
                dag=dag,
                session_id=session_id,
                strategy=strategy,
                tool_runner=tool_runner,
            )

        # Route through mesh to a capable worker
        try:
            result = self._mesh.call(
                service="worker",
                method="execute_dag",
                payload={
                    "dag": dag,
                    "session_id": session_id or "",
                    "strategy": strategy,
                },
            )
            return result
        except ServiceNotAvailable:
            logger.warning("No worker available in mesh — falling back to local")

            if self._engine is not None:
                return self._engine.execute(
                    dag=dag,
                    session_id=session_id,
                    strategy=strategy,
                    tool_runner=tool_runner,
                )

            raise

    def execute_remote(
        self,
        dag: DependencyGraph,
        worker_id: str,
        session_id: Optional[str] = None,
        strategy: str = "balanced",
    ) -> Dict[str, Any]:
        """Execute a DAG on a specific remote worker.

        Args:
            dag: The DAG to execute.
            worker_id: The mesh node / worker ID to dispatch to.
            session_id: Optional session identifier.
            strategy: Execution strategy.

        Returns:
            Execution result dict.
        """
        return self._mesh.call(
            service="worker",
            method="execute_dag",
            payload={
                "dag": dag,
                "session_id": session_id or "",
                "strategy": strategy,
                "worker_id": worker_id,
            },
        )
