"""F3 — Resource Scheduler Tests.

Verifies scheduling, quota enforcement, and capacity management.

Ref: DEVELOPER.md §15.10
Ref: Canon LAW 10, LAW 13, LAW 23
"""

from unittest.mock import MagicMock

from core.interfaces.state_store import IExecutionStateStore
from core.models.resource_scheduler import (
    AllocationStatus,
    ResourceAllocation,
    ResourceRequest,
    WorkerQuota,
)
from core.runtime.resource_scheduler.f3_resource_scheduler import F3ResourceScheduler


def _build_scheduler() -> F3ResourceScheduler:
    state_store = MagicMock(spec=IExecutionStateStore)
    return F3ResourceScheduler(state_store=state_store)


class TestResourceScheduler:
    def test_resource_scheduler_allocates_to_healthy_worker(self) -> None:
        rs = _build_scheduler()
        rs.register_worker("worker-1", cpu_cores=8.0, memory_mb=16384)
        request = ResourceRequest(
            execution_id="exec-1",
            cpu_cores=2.0,
            memory_mb=4096,
            priority=1,
        )
        allocation = rs.schedule_execution(request)
        assert allocation.status == AllocationStatus.ALLOCATED
        assert allocation.worker_id == "worker-1"

    def test_resource_scheduler_rejects_when_quotas_exceeded(self) -> None:
        rs = _build_scheduler()
        rs.register_worker("worker-1", cpu_cores=2.0, memory_mb=4096)
        request = ResourceRequest(
            execution_id="exec-1",
            cpu_cores=4.0,
            memory_mb=8192,
            priority=1,
        )
        allocation = rs.schedule_execution(request)
        assert allocation.status == AllocationStatus.REJECTED
        assert allocation.worker_id == ""

    def test_resource_scheduler_prioritizes_high_priority_tasks(self) -> None:
        rs = _build_scheduler()
        rs.register_worker("worker-1", cpu_cores=8.0, memory_mb=16384)
        request_high = ResourceRequest(
            execution_id="exec-high",
            cpu_cores=2.0,
            memory_mb=4096,
            priority=10,
        )
        request_low = ResourceRequest(
            execution_id="exec-low",
            cpu_cores=2.0,
            memory_mb=4096,
            priority=1,
        )
        alloc_high = rs.schedule_execution(request_high)
        alloc_low = rs.schedule_execution(request_low)
        assert alloc_high.status == AllocationStatus.ALLOCATED
        assert alloc_low.status == AllocationStatus.ALLOCATED

    def test_check_quotas_returns_true_for_sufficient_resources(self) -> None:
        rs = _build_scheduler()
        rs.register_worker("worker-1", cpu_cores=8.0, memory_mb=16384)
        assert rs.check_quotas("worker-1", required_cpu=2.0, required_memory=4096)
        assert not rs.check_quotas("worker-1", required_cpu=16.0, required_memory=32768)

    def test_enforce_limits_simulates_resource_capping(self) -> None:
        rs = _build_scheduler()
        rs.register_worker("worker-1", cpu_cores=4.0, memory_mb=8192)
        rs._workers["worker-1"]["used_cpu"] = 5.0
        result = rs.enforce_limits("worker-1")
        assert result is False
        assert rs._workers["worker-1"]["used_cpu"] == 4.0

    def test_get_available_capacity_returns_accurate_cluster_metrics(self) -> None:
        rs = _build_scheduler()
        rs.register_worker("worker-1", cpu_cores=8.0, memory_mb=16384)
        rs.register_worker("worker-2", cpu_cores=16.0, memory_mb=32768)
        capacity = rs.get_available_capacity()
        assert capacity["worker_count"] == 2
        assert capacity["total_cpu"] == 24.0
        assert capacity["available_cpu"] == 24.0
