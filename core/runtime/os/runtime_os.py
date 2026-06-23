"""GAP 3 / F1 — RuntimeOS: the unified external control interface.

Transforms the system from a Library into an Operating System.

Public API surface:
  - Runtime.submit(task)          → execution_id
  - Runtime.observe(id)           → execution status + events
  - Runtime.replay(id)            → re-execute
  - Runtime.cancel(id)            → stop
  - Runtime.resume(id)            → resume paused execution
  - Runtime.scale(n)              → resize workers
  - Runtime.register_worker(...)  → register a new worker

This is the only interface external consumers should use.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from core.control_plane import ControlPlaneBrain
from core.interfaces.execution_engine import IExecutionEngine
from core.models.dag import DependencyGraph, PlanNode
from core.runtime.control.worker_orchestrator import WorkerOrchestrator
from core.runtime.isolation.isolation_runtime import IsolationRuntime
from core.runtime.mesh.mesh_execution_runtime import MeshExecutionRuntime
from core.runtime.mesh.service_mesh import ServiceMesh
from core.runtime.mesh.service_registry import ServiceRegistry

logger = logging.getLogger("emo_ai.os")


@dataclass
class ExecutionRecord:
    """Record of an execution in the runtime OS."""
    execution_id: str
    status: str = "pending"
    dag: Optional[DependencyGraph] = None
    session_id: str = ""
    strategy: str = "balanced"
    result: Optional[Dict[str, Any]] = None
    created_at: float = 0.0
    completed_at: float = 0.0
    events: List[Dict[str, Any]] = field(default_factory=list)
    error: str = ""


class RuntimeOS:
    """Unified Runtime Operating System — the public API surface.

    This is THE single interface for all external consumers.
    Everything the system can do is accessible through this class.
    """

    def __init__(
        self,
        engine: Optional[IExecutionEngine] = None,
        control_brain: Optional[ControlPlaneBrain] = None,
        orchestrator: Optional[WorkerOrchestrator] = None,
        isolation: Optional[IsolationRuntime] = None,
        mesh: Optional[ServiceMesh] = None,
        registry: Optional[ServiceRegistry] = None,
        mesh_runtime: Optional[MeshExecutionRuntime] = None,
        codegraph: Optional[Any] = None,
    ):
        self._engine = engine
        self._brain = control_brain or ControlPlaneBrain(
            correction_handler=self._handle_correction,
            codegraph=codegraph,
        )
        self._orchestrator = orchestrator or WorkerOrchestrator()
        self._isolation = isolation
        self._mesh = mesh or ServiceMesh()
        self._registry = registry or ServiceRegistry()
        self._mesh_runtime = mesh_runtime or MeshExecutionRuntime(
            engine=engine,
            mesh=self._mesh,
        )

        self._executions: Dict[str, ExecutionRecord] = {}
        self._phase = "booting"
        self._started = False

    # ── Lifecycle ──

    def start(self) -> None:
        """Start the runtime OS and all subsystems."""
        if self._started:
            return
        self._brain.start()
        self._phase = "active"
        self._started = True
        logger.info("RuntimeOS started")

    def shutdown(self) -> None:
        """Shutdown the runtime OS and all subsystems."""
        if not self._started:
            return
        self._brain.shutdown()
        if self._isolation:
            self._isolation.shutdown()
        self._phase = "shutdown"
        self._started = False
        logger.info("RuntimeOS shutdown")

    @property
    def engine(self) -> Optional[IExecutionEngine]:
        return self._engine

    @property
    def brain(self) -> ControlPlaneBrain:
        return self._brain

    @property
    def control(self) -> ControlPlaneBrain:
        """Backward-compat: returns the same as .brain."""
        return self._brain

    @property
    def isolation(self) -> Optional[IsolationRuntime]:
        return self._isolation

    @property
    def mesh(self) -> ServiceMesh:
        return self._mesh

    @property
    def mesh_runtime(self) -> MeshExecutionRuntime:
        return self._mesh_runtime

    @property
    def registry(self) -> ServiceRegistry:
        return self._registry

    def _handle_correction(self, correction) -> None:
        """Handle reconciliation corrections from the brain."""
        from core.control_plane.reconciler import Correction
        logger.info("Correction: %s — %s", correction.action, correction.reason)

    # ═══════════════════════════════════════════════════════════════
    # GAP 3 — Unified Runtime API
    # ═══════════════════════════════════════════════════════════════

    def submit(
        self,
        dag: DependencyGraph,
        session_id: Optional[str] = None,
        strategy: str = "balanced",
        tool_runner: Optional[Callable] = None,
        use_mesh_routing: bool = True,
    ) -> str:
        """Submit a DAG for execution.

        Routes through the mesh runtime for worker-aware dispatch.
        Falls back to direct engine execution if mesh routing is disabled
        or unavailable.

        Returns an execution_id that can be used with observe(),
        cancel(), and replay().

        Args:
            dag: The DAG to execute.
            session_id: Optional session identifier.
            strategy: Execution strategy.
            tool_runner: Optional tool runner callable.
            use_mesh_routing: If True, route through mesh runtime.

        Returns:
            execution_id for tracking.
        """
        execution_id = uuid.uuid4().hex[:16]
        record = ExecutionRecord(
            execution_id=execution_id,
            status="submitted",
            dag=dag,
            session_id=session_id or "",
            strategy=strategy,
            created_at=time.time(),
        )
        self._executions[execution_id] = record

        # Phase 6: Brain decides placement
        task_info = {
            "dag_id": getattr(dag, "id", execution_id),
            "strategy": strategy,
        }
        try:
            selected_node = self._brain.decide_placement(task_info)
            self._brain.record_execution_start(execution_id, task_info["dag_id"], strategy)
            logger.debug("Brain placed execution %s → node %s", execution_id, selected_node)
        except RuntimeError:
            selected_node = ""
            self._brain.record_execution_start(execution_id, task_info["dag_id"], strategy)

        try:
            record.status = "running"

            if use_mesh_routing and self._mesh_runtime is not None:
                result = self._mesh_runtime.execute(
                    dag=dag,
                    session_id=session_id,
                    strategy=strategy,
                    tool_runner=tool_runner,
                )
            elif self._engine is not None:
                result = self._engine.execute(
                    dag=dag,
                    session_id=session_id,
                    strategy=strategy,
                    tool_runner=tool_runner,
                )
            else:
                record.status = "failed"
                record.error = "No execution engine configured"
                record.completed_at = time.time()
                self._brain.record_execution_end(execution_id, "failed", node_id=selected_node)
                return execution_id

            record.status = result.get("status", "completed")
            record.result = result
            record.completed_at = time.time()
            self._brain.record_execution_end(execution_id, record.status, node_id=selected_node)
        except Exception as e:
            record.status = "failed"
            record.error = str(e)
            record.completed_at = time.time()
            self._brain.record_execution_end(execution_id, "failed", error=str(e), node_id=selected_node)

        return execution_id

    def observe(self, execution_id: str) -> Dict[str, Any]:
        """Observe the status and events of an execution.

        Returns the full execution record with status, results,
        events, and timing.
        """
        record = self._executions.get(execution_id)
        if record is None:
            return {
                "execution_id": execution_id,
                "status": "not_found",
                "error": f"No execution found with id '{execution_id}'",
            }

        return {
            "execution_id": record.execution_id,
            "status": record.status,
            "session_id": record.session_id,
            "strategy": record.strategy,
            "created_at": record.created_at,
            "completed_at": record.completed_at,
            "result": record.result,
            "error": record.error,
        }

    def rerun(self, execution_id: str) -> str:
        """Re-execute a previously submitted DAG from scratch.

        Returns a new execution_id for the re-executed execution.
        The original execution is preserved.
        """
        original = self._executions.get(execution_id)
        if original is None:
            raise ValueError(f"No execution found with id '{execution_id}'")

        if original.dag is None:
            raise ValueError(f"Execution {execution_id} has no DAG to re-run")

        import copy
        replay_dag = copy.deepcopy(original.dag)

        return self.submit(
            dag=replay_dag,
            session_id=original.session_id,
            strategy=original.strategy,
        )

    def replay(self, execution_id: str) -> str:
        """DEPRECATED: Use rerun() instead.

        Re-execute a previously submitted DAG.
        """
        import warnings
        warnings.warn("replay() is deprecated, use rerun()", DeprecationWarning, stacklevel=2)
        return self.rerun(execution_id)

    def cancel(self, execution_id: str) -> bool:
        """Cancel a running execution.

        Returns True if the execution was cancelled,
        False if it was already completed or not found.
        """
        record = self._executions.get(execution_id)
        if record is None:
            return False
        if record.status in ("completed", "failed", "cancelled"):
            return False
        if self._engine is not None:
            record.status = "cancelled"
            record.completed_at = time.time()
            self._brain.record_execution_end(execution_id, "cancelled")
            return True
        return False

    def resume(self, execution_id: str) -> bool:
        """Resume a paused or failed execution.

        Re-submits the DAG for execution if the original DAG exists.

        Returns True if the execution was resumed.
        """
        record = self._executions.get(execution_id)
        if record is None:
            return False
        if record.status not in ("paused", "failed", "cancelled"):
            return False
        if record.dag is None:
            return False
        new_id = self.submit(
            dag=record.dag,
            session_id=record.session_id,
            strategy=record.strategy,
        )
        record.status = "resumed"
        logger.info("Resumed execution %s → new execution %s", execution_id, new_id)
        return True

    def register_worker(self, worker_id: str, node_id: str = "",
                         total_cpu: float = 8.0, total_memory: float = 8192.0,
                         total_gpu: int = 0, total_gpu_memory: float = 0.0,
                         capacity: int = 10,
                         tags: Optional[Dict[str, str]] = None) -> None:
        """Register a new worker with the runtime OS.

        Registers with: scheduler (F3), topology (F4), service registry (mesh),
        and worker orchestrator.

        Args:
            worker_id: Unique worker identifier.
            node_id: Node this worker runs on.
            total_cpu: Total CPU cores available.
            total_memory: Total memory in MB.
            total_gpu: Total GPU cores available.
            total_gpu_memory: Total GPU memory in MB.
            capacity: Max concurrent tasks.
            tags: Optional worker metadata tags.
        """
        nid = node_id or f"node-{worker_id}"
        self._brain.register_worker_resources(
            worker_id=worker_id, node_id=nid,
            total_cpu=total_cpu, total_memory=total_memory,
            total_gpu=total_gpu, total_gpu_memory=total_gpu_memory,
            capacity=capacity, tags=tags,
        )
        self._registry.register(
            service_name=worker_id,
            host=nid, port=0,
            capabilities=[],
        )
        self._orchestrator.create_worker(
            worker_id=worker_id,
            capacity=capacity,
        )
        logger.info("Registered worker %s on node %s (cpu=%.1f, gpu=%d)",
                     worker_id, nid, total_cpu, total_gpu)

    def scale(self, workers: int) -> int:
        """Scale the number of runtime workers.

        Args:
            workers: Desired number of workers.

        Returns:
            Actual number of workers after scaling.
        """
        current = self._orchestrator.active_count()
        if workers > current:
            self._orchestrator.scale_up(workers - current)
        elif workers < current:
            self._orchestrator.scale_down(current - workers)
        return self._orchestrator.active_count()

    # ── Runtime intelligence ──

    def list_executions(
        self,
        status: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """List all executions, optionally filtered by status."""
        results = []
        for record in self._executions.values():
            if status and record.status != status:
                continue
            results.append({
                "execution_id": record.execution_id,
                "status": record.status,
                "created_at": record.created_at,
            })
        results.sort(key=lambda r: r["created_at"], reverse=True)
        return results[:limit]

    def status_summary(self) -> Dict[str, Any]:
        """Return a summary of the runtime OS status."""
        total = len(self._executions)
        completed = sum(1 for e in self._executions.values() if e.status == "completed")
        failed = sum(1 for e in self._executions.values() if e.status == "failed")
        running = sum(1 for e in self._executions.values() if e.status == "running")
        return {
            "started": self._started,
            "total_executions": total,
            "completed": completed,
            "failed": failed,
            "running": running,
            "system_phase": self._phase,
        }
