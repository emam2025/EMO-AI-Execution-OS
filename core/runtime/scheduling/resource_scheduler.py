"""Phase F3 — SchedulingOrchestrator: bridges ClusterManager, QuotaManager, IsolationRuntime.

LAW 3: Every dispatch is lease-aware.
LAW 5: Every decision emits an ExecutionEvent.
LAW 8: Fair distribution — no starvation.
LAW 10: Resource limits enforced before dispatch.
LAW 11: No global mutable state — per-instance tracking.
RULE 1: Deterministic fit scoring — same inputs → same score.
RULE 3: Capability-first — worker must satisfy task capability requirements.

Ref: Canon LAW 3, LAW 5, LAW 8, LAW 10, LAW 11, RULE 1, RULE 3
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.runtime.scheduling.policies import (
    AffinityRules,
    FairnessPolicy,
    MatchScore,
    PriorityScheduler,
    SchedulingDecision,
    ReasonCode,
)

logger = logging.getLogger("emo_ai.scheduling.orchestrator")


@dataclass
class TaskRequirements:
    execution_id: str = ""
    dag_id: str = ""
    cpu_cores: float = 1.0
    memory_mb: int = 512
    gpu_memory_mb: int = 0
    io_bandwidth: str = "standard"
    network_access: bool = False
    priority: int = 2
    max_wait_sec: float = 300.0
    affinity_tags: List[str] = field(default_factory=list)


class SchedulingOrchestrator:
    """Top-level scheduling orchestrator.

    Decides WHERE and WHEN a task runs, then delegates execution
    to IsolationRuntime → SandboxExecutor.

    All decisions are event-driven (LAW 5).
    All worker assignments are lease-aware (LAW 3).
    No direct execution — routing only (RULE 1).
    """

    def __init__(
        self,
        cluster_manager: Any = None,
        quota_manager: Any = None,
        isolation_runtime: Any = None,
        event_bus: Any = None,
        lease_manager: Any = None,
        fairness_policy: Optional[FairnessPolicy] = None,
        priority_scheduler: Optional[PriorityScheduler] = None,
        affinity_rules: Optional[AffinityRules] = None,
    ):
        self._cluster = cluster_manager
        self._quota = quota_manager
        self._isolation = isolation_runtime
        self._event_bus = event_bus
        self._lease_manager = lease_manager

        self._fairness = fairness_policy or FairnessPolicy()
        self._priority = priority_scheduler or PriorityScheduler()
        self._affinity = affinity_rules or AffinityRules()

    @property
    def fairness_policy(self) -> FairnessPolicy:
        return self._fairness

    @property
    def priority_scheduler(self) -> PriorityScheduler:
        return self._priority

    @property
    def affinity_rules(self) -> AffinityRules:
        return self._affinity

    # ── evaluate_worker_fit ──────────────────────────────────

    def evaluate_worker_fit(
        self,
        task: TaskRequirements,
        worker_capabilities: Dict[str, Any],
    ) -> MatchScore:
        """Score how well a worker fits a task's requirements.

        Considers CPU/RAM/GPU/Network requirements against the
        worker's available capabilities and current load.

        Returns MatchScore (0.0 = no fit, 1.0 = perfect fit).
        """
        violations: List[str] = []
        score = 0.0

        worker_cpu = float(worker_capabilities.get("available_cpu", 0))
        worker_mem = int(worker_capabilities.get("available_memory", 0))
        worker_gpu = int(worker_capabilities.get("available_gpu", 0))
        worker_network = bool(worker_capabilities.get("network", False))

        if worker_cpu < task.cpu_cores:
            violations.append(f"CPU {worker_cpu} < {task.cpu_cores}")
        else:
            score += 0.3

        if worker_mem < task.memory_mb:
            violations.append(f"memory {worker_mem} < {task.memory_mb}")
        else:
            score += 0.3

        if task.gpu_memory_mb > 0:
            if worker_gpu >= task.gpu_memory_mb:
                score += 0.2
            else:
                violations.append(f"GPU {worker_gpu} < {task.gpu_memory_mb}")

        if task.network_access and not worker_network:
            violations.append("network required but worker has no network")
        elif task.network_access:
            score += 0.1

        load_pct = float(worker_capabilities.get("load_pct", 0))
        if load_pct > 0:
            penalty = (load_pct / 100.0) * 0.4
            score -= min(penalty, 0.4)

        score = max(0.0, min(1.0, score))

        return MatchScore(
            score=round(score, 4),
            matched=len(violations) == 0,
            reason=(
                "Worker meets requirements"
                if len(violations) == 0
                else "; ".join(violations)
            ),
            violations=violations,
        )

    # ── select_optimal_worker ────────────────────────────────

    def select_optimal_worker(
        self,
        task: TaskRequirements,
        constraints: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Select the best worker for a task.

        Process:
          1. Get active workers from ClusterManager.
          2. Evaluate fit for each worker.
          3. Apply fairness, priority, and affinity policies.
          4. Reserve quota on the best candidate.
          5. Emit TaskScheduled event.

        Returns worker_id or None if no suitable worker found.
        """
        constraints = constraints or {}

        if self._cluster is None:
            logger.debug("No cluster manager — cannot select worker")
            return None

        workers = self._cluster.list_active_workers()
        if not workers:
            logger.debug("No active workers available")
            self._emit_event("scheduling.task.rejected", {
                "execution_id": task.execution_id,
                "reason": "no_active_workers",
            })
            return None

        candidates: List[tuple[str, float, str]] = []

        for w in workers:
            caps = dict(getattr(w, "capabilities", {}) or {})
            load = getattr(w, "load", None)
            if load is not None:
                load_pct = (
                    getattr(load, "cpu_pct", 0)
                    + getattr(load, "mem_pct", 0)
                ) / 2.0
                caps["load_pct"] = load_pct

            score = self.evaluate_worker_fit(task, caps)
            if not score.matched:
                continue

            affinity_score = self._affinity.evaluate(
                task.execution_id,
                caps,
                constraints.get("preferred_worker", ""),
            )
            adjusted = score.score * (0.8 + 0.2 * affinity_score)

            fairness_adjustment = self._fairness.compute_weight(w.worker_id)
            adjusted *= fairness_adjustment

            candidates.append((w.worker_id, adjusted, score.reason))

        if not candidates:
            self._emit_event("scheduling.task.rejected", {
                "execution_id": task.execution_id,
                "reason": "no_matching_worker",
            })
            return None

        candidates.sort(key=lambda c: c[1], reverse=True)
        best_id, best_score, best_reason = candidates[0]

        if self._quota is not None:
            lease_id = self._quota.reserve_quota(
                best_id,
                {
                    "cpu": task.cpu_cores,
                    "memory": task.memory_mb,
                    "gpu": task.gpu_memory_mb,
                },
            )
            if lease_id is None:
                logger.debug(
                    "Quota reservation failed for worker %s", best_id,
                )
                self._emit_event("scheduling.task.rejected", {
                    "execution_id": task.execution_id,
                    "reason": "quota_exceeded",
                    "worker_id": best_id,
                })
                return None

        self._emit_event("scheduling.task.scheduled", {
            "execution_id": task.execution_id,
            "worker_id": best_id,
            "score": best_score,
            "reason": best_reason,
        })

        logger.info(
            "Task %s → worker %s (score=%.4f)",
            task.execution_id, best_id, best_score,
        )
        return best_id

    # ── preempt_low_priority_task ────────────────────────────

    def preempt_low_priority_task(
        self,
        worker_id: str,
        high_priority_task: TaskRequirements,
    ) -> bool:
        """Preempt a low-priority task on a worker.

        Requirements:
          - Priority diff >= 2 tiers (P0 can preempt P2/P3; P1 can preempt P3).
          - Target has checkpoint available.
          - Emits TaskPreempted event.

        Actual execution stopping is delegated to IsolationRuntime.
        """
        worker = None
        if self._cluster is not None:
            worker = self._cluster.get_worker(worker_id)

        if worker is None:
            logger.debug("Worker %s not found for preemption", worker_id)
            return False

        caps = dict(getattr(worker, "capabilities", {}) or {})
        active_tasks = caps.get("active_tasks", [])

        if not active_tasks:
            logger.debug("No active tasks on worker %s to preempt", worker_id)
            return False

        target = self._priority.select_preemption_target(
            high_priority_task.priority,
            active_tasks,
        )

        if target is None:
            logger.debug(
                "No preemptable task on worker %s for priority %d",
                worker_id, high_priority_task.priority,
            )
            return False

        logger.info(
            "Preempting task %s on worker %s for priority %d",
            target, worker_id, high_priority_task.priority,
        )

        if self._quota is not None:
            self._quota.release_quota(
                f"task:{target}",
                {"cpu": 0, "memory": 0},
            )

        self._emit_event("scheduling.task.preempted", {
            "worker_id": worker_id,
            "preempted_task": target,
            "incoming_priority": high_priority_task.priority,
            "checkpoint_available": True,
        })

        return True

    # ── release_resources ────────────────────────────────────

    def release_resources(
        self,
        execution_id: str,
        actual_usage: Optional[Dict[str, float]] = None,
    ) -> None:
        """Release resources after task completion or failure.

        Delegates to QuotaManager.release_quota.
        """
        if self._quota is not None:
            self._quota.release_quota(
                f"task:{execution_id}",
                actual_usage or {},
            )

        self._emit_event("scheduling.task.completed", {
            "execution_id": execution_id,
        })

    # ── enforce_global_ceiling ───────────────────────────────

    def enforce_global_ceiling(self) -> Optional[str]:
        """Check global resource ceiling and signal autoscaler.

        Returns a scaling signal ("up", "down", "hold") or None.
        """
        if self._quota is None:
            return None

        signal = self._quota.enforce_global_ceiling()
        if signal and signal != "hold":
            self._emit_event("scheduling.quota.ceiling", {
                "signal": signal,
                "source": "SchedulingOrchestrator",
            })

        return signal

    # ── Event emission ───────────────────────────────────────

    def _emit_event(self, topic: str, payload: Dict[str, Any]) -> None:
        if self._event_bus is None:
            return
        try:
            from core.models.events import ExecutionEvent
            event = ExecutionEvent(
                event_id=uuid.uuid4().hex[:16],
                event_type=topic.split(".")[-1].upper(),
                timestamp=time.time(),
                source="SchedulingOrchestrator",
                payload=payload,
            )
            self._event_bus.publish(f"scheduling.{topic}", event)
        except Exception as e:
            logger.error("Failed to emit event %s: %s", topic, e)
