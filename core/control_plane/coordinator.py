"""F2 — RuntimeCoordinator: bridge between brain, mesh, and runtime.

The coordinator is the central orchestrator that:
  1. Receives decisions from ControlPlaneBrain
  2. Routes execution through MeshExecutionRuntime
  3. Monitors execution lifecycle
  4. Handles failures and escalations
  5. Coordinates scaling with Autoscaler
  6. Manages worker drain for graceful shutdowns

This reduces coupling between the brain and the runtime.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, List, Optional

from core.control_plane.autoscaler import Autoscaler, ScalingDecision, ScalingDirection
from core.control_plane.brain import ControlPlaneBrain
from core.control_plane.health_supervisor import HealthSupervisor, RecoveryAction
from core.control_plane.worker_drainer import WorkerDrainer
from core.observability.timeline import EventType
from core.runtime.mesh.mesh_execution_runtime import MeshExecutionRuntime
from core.runtime.resource_scheduler import ResourceRequirements

logger = logging.getLogger("emo_ai.control_plane.coordinator")


class RuntimeCoordinator:
    """Central coordinator that bridges control plane decisions to execution.

    Responsibilities:
      - Translate brain decisions into runtime actions
      - Coordinate scaling (autoscaler → orchestrator)
      - Manage worker drain (drainer → orchestrator)
      - Supervise health (supervisor → recovery → runtime)
      - Provide unified execution flow
    """

    def __init__(
        self,
        brain: ControlPlaneBrain,
        mesh_runtime: Optional[MeshExecutionRuntime] = None,
        autoscaler: Optional[Autoscaler] = None,
        drainer: Optional[WorkerDrainer] = None,
        supervisor: Optional[HealthSupervisor] = None,
        on_execution_result: Optional[Callable[[str, str, Dict[str, Any]], None]] = None,
    ):
        self._brain = brain
        self._mesh_runtime = mesh_runtime
        self._autoscaler = autoscaler or Autoscaler()
        self._drainer = drainer or WorkerDrainer(state=brain.state)
        self._supervisor = supervisor or HealthSupervisor()
        self._on_execution_result = on_execution_result

    @property
    def brain(self) -> ControlPlaneBrain:
        return self._brain

    @property
    def autoscaler(self) -> Autoscaler:
        return self._autoscaler

    @property
    def drainer(self) -> WorkerDrainer:
        return self._drainer

    @property
    def supervisor(self) -> HealthSupervisor:
        return self._supervisor

    # ── Execution Coordination ───────────────────────────────

    def execute(self, task: Dict[str, Any],
                requirements: Optional[ResourceRequirements] = None,
                user_id: str = "default") -> Dict[str, Any]:
        """Full execution flow: placement → dispatch → monitor → report.

        Steps:
          1. Brain decides placement (via ResourceScheduler F3)
          2. Check drain (don't schedule on draining workers)
          3. Dispatch through mesh runtime
          4. Record execution in brain
          5. Return result

        Args:
            task: Task to execute (must have 'dag' or 'dag_id').
            requirements: Resource requirements for F3 scheduler.
            user_id: User for quota tracking.

        Returns:
            Execution result dict with status and data.
        """
        # Step 1: Placement decision
        result = self._brain.decide_placement(
            task=task,
            requirements=requirements,
            user_id=user_id,
        )
        node_id = result.node_id
        worker_id = result.worker_id

        if not node_id or not worker_id:
            return {
                "status": "failed",
                "error": f"No placement available: {result.reason}",
                "execution_id": "",
            }

        # Step 2: Check if target is draining
        if self._drainer.is_draining(worker_id):
            return {
                "status": "failed",
                "error": f"Worker {worker_id} is draining",
                "execution_id": "",
            }

        # Step 3: Dispatch
        execution_id = task.get("execution_id", "")
        dag = task.get("dag")
        if dag and self._mesh_runtime:
            try:
                exec_result = self._mesh_runtime.execute(
                    dag=dag,
                    session_id=task.get("session_id", ""),
                    strategy=task.get("strategy", "balanced"),
                )
                status = exec_result.get("status", "completed")
                error = exec_result.get("error", "")
                self._brain.record_execution_end(
                    execution_id, status,
                    worker_id=worker_id, node_id=node_id,
                    error=error,
                )
                if self._on_execution_result:
                    self._on_execution_result(execution_id, status, exec_result)
                return exec_result
            except Exception as e:
                self._brain.record_execution_end(
                    execution_id, "failed",
                    worker_id=worker_id, node_id=node_id,
                    error=str(e),
                )
                return {"status": "failed", "error": str(e)}

        return {
            "status": "failed",
            "error": "No mesh runtime or DAG available",
            "execution_id": execution_id,
        }

    # ── Scaling Coordination ────────────────────────────────

    def evaluate_scaling(self, current_workers: int,
                          pending_tasks: int = 0,
                          worker_utilization: float = 0.0) -> ScalingDecision:
        """Evaluate and execute autoscaling."""
        decision = self._autoscaler.evaluate(
            current_workers=current_workers,
            pending_tasks=pending_tasks,
            worker_utilization=worker_utilization,
        )
        if decision.direction == ScalingDirection.UP:
            self._brain.timelines.add_event(
                "autoscaler", EventType.SCHEDULED, "autoscaler",
                f"Scaling up {decision.count} workers",
            )
        elif decision.direction == ScalingDirection.DOWN:
            self._brain.timelines.add_event(
                "autoscaler", EventType.SCHEDULED, "autoscaler",
                f"Scaling down {decision.count} workers",
            )
        return decision

    def scale_to(self, target_count: int) -> int:
        """Scale to an exact worker count, draining excess if needed."""
        current = len(self._brain.state.healthy_workers())
        if target_count > current:
            diff = target_count - current
            for _ in range(diff):
                self._brain.state.register_worker(f"auto-w{time.time():.0f}")
            return target_count
        elif target_count < current:
            excess = current - target_count
            workers = list(self._brain.state.healthy_workers().keys())
            for wid in workers[:excess]:
                self._drainer.start_drain(wid)
            return target_count
        return current

    # ── Health Coordination ─────────────────────────────────

    def supervise_health(self) -> List[RecoveryAction]:
        """Run health supervision cycle."""
        return self._supervisor.tick()

    # ── Status ──────────────────────────────────────────────

    def status_summary(self) -> Dict[str, Any]:
        return {
            "autoscaler": {
                "config": {
                    "min": self._autoscaler.config.min_workers,
                    "max": self._autoscaler.config.max_workers,
                },
            },
            "drainer": self._drainer.drain_summary(),
            "supervisor": {
                "recoveries": len(self._supervisor.recovery_history()),
            },
        }
