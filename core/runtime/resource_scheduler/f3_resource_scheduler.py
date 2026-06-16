"""F3 — Resource Scheduler: scheduling and quota enforcement.

Decides where and when to execute tasks based on available resources.
Delegates to D8 services via constructor injection.

Ref: DEVELOPER.md §15.10
Ref: Canon LAW 10, LAW 13, LAW 23
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from core.interfaces.state_store import IExecutionStateStore
from core.models.resource_scheduler import (
    AllocationStatus,
    ResourceAllocation,
    ResourceRequest,
    WorkerQuota,
)

logger = logging.getLogger("emo_ai.resource_scheduler.f3")


class F3ResourceScheduler:
    """Schedules tasks based on available resources and enforces quotas.

    LAW 13: Dependencies injected via constructor.
    No direct execution — decides allocation only.
    """

    def __init__(
        self,
        state_store: IExecutionStateStore,
    ):
        self._state_store = state_store
        self._workers: Dict[str, Dict[str, Any]] = {}
        self._quotas: Dict[str, WorkerQuota] = {}

    def register_worker(
        self,
        worker_id: str,
        cpu_cores: float,
        memory_mb: int,
    ) -> None:
        """Register a worker with its total resources."""
        self._workers[worker_id] = {
            "cpu_cores": cpu_cores,
            "memory_mb": memory_mb,
            "used_cpu": 0.0,
            "used_memory": 0,
        }

    def schedule_execution(
        self,
        request: ResourceRequest,
    ) -> ResourceAllocation:
        """Evaluate request and allocate to the best available worker."""
        best_worker: Optional[str] = None
        best_score = -1.0

        for worker_id, worker in self._workers.items():
            available_cpu = worker["cpu_cores"] - worker["used_cpu"]
            available_memory = worker["memory_mb"] - worker["used_memory"]

            if available_cpu >= request.cpu_cores and available_memory >= request.memory_mb:
                score = available_cpu / worker["cpu_cores"]
                if score > best_score:
                    best_score = score
                    best_worker = worker_id

        if best_worker is None:
            return ResourceAllocation(
                execution_id=request.execution_id,
                worker_id="",
                allocated_cpu=0.0,
                allocated_memory=0,
                status=AllocationStatus.REJECTED,
            )

        worker = self._workers[best_worker]
        worker["used_cpu"] += request.cpu_cores
        worker["used_memory"] += request.memory_mb

        return ResourceAllocation(
            execution_id=request.execution_id,
            worker_id=best_worker,
            allocated_cpu=request.cpu_cores,
            allocated_memory=request.memory_mb,
            status=AllocationStatus.ALLOCATED,
        )

    def check_quotas(
        self,
        worker_id: str,
        required_cpu: float,
        required_memory: int,
    ) -> bool:
        """Check if worker has sufficient resources within quota."""
        worker = self._workers.get(worker_id)
        if worker is None:
            return False

        available_cpu = worker["cpu_cores"] - worker["used_cpu"]
        available_memory = worker["memory_mb"] - worker["used_memory"]

        return available_cpu >= required_cpu and available_memory >= required_memory

    def enforce_limits(self, worker_id: str) -> bool:
        """Enforce strict resource limits on a worker."""
        worker = self._workers.get(worker_id)
        if worker is None:
            return False

        if worker["used_cpu"] > worker["cpu_cores"]:
            worker["used_cpu"] = worker["cpu_cores"]
            return False
        if worker["used_memory"] > worker["memory_mb"]:
            worker["used_memory"] = worker["memory_mb"]
            return False

        return True

    def get_available_capacity(self) -> Dict[str, Any]:
        """Return available capacity across the cluster."""
        total_cpu = 0.0
        used_cpu = 0.0
        total_memory = 0
        used_memory = 0
        worker_count = 0

        for worker in self._workers.values():
            total_cpu += worker["cpu_cores"]
            used_cpu += worker["used_cpu"]
            total_memory += worker["memory_mb"]
            used_memory += worker["used_memory"]
            worker_count += 1

        return {
            "worker_count": worker_count,
            "total_cpu": total_cpu,
            "available_cpu": total_cpu - used_cpu,
            "total_memory": total_memory,
            "available_memory": total_memory - used_memory,
        }
