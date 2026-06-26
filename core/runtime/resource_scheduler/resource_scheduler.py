"""Phase F3 — Resource Scheduler implementation.  # LAW-5 # LAW-8 # LAW-11

Implements IResourceScheduler: match_resources, assign_worker,
preempt_if_needed, release_resources.

Also exposes the legacy ControlPlane scheduling API: select_worker,
register_worker, allocate, release, set_quota, cluster_summary, etc.

Coordinates QuotaArbitrator, FairnessEngine, TopologyMapper,
AllocationStateMachine, and StarvationHandler.

Ref: Canon LAW 5 (Observability), LAW 8 (Fairness), LAW 11 (No global state)
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Dict, List, Optional, Set

from core.runtime.models.resource_scheduler_models import (
    AssignmentRecord,
    PriorityTier,
    ResourceOffer,
    ResourceRequest,
    SchedulingDecision,
    SchedulingStatus,
)
from core.runtime.resource_scheduler.allocation_state_machine import (
    AllocationState,
    AllocationStateMachine,
)
from core.runtime.resource_scheduler.fairness_engine import FairnessEngine
from core.runtime.resource_scheduler.quota_arbitrator import QuotaArbitrator
from core.runtime.resource_scheduler.starvation_handler import StarvationHandler
from core.runtime.resource_scheduler.topology_mapper import TopologyMapper

logger = logging.getLogger("emo_ai.resource_scheduler")


# ── Legacy model types (used by ControlPlaneBrain) ────────────

class Priority(IntEnum):
    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3
    BACKGROUND = 4


@dataclass
class ResourceRequirements:
    cpu_cores: float = 1.0
    memory_mb: float = 256.0
    gpu_cores: int = 0
    gpu_memory_mb: float = 0.0
    disk_mb: float = 1024.0
    network_bandwidth_mbps: float = 100.0

    def requires_gpu(self) -> bool:
        return self.gpu_cores > 0 or self.gpu_memory_mb > 0


@dataclass
class WorkerResource:
    worker_id: str
    node_id: str
    total_cpu: float = 8.0
    total_memory: float = 8192.0
    total_gpu: int = 0
    total_gpu_memory: float = 0.0
    used_cpu: float = 0.0
    used_memory: float = 0.0
    used_gpu: int = 0
    used_gpu_memory: float = 0.0
    active_tasks: int = 0
    capacity: int = 10
    tags: Dict[str, str] = field(default_factory=dict)

    @property
    def cpu_available(self) -> float:
        return self.total_cpu - self.used_cpu

    @property
    def memory_available(self) -> float:
        return self.total_memory - self.used_memory

    @property
    def gpu_available(self) -> int:
        return self.total_gpu - self.used_gpu

    @property
    def gpu_memory_available(self) -> float:
        return self.total_gpu_memory - self.used_gpu_memory

    @property
    def cpu_utilization(self) -> float:
        return self.used_cpu / self.total_cpu if self.total_cpu > 0 else 1.0

    @property
    def memory_utilization(self) -> float:
        return self.used_memory / self.total_memory if self.total_memory > 0 else 1.0

    def can_fit(self, req: ResourceRequirements) -> bool:
        return (
            self.cpu_available >= req.cpu_cores
            and self.memory_available >= req.memory_mb
            and self.gpu_available >= req.gpu_cores
            and self.gpu_memory_available >= req.gpu_memory_mb
            and self.active_tasks < self.capacity
        )

    def allocate(self, req: ResourceRequirements) -> None:
        self.used_cpu += req.cpu_cores
        self.used_memory += req.memory_mb
        self.used_gpu += req.gpu_cores
        self.used_gpu_memory += req.gpu_memory_mb
        self.active_tasks += 1

    def release(self, req: ResourceRequirements) -> None:
        self.used_cpu = max(0.0, self.used_cpu - req.cpu_cores)
        self.used_memory = max(0.0, self.used_memory - req.memory_mb)
        self.used_gpu = max(0, self.used_gpu - req.gpu_cores)
        self.used_gpu_memory = max(0.0, self.used_gpu_memory - req.gpu_memory_mb)
        self.active_tasks = max(0, self.active_tasks - 1)


@dataclass
class UserQuota:
    user_id: str
    max_cpu: float = 32.0
    max_memory: float = 32768.0
    max_gpu: int = 4
    max_executions: int = 20
    used_cpu: float = 0.0
    used_memory: float = 0.0
    used_gpu: int = 0
    active_executions: int = 0

    def has_quota(self, req: ResourceRequirements) -> bool:
        return (
            self.used_cpu + req.cpu_cores <= self.max_cpu
            and self.used_memory + req.memory_mb <= self.max_memory
            and self.used_gpu + req.gpu_cores <= self.max_gpu
            and self.active_executions < self.max_executions
        )

    def consume(self, req: ResourceRequirements) -> None:
        self.used_cpu += req.cpu_cores
        self.used_memory += req.memory_mb
        self.used_gpu += req.gpu_cores
        self.active_executions += 1

    def release(self, req: ResourceRequirements) -> None:
        self.used_cpu = max(0.0, self.used_cpu - req.cpu_cores)
        self.used_memory = max(0.0, self.used_memory - req.memory_mb)
        self.used_gpu = max(0, self.used_gpu - req.gpu_cores)
        self.active_executions = max(0, self.active_executions - 1)


@dataclass
class SchedulingResult:
    node_id: str
    worker_id: str
    score: float
    reason: str


class FairnessModel:
    """Weighted fair sharing across users/tenants."""

    def __init__(self) -> None:
        self._weights: Dict[str, float] = {}
        self._usage: Dict[str, float] = defaultdict(float)

    def set_weight(self, user_id: str, weight: float) -> None:
        self._weights[user_id] = weight

    def record_usage(self, user_id: str, amount: float) -> None:
        self._usage[user_id] += amount

    def record_release(self, user_id: str, amount: float) -> None:
        self._usage[user_id] = max(0.0, self._usage[user_id] - amount)

    def fairness_score(self, user_id: str) -> float:
        if not self._weights or not self._usage:
            return 1.0
        total_weight = sum(self._weights.values())
        if total_weight == 0:
            return 1.0
        fair_share = self._weights.get(user_id, 1.0) / total_weight
        total_usage = sum(self._usage.values())
        if total_usage == 0:
            return 1.0
        actual_share = self._usage.get(user_id, 0.0) / total_usage
        if actual_share <= fair_share:
            return 1.0
        return max(0.1, fair_share / actual_share)


@dataclass
class PriorityQueue:
    priority: Priority
    items: List[Dict[str, Any]] = field(default_factory=list)

    def push(self, item: Dict[str, Any]) -> None:
        self.items.append(item)

    def pop(self) -> Optional[Dict[str, Any]]:
        if self.items:
            return self.items.pop(0)
        return None

    @property
    def size(self) -> int:
        return len(self.items)


class PriorityScheduler:
    """Multi-level priority queue with aging."""

    def __init__(self) -> None:
        self._queues: Dict[Priority, PriorityQueue] = {
            p: PriorityQueue(priority=p) for p in Priority
        }
        self._aging_factor: float = 0.05
        self._aging_interval: float = 10.0
        self._last_aging: float = time.time()

    def submit(self, task: Dict[str, Any], priority: Priority = Priority.NORMAL) -> None:
        task["_submitted_at"] = time.time()
        task["_priority"] = priority
        self._queues[priority].push(task)

    def select(self) -> Optional[Dict[str, Any]]:
        self._age_tasks()
        for p in sorted(self._queues.keys()):
            if self._queues[p].size > 0:
                return self._queues[p].pop()
        return None

    def _age_tasks(self) -> None:
        now = time.time()
        if now - self._last_aging < self._aging_interval:
            return
        self._last_aging = now
        for p in Priority:
            if p == Priority.CRITICAL:
                continue
            queue = self._queues[p]
            for item in queue.items:
                age = now - item.get("_submitted_at", now)
                boost = int(age / self._aging_interval)
                item["_aging_boost"] = boost

    def priority_score(self, task: Dict[str, Any]) -> float:
        p = task.get("_priority", Priority.NORMAL)
        base = {Priority.CRITICAL: 100, Priority.HIGH: 75,
                Priority.NORMAL: 50, Priority.LOW: 25, Priority.BACKGROUND: 10}
        score = base.get(p, 50)
        aging = task.get("_aging_boost", 0) * 5
        return min(100.0, score + aging)


# ── Main ResourceScheduler ────────────────────────────────────

class ResourceScheduler:  # ←→ IResourceScheduler
    """Matches resource requests to available workers with fairness.

    LAW 5: All decisions return SchedulingDecision with reason.
    LAW 8: Fair distribution + starvation prevention.
    LAW 11: No global state — per-instance tracking via AssignmentRecord.
    """

    def __init__(
        self,
        quota_arbitrator: Optional[QuotaArbitrator] = None,
        fairness_engine: Optional[FairnessEngine] = None,
        topology_mapper: Optional[TopologyMapper] = None,
        state_machine: Optional[AllocationStateMachine] = None,
        starvation_handler: Optional[StarvationHandler] = None,
        db: Any = None,
    ) -> None:
        self._quota = quota_arbitrator or QuotaArbitrator()
        self._fairness = fairness_engine or FairnessEngine()
        self._topology = topology_mapper or TopologyMapper()
        self._sm = state_machine or AllocationStateMachine()
        self._starvation = starvation_handler or StarvationHandler()
        self._db = db
        self._assignments: Dict[str, AssignmentRecord] = {}

        # Legacy scheduling state (used by ControlPlaneBrain)
        self._workers: Dict[str, WorkerResource] = {}
        self._quotas: Dict[str, UserQuota] = {}
        self._fairness_model = FairnessModel()
        self._priority_scheduler = PriorityScheduler()
        self._gpu_nodes: Set[str] = set()

    @property
    def active_assignments(self) -> Dict[str, AssignmentRecord]:
        return dict(self._assignments)

    @property
    def quota(self) -> QuotaArbitrator:
        return self._quota

    @property
    def fairness(self) -> FairnessEngine:
        return self._fairness

    @property
    def topology(self) -> TopologyMapper:
        return self._topology

    @property
    def starvation_handler(self) -> StarvationHandler:
        return self._starvation

    # ── Legacy worker management (ControlPlaneBrain API) ───────

    def register_worker(self, worker_id: str, node_id: str,
                        total_cpu: float = 8.0, total_memory: float = 8192.0,
                        total_gpu: int = 0, total_gpu_memory: float = 0.0,
                        capacity: int = 10,
                        tags: Optional[Dict[str, str]] = None) -> None:
        self._workers[worker_id] = WorkerResource(
            worker_id=worker_id, node_id=node_id,
            total_cpu=total_cpu, total_memory=total_memory,
            total_gpu=total_gpu, total_gpu_memory=total_gpu_memory,
            capacity=capacity, tags=tags or {},
        )
        if total_gpu > 0:
            self._gpu_nodes.add(node_id)
        logger.info("Registered worker %s (node=%s, cpu=%.1f, gpu=%d)",
                     worker_id, node_id, total_cpu, total_gpu)

    def unregister_worker(self, worker_id: str) -> None:
        worker = self._workers.pop(worker_id, None)
        if worker:
            self._gpu_nodes.discard(worker.node_id)

    def update_worker_load(self, worker_id: str, used_cpu: float = -1.0,
                           used_memory: float = -1.0, active_tasks: int = -1) -> None:
        worker = self._workers.get(worker_id)
        if not worker:
            return
        if used_cpu >= 0:
            worker.used_cpu = used_cpu
        if used_memory >= 0:
            worker.used_memory = used_memory
        if active_tasks >= 0:
            worker.active_tasks = active_tasks

    # ── Legacy quota management ────────────────────────────────

    def set_quota(self, user_id: str, max_cpu: float = 32.0,
                  max_memory: float = 32768.0, max_gpu: int = 4,
                  max_executions: int = 20) -> None:
        if user_id in self._quotas:
            q = self._quotas[user_id]
            q.max_cpu = max_cpu
            q.max_memory = max_memory
            q.max_gpu = max_gpu
            q.max_executions = max_executions
        else:
            self._quotas[user_id] = UserQuota(
                user_id=user_id, max_cpu=max_cpu,
                max_memory=max_memory, max_gpu=max_gpu,
                max_executions=max_executions,
            )

    def get_quota(self, user_id: str) -> Optional[UserQuota]:
        return self._quotas.get(user_id)

    # ── Legacy fairness ────────────────────────────────────────

    def set_user_weight(self, user_id: str, weight: float) -> None:
        self._fairness_model.set_weight(user_id, weight)

    # ── Legacy priority ────────────────────────────────────────

    def submit_task(self, task: Dict[str, Any],
                    priority: Priority = Priority.NORMAL) -> None:
        self._priority_scheduler.submit(task, priority)

    def select_next_task(self) -> Optional[Dict[str, Any]]:
        return self._priority_scheduler.select()

    # ── Legacy core scheduling ─────────────────────────────────

    def select_worker(self, task: Dict[str, Any],
                      user_id: str = "default",
                      requirements: Optional[ResourceRequirements] = None) -> SchedulingResult:
        req = requirements or ResourceRequirements()
        priority = task.get("_priority", Priority.NORMAL)

        quota = self._quotas.get(user_id)
        if quota and not quota.has_quota(req):
            return SchedulingResult(
                node_id="", worker_id="",
                score=-1.0,
                reason=f"User {user_id} exceeds quota",
            )

        candidates: List[tuple[str, float]] = []
        for wid, w in self._workers.items():
            if not w.can_fit(req):
                continue
            if req.requires_gpu() and w.total_gpu == 0:
                continue
            if not req.requires_gpu() and w.total_gpu > 0:
                continue
            score = self._score_worker(w, req, task, priority)
            candidates.append((wid, score))

        if not candidates:
            return SchedulingResult(
                node_id="", worker_id="",
                score=-1.0,
                reason="No suitable worker found",
            )

        candidates.sort(key=lambda x: x[1], reverse=True)
        best_wid = candidates[0][0]
        best_score = candidates[0][1]
        best_worker = self._workers[best_wid]

        fairness = self._fairness_model.fairness_score(user_id)
        adjusted = best_score * fairness

        return SchedulingResult(
            node_id=best_worker.node_id,
            worker_id=best_wid,
            score=adjusted,
            reason=f"cpu={best_worker.cpu_utilization:.2f} "
                   f"mem={best_worker.memory_utilization:.2f} "
                   f"fairness={fairness:.2f}",
        )

    def _score_worker(self, worker: WorkerResource,
                      req: ResourceRequirements,
                      task: Dict[str, Any],
                      priority: Priority) -> float:
        scores = []
        cpu_score = max(0, 100 * (1.0 - worker.cpu_utilization))
        scores.append(("cpu", cpu_score, 0.35))
        mem_score = max(0, 100 * (1.0 - worker.memory_utilization))
        scores.append(("mem", mem_score, 0.20))
        if req.requires_gpu():
            gpu_avail = worker.gpu_available / max(1, worker.total_gpu)
            gpu_score = 100 * gpu_avail
            scores.append(("gpu", gpu_score, 0.25))
        else:
            scores.append(("gpu", 50.0, 0.10))
        cap_score = 100 * (1.0 - worker.active_tasks / max(1, worker.capacity))
        scores.append(("capacity", cap_score, 0.15))
        prio_map = {Priority.CRITICAL: 20, Priority.HIGH: 10,
                    Priority.NORMAL: 0, Priority.LOW: -10, Priority.BACKGROUND: -20}
        prio_bias = prio_map.get(priority, 0)
        scores.append(("priority", prio_bias, 0.05 + (0.10 if priority == Priority.CRITICAL else 0)))
        total_weight = sum(w for _, _, w in scores)
        score = sum(s * (w / total_weight) for _, s, w in scores)
        return score + prio_bias

    def allocate(self, worker_id: str, req: ResourceRequirements,
                 user_id: str = "default") -> bool:
        worker = self._workers.get(worker_id)
        if not worker or not worker.can_fit(req):
            return False
        quota = self._quotas.get(user_id)
        if quota and not quota.has_quota(req):
            return False
        worker.allocate(req)
        if quota:
            quota.consume(req)
        resource_cost = req.cpu_cores + req.memory_mb / 1024
        self._fairness_model.record_usage(user_id, resource_cost)
        return True

    def release(self, worker_id: str, req: ResourceRequirements,
                user_id: str = "default") -> None:
        worker = self._workers.get(worker_id)
        if worker:
            worker.release(req)
        quota = self._quotas.get(user_id)
        if quota:
            quota.release(req)
        resource_cost = req.cpu_cores + req.memory_mb / 1024
        self._fairness_model.record_release(user_id, resource_cost)

    # ── Legacy introspection ───────────────────────────────────

    def worker_summary(self, worker_id: str) -> Optional[Dict[str, Any]]:
        w = self._workers.get(worker_id)
        if not w:
            return None
        return {
            "worker_id": w.worker_id,
            "node_id": w.node_id,
            "cpu": f"{w.used_cpu:.1f}/{w.total_cpu:.1f}",
            "memory": f"{w.used_memory:.0f}/{w.total_memory:.0f}",
            "gpu": f"{w.used_gpu}/{w.total_gpu}",
            "tasks": f"{w.active_tasks}/{w.capacity}",
        }

    def cluster_summary(self) -> Dict[str, Any]:
        total_cpu = sum(w.total_cpu for w in self._workers.values())
        total_mem = sum(w.total_memory for w in self._workers.values())
        total_gpu = sum(w.total_gpu for w in self._workers.values())
        used_cpu = sum(w.used_cpu for w in self._workers.values())
        used_mem = sum(w.used_memory for w in self._workers.values())
        used_gpu = sum(w.used_gpu for w in self._workers.values())
        cpu_pct = (used_cpu / total_cpu * 100) if total_cpu > 0 else 0.0
        return {
            "workers": len(self._workers),
            "gpu_nodes": len(self._gpu_nodes),
            "cpu": f"{used_cpu:.1f}/{total_cpu:.1f} ({cpu_pct:.0f}%)",
            "memory": f"{used_mem:.0f}/{total_mem:.0f}",
            "gpu": f"{used_gpu}/{total_gpu}",
        }

    # ── match_resources ───────────────────────────────────────

    def match_resources(  # LAW-5, LAW-8, RULE-1
        self,
        request: ResourceRequest,
        available_offers: List[ResourceOffer],
    ) -> SchedulingDecision:
        mapping = self._topology.map_to_hardware(request, available_offers)

        if mapping.worker_id:
            self._sm.transition(AllocationState.MATCHED)
            self._sm.transition(AllocationState.RESERVED, offer_available=True)

            for offer in available_offers:
                if offer.worker_id == mapping.worker_id:
                    return SchedulingDecision(
                        status=SchedulingStatus.ASSIGNED,
                        assigned_worker=mapping.worker_id,
                        reason=(
                            f"Matched worker {mapping.worker_id} "
                            f"(score={mapping.score})"
                        ),
                        timestamp=time.time(),
                    )

        if request.max_wait_sec > 0:
            self._starvation.enqueue(request)
            self._sm.transition(AllocationState.MATCHED)
            self._sm.transition(AllocationState.QUEUED)
            return SchedulingDecision(
                status=SchedulingStatus.QUEUED,
                reason="No matching offer — queued",
                timestamp=time.time(),
            )

        if request.priority in (PriorityTier.CRITICAL, PriorityTier.HIGH):
            preempted = self.preempt_if_needed(request, [
                self._assignments[eid]
                for eid in list(self._assignments.keys())
            ])
            if preempted:
                return preempted

        return SchedulingDecision(
            status=SchedulingStatus.REJECTED,
            reason="No matching offer and cannot wait",
            timestamp=time.time(),
        )

    # ── assign_worker ─────────────────────────────────────────

    def assign_worker(  # RULE-5
        self,
        assignment: SchedulingDecision,
        offer: ResourceOffer,
    ) -> bool:
        if not assignment.assigned_worker:
            logger.debug("No worker in assignment")
            return False

        if assignment.assigned_worker in self._assignments:
            logger.debug("Worker %s already assigned (idempotent)", assignment.assigned_worker)
            return True

        self._sm.transition(AllocationState.ASSIGNED)

        record = AssignmentRecord(
            execution_id=assignment.preempted_id or assignment.assigned_worker,
            worker_id=assignment.assigned_worker,
            resources=ResourceRequest(),
            assigned_at=time.time(),
            preemptible=True,
            checkpoint_available=True,
        )
        self._assignments[assignment.assigned_worker] = record

        logger.info("Assigned worker %s", assignment.assigned_worker)
        return True

    # ── preempt_if_needed ─────────────────────────────────────

    def preempt_if_needed(  # LAW-8, RULE-3
        self,
        request: ResourceRequest,
        _active_assignments: List[SchedulingDecision],
    ) -> Optional[SchedulingDecision]:
        candidates: List[AssignmentRecord] = []
        for rec in self._assignments.values():
            ok, _ = self._sm.can_preempt(request, rec)
            if ok:
                candidates.append(rec)

        if not candidates:
            return None

        candidates.sort(key=lambda r: (
            r.resources.priority.value if r.resources else PriorityTier.BATCH.value
        ))

        target = candidates[0]
        self._sm.transition(AllocationState.PREEMPTED,
                            request=request, record=target)
        self._sm.transition(AllocationState.QUEUED, preempted=True)

        if target.execution_id in self._assignments:
            del self._assignments[target.execution_id]

        return SchedulingDecision(
            status=SchedulingStatus.PREEMPTED,
            assigned_worker=target.worker_id,
            preempted_id=target.execution_id,
            reason=(
                f"Preempted {target.execution_id} for {request.execution_id}"
            ),
            timestamp=time.time(),
        )

    # ── release_resources ─────────────────────────────────────

    def release_resources(  # LAW-11, RULE-2
        self,
        execution_id: str,
        assignment: SchedulingDecision,
    ) -> bool:
        if execution_id in self._assignments:
            del self._assignments[execution_id]
            logger.info("Released resources for %s", execution_id)
            return True

        worker_id = assignment.assigned_worker
        if worker_id in self._assignments:
            del self._assignments[worker_id]
            logger.info("Released resources for worker %s", worker_id)
            return True

        logger.debug("No resources to release for %s", execution_id)
        return False

    # ── Async persistence helpers (P1-01) ──────────────────────────

    def set_db(self, db: Any) -> None:
        self._db = db

    async def async_register_worker(
        self, worker_id: str, node_id: str,
        total_cpu: float = 8.0, total_memory: float = 8192.0,
        total_gpu: int = 0, total_gpu_memory: float = 0.0,
        capacity: int = 10,
        tags: Optional[Dict[str, str]] = None,
    ) -> None:
        self.register_worker(worker_id, node_id, total_cpu, total_memory,
                             total_gpu, total_gpu_memory, capacity, tags)
        if self._db is not None:
            await self._db.save_worker(
                worker_id=worker_id, node_id=node_id,
                total_cpu=total_cpu, total_memory=total_memory,
                total_gpu=total_gpu, total_gpu_memory=total_gpu_memory,
                capacity=capacity, tags=tags or {},
            )

    async def async_unregister_worker(self, worker_id: str) -> None:
        self.unregister_worker(worker_id)
        if self._db is not None:
            await self._db.delete_worker(worker_id)

    async def async_set_quota(self, user_id: str, max_cpu: float = 32.0,
                              max_memory: float = 32768.0, max_gpu: int = 4,
                              max_executions: int = 20) -> None:
        self.set_quota(user_id, max_cpu, max_memory, max_gpu, max_executions)
        if self._db is not None:
            await self._db.save_quota(
                user_id=user_id, max_cpu=max_cpu,
                max_memory=max_memory, max_gpu=max_gpu,
                max_executions=max_executions,
            )

    async def load_workers_from_db(self) -> int:
        if self._db is None:
            return 0
        try:
            rows = await self._db.list_workers()
            for w in rows:
                self._workers[w["worker_id"]] = WorkerResource(
                    worker_id=w["worker_id"], node_id=w.get("node_id", ""),
                    total_cpu=w.get("total_cpu", 8.0),
                    total_memory=w.get("total_memory", 8192.0),
                    total_gpu=w.get("total_gpu", 0),
                    total_gpu_memory=w.get("total_gpu_memory", 0.0),
                    capacity=w.get("capacity", 10),
                    tags=w.get("tags", {}),
                )
                if w.get("total_gpu", 0) > 0:
                    self._gpu_nodes.add(w.get("node_id", ""))
            return len(rows)
        except Exception:
            return 0

    async def load_quotas_from_db(self) -> int:
        if self._db is None:
            return 0
        try:
            rows = await self._db.list_quotas()
            for q in rows:
                self._quotas[q["user_id"]] = UserQuota(
                    user_id=q["user_id"],
                    max_cpu=q.get("max_cpu", 32.0),
                    max_memory=q.get("max_memory", 32768.0),
                    max_gpu=q.get("max_gpu", 4),
                    max_executions=q.get("max_executions", 20),
                )
            return len(rows)
        except Exception:
            return 0
