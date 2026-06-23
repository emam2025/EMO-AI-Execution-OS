"""Phase 6 / F2 — ControlPlaneBrain: cognitive decision layer + F3 ResourceScheduler.

Orchestrates the 5 core subsystems:
  6.1 — SystemStateBrain (global truth model)
  6.2 — Reconciler (self-healing loop)
  6.3 — ExecutionOrchestrator (decision engine)
  6.4 — HealthManager (health + topology)
  F3  — ResourceScheduler (CPU/GPU/fairness/quotas/priority)

Design rules:
  - Control Plane = decisions ONLY
  - Execution Layer = execution ONLY
  - State = event-derived truth
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from core.control_plane.health import HealthManager
from core.control_plane.orchestrator import ExecutionOrchestrator
from core.control_plane.reconciler import Reconciler, Correction
from core.control_plane.state.system_state import SystemStateBrain
from core.codegraph.integration import CodeGraphRuntime
from core.runtime.resource_scheduler import (
    Priority,
    ResourceRequirements,
    ResourceScheduler,
    SchedulingResult,
)
from core.observability.trace import TraceStore, SpanStatus
from core.observability.timeline import TimelineStore, EventType
from core.observability.failure_explorer import FailureExplorer
from core.observability.topology_viewer import TopologyViewer

logger = logging.getLogger("emo_ai.control_plane.brain")


class ControlPlaneBrain:
    """The cognitive decision layer over the distributed execution kernel.

    This is the BRAIN of the system. It:
      - Maintains the global truth model (SystemStateBrain)
      - Runs reconciliation loops (Reconciler)
      - Makes placement decisions via ResourceScheduler (F3)
      - Monitors health and topology (HealthManager)
      - Provides observability (F4: traces, timelines, failures, topology)

    It does NOT execute tasks — it decides. Execution is delegated
    to the MeshExecutionRuntime.
    """

    def __init__(
        self,
        state: Optional[SystemStateBrain] = None,
        reconciler: Optional[Reconciler] = None,
        orchestrator: Optional[ExecutionOrchestrator] = None,
        health: Optional[HealthManager] = None,
        scheduler: Optional[ResourceScheduler] = None,
        codegraph: Optional[CodeGraphRuntime] = None,
        correction_handler: Optional[Callable[[Correction], None]] = None,
    ):
        self._state = state or SystemStateBrain()
        self._reconciler = reconciler or Reconciler()
        self._orchestrator = orchestrator or ExecutionOrchestrator()
        self._health = health or HealthManager(state=self._state)
        # F3 — Resource Scheduler
        self._scheduler = scheduler or ResourceScheduler()
        # F4 — Observability
        self._trace_store = TraceStore()
        self._timeline_store = TimelineStore()
        self._failure_explorer = FailureExplorer()
        self._topology_viewer = TopologyViewer()
        # CodeGraph Runtime Integration
        self._codegraph = codegraph

        self._correction_handler = correction_handler
        self._loop_thread: Optional[threading.Thread] = None
        self._running = False
        self._loop_interval: float = 5.0

    @property
    def state(self) -> SystemStateBrain:
        return self._state

    @property
    def reconciler(self) -> Reconciler:
        return self._reconciler

    @property
    def orchestrator(self) -> ExecutionOrchestrator:
        return self._orchestrator

    @property
    def health(self) -> HealthManager:
        return self._health

    @property
    def scheduler(self) -> ResourceScheduler:
        return self._scheduler

    @property
    def traces(self) -> TraceStore:
        return self._trace_store

    @property
    def timelines(self) -> TimelineStore:
        return self._timeline_store

    @property
    def failures(self) -> FailureExplorer:
        return self._failure_explorer

    @property
    def topology(self) -> TopologyViewer:
        return self._topology_viewer

    @property
    def codegraph(self) -> Optional[CodeGraphRuntime]:
        return self._codegraph

    def on_correction(self, handler: Callable[[Correction], None]) -> None:
        """Register a handler for reconciliation corrections."""
        self._correction_handler = handler

    # ── Lifecycle ─────────────────────────────────────────────────

    def start(self, interval: float = 5.0) -> None:
        """Start the control plane background loop."""
        if self._running:
            return
        self._running = True
        self._loop_interval = interval
        self._loop_thread = threading.Thread(
            target=self._brain_loop,
            daemon=True,
            name="control-plane-brain",
        )
        self._loop_thread.start()
        logger.info("ControlPlaneBrain started (interval=%.1fs)", interval)

    def shutdown(self) -> None:
        """Stop the control plane."""
        self._running = False
        logger.info("ControlPlaneBrain shutdown")

    # ── Decision API ──────────────────────────────────────────────

    def decide_placement(
        self,
        task: Dict[str, Any],
        preferred_nodes: Optional[List[str]] = None,
        requirements: Optional[ResourceRequirements] = None,
        user_id: str = "default",
        priority: Priority = Priority.NORMAL,
    ) -> SchedulingResult:
        """Decide where a task should execute.

        Uses ResourceScheduler (F3) to find the best worker
        based on CPU, memory, GPU availability, fairness, and priority.

        Args:
            task: Task metadata for placement decisions.
            preferred_nodes: Optional preferred node list.
            requirements: Resource requirements (CPU, memory, GPU).
            user_id: User for quota/fairness tracking.
            priority: Task priority level.

        Returns:
            SchedulingResult with the selected worker and score.
        """
        task["_priority"] = priority
        result = self._scheduler.select_worker(
            task=task,
            user_id=user_id,
            requirements=requirements,
        )
        # Fall back to ExecutionOrchestrator if scheduler fails
        if result.score < 0 and result.worker_id == "":
            try:
                node_id = self._orchestrator.select_node(
                    task, self._state, preferred_nodes
                )
                result = SchedulingResult(
                    node_id=node_id,
                    worker_id="",
                    score=0.5,
                    reason=f"orchestrator_fallback (scheduler: {result.reason})",
                )
            except RuntimeError:
                result = SchedulingResult(
                    node_id="", worker_id="",
                    score=-1.0,
                    reason=f"scheduler_and_orchestrator_failed: {result.reason}",
                )
        return result

    def record_execution_start(self, execution_id: str, dag_id: str = "",
                                 strategy: str = "balanced") -> None:
        """Record that an execution has started."""
        self._state.register_execution(execution_id, dag_id, strategy)
        self._trace_store.create_trace(execution_id, dag_id, strategy)
        self._timeline_store.add_event(
            execution_id, EventType.SUBMITTED,
            service="control_plane",
            message=f"Execution {execution_id} submitted (strategy={strategy})",
        )

    def record_execution_end(self, execution_id: str, status: str = "completed",
                               worker_id: str = "", node_id: str = "",
                               error: str = "") -> None:
        """Record that an execution has ended."""
        self._state.update_execution(
            execution_id,
            status=status,
            worker_id=worker_id,
            node_id=node_id,
            completed_at=time.time(),
        )
        if error:
            self._state.record_failure(node_id or "unknown", execution_id, error)
            span_status = SpanStatus.ERROR
            self._failure_explorer.record_failure(
                execution_id=execution_id,
                error=error,
                worker_id=worker_id,
                node_id=node_id,
                error_type="execution_error",
            )
            self._timeline_store.add_event(
                execution_id, EventType.WORKER_FAILED,
                service="control_plane",
                message=f"Execution {execution_id} failed: {error[:100]}",
            )
        else:
            span_status = SpanStatus.OK
            self._timeline_store.add_event(
                execution_id, EventType.WORKER_COMPLETED,
                service="control_plane",
                message=f"Execution {execution_id} completed",
            )
        self._trace_store.complete_trace(execution_id, span_status, error)

    def record_failure(self, node_id: str, execution_id: str, error: str) -> str:
        """Record a failure in the system state."""
        result = self._state.record_failure(node_id, execution_id, error)
        self._failure_explorer.record_failure(
            execution_id=execution_id,
            error=error,
            node_id=node_id,
        )
        return result

    # ── F3 Resource Scheduler Integration ─────────────────────────

    def register_worker_resources(self, worker_id: str, node_id: str,
                                   total_cpu: float = 8.0,
                                   total_memory: float = 8192.0,
                                   total_gpu: int = 0,
                                   total_gpu_memory: float = 0.0,
                                   capacity: int = 10,
                                   tags: Optional[Dict[str, str]] = None) -> None:
        """Register a worker with the resource scheduler and topology."""
        self._scheduler.register_worker(
            worker_id, node_id,
            total_cpu=total_cpu, total_memory=total_memory,
            total_gpu=total_gpu, total_gpu_memory=total_gpu_memory,
            capacity=capacity, tags=tags,
        )
        self._topology_viewer.add_worker(
            worker_id, node_id,
            label=f"Worker {worker_id[:8]}",
            status="online",
            properties={
                "cpu": total_cpu, "memory": total_memory,
                "gpu": total_gpu, "capacity": capacity,
            },
        )

    def unregister_worker_resources(self, worker_id: str) -> None:
        self._scheduler.unregister_worker(worker_id)
        self._topology_viewer.remove_node(worker_id)

    def set_user_quota(self, user_id: str, max_cpu: float = 32.0,
                        max_memory: float = 32768.0, max_gpu: int = 4,
                        max_executions: int = 20) -> None:
        self._scheduler.set_quota(user_id, max_cpu, max_memory, max_gpu, max_executions)

    def allocate_resources(self, worker_id: str,
                            req: ResourceRequirements,
                            user_id: str = "default") -> bool:
        return self._scheduler.allocate(worker_id, req, user_id)

    def release_resources(self, worker_id: str,
                           req: ResourceRequirements,
                           user_id: str = "default") -> None:
        self._scheduler.release(worker_id, req, user_id)

    # ── Brain Loop ────────────────────────────────────────────────

    def _brain_loop(self) -> None:
        """Background loop: health check → reconcile → correct."""
        while self._running:
            try:
                self._tick()
            except Exception as e:
                logger.error("Brain tick failed: %s", e)
            time.sleep(self._loop_interval)

    def _tick(self) -> None:
        """Single brain tick.

        Phase 1: Health check all nodes
        Phase 2: Reconcile (desired vs actual) with anti-loop protection
        Phase 3: Execute corrections
        """
        # Phase 1: Health
        health_reports = self._health.check_all()
        for nid, report in health_reports.items():
            if report.alerts:
                logger.debug("Node %s: %s", nid, ", ".join(report.alerts))

        # Phase 2: Reconcile (with circuit breaker + dedup + cooldown)
        corrections = self._reconciler.reconcile(self._state)

        # Update reconciler with correction outcomes
        for c in corrections:
            self._timeline_store.add_event(
                c.target_id or "system",
                EventType.RECONCILED,
                service="reconciler",
                message=f"{c.action}: {c.reason}",
                metadata={"priority": c.priority},
            )

        # Phase 3: Execute corrections
        if corrections and self._correction_handler:
            for correction in corrections:
                try:
                    self._correction_handler(correction)
                except Exception as e:
                    logger.error("Correction failed: %s — %s", correction.action, e)
                    self._reconciler.record_correction_outcome(
                        correction.action, correction.target_id, succeeded=False
                    )

    # ── Snapshot ──────────────────────────────────────────────────

    def snapshot(self) -> Dict[str, Any]:
        """Return a complete brain snapshot."""
        return {
            "system_state": self._state.snapshot(),
            "health": self._health.status_summary(),
            "reconciler": {
                "desired_min_workers": self._reconciler.desired.min_workers,
                "desired_max_workers": self._reconciler.desired.max_workers,
            },
            "scheduler": self._scheduler.cluster_summary(),
            "observability": {
                "traces": len(self._trace_store._traces),
                "timelines": len(self._timeline_store._timelines),
                "failures": len(self._failure_explorer._records),
                "topology_nodes": len(self._topology_viewer._nodes),
            },
            "running": self._running,
        }
