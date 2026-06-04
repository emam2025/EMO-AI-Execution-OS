"""Phase F3 — Scheduling Policies: Fairness, Priority, Affinity.

FairnessPolicy:  Weighted Fair Queueing — prevents starvation.
PriorityScheduler: P0 (Critical) → P3 (Background) with time limits.
AffinityRules:    Data locality / GPU topology preference.

Each policy returns a SchedulingDecision with ReasonCode.

Ref: Canon LAW 8 (Fairness), LAW 10 (Resource constraints)
Ref: Canon RULE 1 (Deterministic), RULE 3 (Recoverability)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("emo_ai.scheduling.policies")


class ReasonCode(str, Enum):
    FAIRNESS_BOOST = "fairness_boost"
    PRIORITY_PREEMPT = "priority_preempt"
    AFFINITY_MATCH = "affinity_match"
    STARVATION_PREVENTION = "starvation_prevention"
    QUOTA_EXCEEDED = "quota_exceeded"
    RESOURCE_FIT = "resource_fit"
    AFFINITY_MISMATCH = "affinity_mismatch"
    LOAD_BALANCE = "load_balance"
    PRIORITY_QUEUED = "priority_queued"
    NO_CAPACITY = "no_capacity"


@dataclass
class MatchScore:
    score: float = 0.0
    matched: bool = False
    reason: str = ""
    violations: List[str] = field(default_factory=list)


@dataclass
class SchedulingDecision:
    worker_id: str = ""
    accepted: bool = False
    reason_code: ReasonCode = ReasonCode.RESOURCE_FIT
    reason: str = ""
    score: float = 0.0
    preempted_id: str = ""
    queue_position: int = 0


# ── FairnessPolicy ──────────────────────────────────────────

class FairnessPolicy:
    """Weighted Fair Queueing — prevents task starvation.

    LAW 8: Tracks cumulative resource usage and boosts starved tasks.
    RULE 1: Deterministic weight computation.
    """

    def __init__(self, decay_factor: float = 0.95):
        self._usage: Dict[str, float] = {}
        self._start_times: Dict[str, float] = {}
        self._decay = decay_factor

    def record_usage(self, worker_id: str, cpu_used: float) -> None:
        now = time.time()
        prev = self._usage.get(worker_id, 0.0)
        last = self._start_times.get(worker_id, now)
        elapsed = max(now - last, 1.0)
        decayed = prev * (self._decay ** (elapsed / 60.0))
        self._usage[worker_id] = decayed + cpu_used
        self._start_times[worker_id] = now

    def compute_weight(self, worker_id: str) -> float:
        """Return fairness weight (1.0 = neutral, >1.0 = under-served).

        Workers with below-average usage get a boost (>1.0).
        Workers with above-average usage get a penalty (<1.0).
        """
        if not self._usage:
            return 1.0

        avg = sum(self._usage.values()) / len(self._usage)
        w_usage = self._usage.get(worker_id, 0.0)

        if avg < 0.01:
            return 1.0

        ratio = w_usage / avg
        if ratio < 0.5:
            return 1.2
        elif ratio < 0.8:
            return 1.1
        elif ratio > 1.5:
            return 0.85
        elif ratio > 1.2:
            return 0.95
        return 1.0

    def detect_starvation(
        self,
        execution_id: str,
        wait_time_sec: float,
        max_wait: float = 300.0,
    ) -> SchedulingDecision:
        if wait_time_sec <= max_wait:
            return SchedulingDecision(accepted=True)

        if wait_time_sec > max_wait * 2:
            return SchedulingDecision(
                accepted=True,
                reason_code=ReasonCode.STARVATION_PREVENTION,
                reason=f"Starvation detected: waited {wait_time_sec:.0f}s",
            )

        return SchedulingDecision(
            accepted=True,
            reason_code=ReasonCode.FAIRNESS_BOOST,
            reason=f"Long wait ({wait_time_sec:.0f}s) — fairness boost",
        )

    def reset(self) -> None:
        self._usage.clear()
        self._start_times.clear()


# ── PriorityScheduler ───────────────────────────────────────

class PriorityScheduler:
    """P0 (Critical) → P3 (Background) priority tiers.

    Tier  | Label       | Max Wait (s) | Preempts
    ------+-------------+--------------+-----------
    P0    | Critical    | 10           | P2, P3
    P1    | High        | 30           | P3
    P2    | Normal      | 60           | (none)
    P3    | Background  | 300          | (none)

    RULE 3: Preemption only when priority diff >= 2.
    """

    TIER_LABELS = {0: "critical", 1: "high", 2: "normal", 3: "background"}
    MAX_WAIT = {0: 10.0, 1: 30.0, 2: 60.0, 3: 300.0}
    PREEMPTION_TABLE = {0: {2, 3}, 1: {3}, 2: set(), 3: set()}

    def __init__(self) -> None:
        self._queued: Dict[str, tuple[int, float]] = {}
        self._boosts: Dict[str, int] = {}

    def enqueue(self, execution_id: str, priority: int) -> SchedulingDecision:
        now = time.time()
        self._queued[execution_id] = (priority, now)
        return SchedulingDecision(
            accepted=True,
            reason_code=ReasonCode.PRIORITY_QUEUED,
            reason=f"Queued at priority {priority} ({self.TIER_LABELS.get(priority, 'unknown')})",
            queue_position=len(self._queued),
        )

    def dequeue(self, execution_id: str) -> None:
        self._queued.pop(execution_id, None)
        self._boosts.pop(execution_id, None)

    def select_preemption_target(
        self,
        incoming_priority: int,
        active_tasks: List[Any],
    ) -> Optional[str]:
        """Select a task to preempt.

        Only preempts if priority diff >= 2 (i.e. P0 preempts P2/P3,
        P1 preempts P3).
        """
        preemptable_tiers = self.PREEMPTION_TABLE.get(incoming_priority, set())
        if not preemptable_tiers:
            return None

        candidates: List[tuple[int, str]] = []
        for task in active_tasks:
            if isinstance(task, dict):
                task_id = task.get("execution_id", "")
                task_prio = task.get("priority", 2)
            else:
                task_id = str(task)
                task_prio = getattr(task, "priority", 2)

            if task_prio in preemptable_tiers:
                candidates.append((task_prio, task_id))

        if not candidates:
            return None

        candidates.sort(key=lambda c: c[0], reverse=True)
        return candidates[0][1]

    def check_time_limit(
        self,
        execution_id: str,
        priority: int,
    ) -> SchedulingDecision:
        entry = self._queued.get(execution_id)
        if entry is None:
            return SchedulingDecision(accepted=True)

        _, enqueued_at = entry
        elapsed = time.time() - enqueued_at
        limit = self.MAX_WAIT.get(priority, 60.0)

        if elapsed <= limit:
            return SchedulingDecision(
                accepted=True,
                reason=f"Within P{priority} time limit ({elapsed:.0f}s ≤ {limit:.0f}s)",
            )

        boost_count = self._boosts.get(execution_id, 0)
        if boost_count < 2 and priority > 0:
            new_priority = max(0, priority - 1)
            self._boosts[execution_id] = boost_count + 1
            return SchedulingDecision(
                accepted=True,
                reason_code=ReasonCode.PRIORITY_PREEMPT,
                reason=f"Priority boost P{priority} → P{new_priority} (waited {elapsed:.0f}s)",
            )

        return SchedulingDecision(
            accepted=True,
            reason_code=ReasonCode.PRIORITY_PREEMPT,
            reason=f"Exceeded P{priority} time limit ({elapsed:.0f}s > {limit:.0f}s)",
        )

    def reset(self) -> None:
        self._queued.clear()
        self._boosts.clear()


# ── AffinityRules ───────────────────────────────────────────

class AffinityRules:
    """Data locality and GPU topology preference rules.

    RULE 1: Deterministic scoring — same inputs → same affinity.
    """

    def evaluate(
        self,
        execution_id: str,
        worker_capabilities: Dict[str, Any],
        preferred_worker: str = "",
    ) -> float:
        """Return affinity score (0.0 = no affinity, 1.0 = strong affinity)."""
        score = 0.0

        worker_id = worker_capabilities.get("worker_id", "")
        if preferred_worker and worker_id == preferred_worker:
            score += 0.5

        affinity_tags = worker_capabilities.get("affinity_tags", [])
        if isinstance(affinity_tags, list):
            for tag in affinity_tags:
                if tag in execution_id:
                    score += 0.3

        gpu_available = worker_capabilities.get("gpu_available", False)
        if gpu_available:
            score += 0.2

        return min(1.0, score)

    def check_data_locality(
        self,
        worker_id: str,
        data_locations: List[str],
    ) -> bool:
        """Check if worker is co-located with required data."""
        return worker_id in data_locations

    def check_gpu_topology(
        self,
        worker_capabilities: Dict[str, Any],
        required_gpu: int = 0,
    ) -> bool:
        """Check if worker's GPU topology meets requirements."""
        if required_gpu == 0:
            return True
        gpu_mem = int(worker_capabilities.get("available_gpu", 0))
        return gpu_mem >= required_gpu
