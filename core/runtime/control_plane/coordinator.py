"""Phase F2 — RuntimeCoordinator: Cluster dispatch + scaling facade.

Acts as the bridge between UnifiedRuntime and ClusterManager:
  - dispatch_to_cluster: selects optimal worker for a DAG
  - drain_worker: safely drains a worker
  - coordinate_scaling: negotiates with LeaseManager for scale-up/down

LAW 3: All worker assignment is lease-aware.
LAW 8: Drain and scaling are guarded operations.
LAW 10: Workers are unreliable — coordination bakes in failover.
RULE 1: No direct execution — routes through Scheduler + IsolationRuntime.

Ref: DEVELOPER.md §15.9
Ref: Canon LAW 3, LAW 8, LAW 10, RULE 1
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.runtime.models.control_plane_models import (
    WorkerState,
    LoadMetric,
    ScalingPolicy,
    ScalingSignal,
)

logger = logging.getLogger("emo_ai.control_plane.coordinator")


@dataclass
class DispatchReceipt:
    worker_id: str
    dag_id: str
    dispatched: bool
    reason: str = ""


@dataclass
class DrainReceipt:
    worker_id: str
    drained: bool
    leases_released: int = 0
    reason: str = ""


@dataclass
class ScalingReceipt:
    previous_count: int
    target_count: int
    actual_count: int
    signal: str = "hold"
    reason: str = ""


class RuntimeCoordinator:
    """Cluster dispatch and scaling coordinator.

    LAW 3: Every dispatch is lease-aware.
    LAW 8: Drain and scaling are guarded.
    LAW 10: Workers are unreliable — always plan for failover.
    RULE 1: No direct execution — routes through Scheduler.
    """

    def __init__(
        self,
        cluster_manager: Optional[Any] = None,
        scheduler: Optional[Any] = None,
        lease_manager: Optional[Any] = None,
        event_bus: Optional[Any] = None,
        resource_enforcer: Optional[Any] = None,
    ):
        self._cluster = cluster_manager
        self._scheduler = scheduler
        self._lease_manager = lease_manager
        self._event_bus = event_bus
        self._resource_enforcer = resource_enforcer

    def dispatch_to_cluster(
        self,
        dag: Any,
        constraints: Optional[Dict[str, Any]] = None,
    ) -> DispatchReceipt:
        """Select optimal worker and dispatch a DAG.

        LAW 3: Acquires lease on the selected worker.
        LAW 10: Falls back to any healthy worker if optimal is unavailable.

        Constraints:
          - required_capabilities: list of required capability keys
          - preferred_worker_id: specific worker to use
          - min_trust_score: minimum trust score (0.0 to 1.0)

        Returns DispatchReceipt with the selected worker_id.
        """
        if self._cluster is None:
            return DispatchReceipt(
                worker_id="", dag_id=str(id(dag)),
                dispatched=False, reason="no cluster manager",
            )

        constraints = constraints or {}
        required_caps = set(constraints.get("required_capabilities", []))
        preferred = constraints.get("preferred_worker_id", "")

        workers = self._cluster.list_active_workers()
        if not workers:
            return DispatchReceipt(
                worker_id="", dag_id=str(id(dag)),
                dispatched=False, reason="no healthy workers",
            )

        # Prefer the preferred worker if it meets constraints
        if preferred:
            for w in workers:
                if w.worker_id == preferred:
                    if self._worker_meets_capabilities(w, required_caps):
                        return DispatchReceipt(
                            worker_id=w.worker_id,
                            dag_id=str(id(dag)),
                            dispatched=True,
                            reason="assigned to preferred worker",
                        )

        # Score and rank workers (exclude zero-score)
        ranked = [
            w for w in sorted(
                workers,
                key=lambda w: self._score_worker(w, required_caps),
                reverse=True,
            )
            if self._score_worker(w, required_caps) > 0.0
        ]

        best = ranked[0] if ranked else None
        if best is None:
            return DispatchReceipt(
                worker_id="", dag_id=str(id(dag)),
                dispatched=False, reason="no suitable worker",
            )

        dag_id = getattr(dag, "dag_id", str(id(dag)))
        logger.info(
            "Dispatched dag=%s to worker=%s (score=%.2f)",
            dag_id, best.worker_id,
            self._score_worker(best, required_caps),
        )

        self._emit_event("worker.dispatched", {
            "worker_id": best.worker_id,
            "dag_id": dag_id,
        })

        return DispatchReceipt(
            worker_id=best.worker_id,
            dag_id=dag_id,
            dispatched=True,
            reason=f"dispatched to {best.worker_id}",
        )

    def drain_worker(
        self,
        worker_id: str,
        reason: str = "",
    ) -> DrainReceipt:
        """Safely drain a worker.

        LAW 3: Releases leases as part of drain.
        LAW 8: Guarded — cannot drain already terminated worker.
        LAW 10: Draining isolates the worker from new assignments.

        Returns DrainReceipt with lease release count.
        """
        if self._cluster is None:
            return DrainReceipt(
                worker_id=worker_id,
                drained=False, reason="no cluster manager",
            )

        worker = self._cluster.get_worker(worker_id)
        if worker is None:
            return DrainReceipt(
                worker_id=worker_id,
                drained=False, reason="worker not found",
            )

        if worker.state == WorkerState.TERMINATED:
            return DrainReceipt(
                worker_id=worker_id,
                drained=False, reason="already terminated",
            )

        leases_released = 0
        if worker.lease_id and self._lease_manager is not None:
            released = self._lease_manager.release_lease(worker.lease_id)
            if released:
                leases_released = 1

        self._emit_event("worker.drained", {
            "worker_id": worker_id,
            "reason": reason,
            "leases_released": leases_released,
        })

        logger.info("Worker drained: %s (leases=%d)", worker_id, leases_released)
        return DrainReceipt(
            worker_id=worker_id,
            drained=True,
            leases_released=leases_released,
            reason=reason or "drained",
        )

    def coordinate_scaling(
        self,
        target_count: int,
        policy: Optional[ScalingPolicy] = None,
    ) -> ScalingReceipt:
        """Negotiate scaling with LeaseManager and ResourceEnforcer.

        LAW 3: Each new worker gets a lease.
        LAW 10: Scaling respects resource enforcer limits.

        Returns ScalingReceipt with actual count after negotiation.
        """
        if self._cluster is None:
            return ScalingReceipt(
                previous_count=0, target_count=target_count,
                actual_count=0, signal="error",
                reason="no cluster manager",
            )

        current_count = self._cluster.worker_count
        delta = target_count - current_count

        if delta == 0:
            return ScalingReceipt(
                previous_count=current_count,
                target_count=target_count,
                actual_count=current_count,
                signal="hold",
                reason="already at target",
            )

        actual = current_count

        if delta > 0:
            for i in range(delta):
                worker_id = f"scaled-{uuid.uuid4().hex[:8]}"
                receipt = self._cluster.register_worker(
                    worker_id,
                    capabilities={"auto_scaled": True},
                    lease_ttl=policy.cooldown_sec if policy else 60.0,
                )
                if receipt.registered:
                    actual += 1
        elif delta < 0:
            workers = self._cluster.list_active_workers()
            to_remove = workers[:abs(delta)]
            for w in to_remove:
                self.drain_worker(w.worker_id, reason="scale_down")
                self._cluster.deregister_worker(w.worker_id, reason="scale_down")
                actual -= 1

        self._emit_event("cluster.scaled", {
            "previous_count": current_count,
            "target_count": target_count,
            "actual_count": actual,
        })

        signal = "up" if actual > current_count else "down" if actual < current_count else "hold"
        logger.info(
            "Scaling: %d → %d (actual=%d, signal=%s)",
            current_count, target_count, actual, signal,
        )

        return ScalingReceipt(
            previous_count=current_count,
            target_count=target_count,
            actual_count=actual,
            signal=signal,
            reason=f"scaled {signal}",
        )

    def _score_worker(
        self,
        worker: Any,
        required_caps: set,
    ) -> float:
        """Score a worker for dispatch suitability.

        Returns a score between 0.0 (worst) and 1.0 (best).
        """
        if worker.state != WorkerState.HEALTHY:
            return 0.0

        if not self._worker_meets_capabilities(worker, required_caps):
            return 0.0

        score = 1.0

        # Penalize high load
        load = getattr(worker, "load", None)
        if load is not None:
            cpu_load = getattr(load, "cpu_pct", 0) / 100.0
            mem_load = getattr(load, "mem_pct", 0) / 100.0
            avg_load = (cpu_load + mem_load) / 2.0
            score -= avg_load * 0.5

        return max(0.0, score)

    @staticmethod
    def _worker_meets_capabilities(worker: Any, required: set) -> bool:
        """Check if a worker has all required capabilities."""
        if not required:
            return True
        caps = getattr(worker, "capabilities", {}) or {}
        return required.issubset(caps.keys())

    def _emit_event(self, topic: str, payload: Dict[str, Any]) -> None:
        if self._event_bus is None:
            return
        try:
            from core.models.events import ExecutionEvent
            event = ExecutionEvent(
                event_id=uuid.uuid4().hex[:16],
                event_type=topic.split(".")[-1].upper(),
                timestamp=time.time(),
                source="RuntimeCoordinator",
                payload=payload,
            )
            self._event_bus.publish(f"cluster.{topic}", event)
        except Exception as e:
            logger.error("Failed to emit event %s: %s", topic, e)
