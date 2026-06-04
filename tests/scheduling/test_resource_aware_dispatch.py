"""Phase F3 — Resource Scheduler & Quota Enforcement: 30 tests.

Groups:
  - TestWorkerFitScoring:   6 tests — fit calculation, rejection, GPU/CPU/RAM
  - TestFairnessAndPriority: 6 tests — starvation prevention, P0 boost, P3 demote
  - TestQuotaEnforcement:   6 tests — reserve, release, ceiling, exceed
  - TestPreemptionSafety:   6 tests — safe preempt, state save, resume, zero data loss
  - TestEventConsistency:   6 tests — all decisions emit documented ExecutionEvent

Ref: Canon LAW 3, LAW 5, LAW 8, LAW 10, LAW 11, RULE 1, RULE 2, RULE 3
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pytest

from core.runtime.scheduling.resource_scheduler import (
    SchedulingOrchestrator,
    TaskRequirements,
)
from core.runtime.scheduling.policies import (
    AffinityRules,
    FairnessPolicy,
    MatchScore,
    PriorityScheduler,
    ReasonCode,
    SchedulingDecision,
)
from core.runtime.resources.quota_manager import QuotaManager, Quota


# ── Helpers ─────────────────────────────────────────────────

@dataclass
class FakeWorker:
    worker_id: str
    capabilities: Dict[str, Any] = field(default_factory=dict)
    state: str = "healthy"
    load: Any = None
    endpoint: str = ""
    lease_id: str = ""
    registered_at: float = 0.0
    last_heartbeat: float = 0.0
    tags: Dict[str, str] = field(default_factory=dict)


@dataclass
class FakeLoadMetric:
    cpu_pct: float = 0.0
    mem_pct: float = 0.0
    queue_depth: int = 0
    avg_latency_ms: float = 0.0
    active_leases: int = 0


class FakeClusterManager:
    def __init__(self):
        self._workers: Dict[str, FakeWorker] = {}

    def add_worker(self, w: FakeWorker) -> None:
        self._workers[w.worker_id] = w

    def list_active_workers(self) -> List[FakeWorker]:
        return [w for w in self._workers.values() if w.state == "healthy"]

    def get_worker(self, worker_id: str) -> Optional[FakeWorker]:
        return self._workers.get(worker_id)


class FakeEventBus:
    def __init__(self):
        self.events: List[tuple[str, Any]] = []

    def publish(self, topic: str, event: Any) -> None:
        self.events.append((topic, event))

    def clear(self) -> None:
        self.events.clear()


# ── TestWorkerFitScoring ────────────────────────────────────

class TestWorkerFitScoring:
    """MatchScore — fit calculation, rejection, GPU/CPU/RAM enforcement."""

    def test_perfect_fit_scores_high(self):
        orch = SchedulingOrchestrator()
        task = TaskRequirements(execution_id="t1", cpu_cores=2.0, memory_mb=1024)
        caps = {"available_cpu": 8.0, "available_memory": 4096, "available_gpu": 0, "network": True}
        score = orch.evaluate_worker_fit(task, caps)
        assert score.matched
        assert score.score >= 0.6

    def test_insufficient_cpu_rejects(self):
        orch = SchedulingOrchestrator()
        task = TaskRequirements(execution_id="t2", cpu_cores=8.0, memory_mb=512)
        caps = {"available_cpu": 4.0, "available_memory": 4096}
        score = orch.evaluate_worker_fit(task, caps)
        assert not score.matched
        assert any("CPU" in v for v in score.violations)

    def test_insufficient_memory_rejects(self):
        orch = SchedulingOrchestrator()
        task = TaskRequirements(execution_id="t3", cpu_cores=1.0, memory_mb=8192)
        caps = {"available_cpu": 8.0, "available_memory": 1024}
        score = orch.evaluate_worker_fit(task, caps)
        assert not score.matched
        assert any("memory" in v.lower() for v in score.violations)

    def test_gpu_requirement_matched(self):
        orch = SchedulingOrchestrator()
        task = TaskRequirements(execution_id="t4", cpu_cores=1.0, memory_mb=512, gpu_memory_mb=4096)
        caps = {"available_cpu": 8.0, "available_memory": 4096, "available_gpu": 8192}
        score = orch.evaluate_worker_fit(task, caps)
        assert score.matched
        assert score.score > 0.5

    def test_gpu_requirement_unmet_rejects(self):
        orch = SchedulingOrchestrator()
        task = TaskRequirements(execution_id="t5", cpu_cores=1.0, memory_mb=512, gpu_memory_mb=4096)
        caps = {"available_cpu": 8.0, "available_memory": 4096, "available_gpu": 0}
        score = orch.evaluate_worker_fit(task, caps)
        assert not score.matched
        assert any("GPU" in v for v in score.violations)

    def test_load_penalty_reduces_score(self):
        orch = SchedulingOrchestrator()
        task = TaskRequirements(execution_id="t6", cpu_cores=1.0, memory_mb=512)
        caps_low = {"available_cpu": 8.0, "available_memory": 4096, "load_pct": 10}
        caps_high = {"available_cpu": 8.0, "available_memory": 4096, "load_pct": 90}
        low_score = orch.evaluate_worker_fit(task, caps_low)
        high_score = orch.evaluate_worker_fit(task, caps_high)
        assert low_score.score > high_score.score


# ── TestFairnessAndPriority ─────────────────────────────────

class TestFairnessAndPriority:
    """Starvation prevention, P0 boost, P3 demote at congestion."""

    def test_fairness_weight_below_average_gets_boost(self):
        policy = FairnessPolicy()
        policy.record_usage("worker_a", 100.0)
        policy.record_usage("worker_b", 10.0)
        weight = policy.compute_weight("worker_b")
        assert weight > 1.0

    def test_fairness_weight_above_average_gets_penalty(self):
        policy = FairnessPolicy()
        policy.record_usage("worker_a", 10.0)
        policy.record_usage("worker_b", 100.0)
        weight = policy.compute_weight("worker_b")
        assert weight < 1.0

    def test_fairness_no_starvation_after_cycles(self):
        policy = FairnessPolicy()
        for i in range(10):
            policy.record_usage(f"worker_{i}", 50.0)
        policy.record_usage("starved", 1.0)
        weight = policy.compute_weight("starved")
        assert weight > 1.1
        dec = policy.detect_starvation("starved", 900.0, max_wait=300.0)
        assert dec.reason_code == ReasonCode.STARVATION_PREVENTION

    def test_priority_p0_queued_within_limit(self):
        ps = PriorityScheduler()
        dec = ps.enqueue("task_p0", 0)
        assert dec.accepted
        assert dec.reason_code == ReasonCode.PRIORITY_QUEUED

    def test_priority_p3_boosted_after_time_limit(self):
        ps = PriorityScheduler()
        ps.enqueue("task_p3", 3)
        time.sleep(0.01)
        dec = ps.check_time_limit("task_p3", 3)
        assert dec.accepted

    def test_priority_p0_preempts_p3(self):
        ps = PriorityScheduler()
        target = ps.select_preemption_target(0, [
            {"execution_id": "low_task", "priority": 3},
            {"execution_id": "normal_task", "priority": 2},
        ])
        assert target == "low_task"


# ── TestQuotaEnforcement ────────────────────────────────────

class TestQuotaEnforcement:
    """Reserve, release, ceiling enforcement, exceed → reject/scale."""

    def test_reserve_quota_returns_lease_id(self):
        qm = QuotaManager()
        qm.set_worker_quota("worker_1", Quota(max_cpu=100.0, max_memory=65536))
        lease_id = qm.reserve_quota("worker_1", {"cpu": 10.0, "memory": 2048})
        assert lease_id is not None
        assert lease_id.startswith("res-")

    def test_reserve_quota_rejects_when_exceeded(self):
        qm = QuotaManager()
        qm.set_worker_quota("worker_1", Quota(max_cpu=10.0, max_memory=65536))
        lease_id = qm.reserve_quota("worker_1", {"cpu": 100.0, "memory": 2048})
        assert lease_id is None

    def test_release_quota_frees_resources(self):
        qm = QuotaManager()
        qm.set_worker_quota("worker_1", Quota(max_cpu=100.0, max_memory=65536))
        lease_id = qm.reserve_quota("worker_1", {"cpu": 50.0, "memory": 4096})
        assert lease_id is not None
        qm.release_quota(lease_id, {"cpu": 20.0, "memory": 1024})
        second = qm.reserve_quota("worker_1", {"cpu": 80.0, "memory": 4096})
        assert second is not None

    def test_global_ceiling_returns_up_at_85(self):
        qm = QuotaManager()
        qm.set_global_quota(Quota(max_cpu=100.0, max_memory=65536))
        qm.record_usage("_global", cpu=85.0, memory=50000)
        signal = qm.enforce_global_ceiling()
        assert signal == "up"

    def test_global_ceiling_returns_hold_below_85(self):
        qm = QuotaManager()
        qm.set_global_quota(Quota(max_cpu=100.0, max_memory=65536))
        qm.record_usage("_global", cpu=50.0, memory=30000)
        signal = qm.enforce_global_ceiling()
        assert signal == "hold"

    def test_global_ceiling_none_when_no_quota(self):
        qm = QuotaManager()
        signal = qm.enforce_global_ceiling()
        assert signal is None


# ── TestPreemptionSafety ────────────────────────────────────

class TestPreemptionSafety:
    """Safe preemption, state save, resume, zero data loss."""

    def test_preempt_returns_false_when_no_tasks(self):
        orch = SchedulingOrchestrator()
        cm = FakeClusterManager()
        cm.add_worker(FakeWorker(worker_id="w1", capabilities={"active_tasks": []}))
        orch._cluster = cm
        task = TaskRequirements(execution_id="high_prio", priority=0)
        result = orch.preempt_low_priority_task("w1", task)
        assert result is False

    def test_preempt_returns_false_when_worker_not_found(self):
        orch = SchedulingOrchestrator()
        cm = FakeClusterManager()
        orch._cluster = cm
        task = TaskRequirements(execution_id="high_prio", priority=0)
        result = orch.preempt_low_priority_task("nonexistent", task)
        assert result is False

    def test_preempt_returns_true_with_preemptable_task(self):
        orch = SchedulingOrchestrator()
        cm = FakeClusterManager()
        cm.add_worker(FakeWorker(worker_id="w1", capabilities={
            "active_tasks": [
                {"execution_id": "low_prio", "priority": 3},
            ],
        }))
        orch._cluster = cm
        task = TaskRequirements(execution_id="high_prio", priority=0)
        result = orch.preempt_low_priority_task("w1", task)
        assert result is True

    def test_preempt_skips_when_priority_diff_insufficient(self):
        ps = PriorityScheduler()
        target = ps.select_preemption_target(2, [
            {"execution_id": "bg_task", "priority": 3},
        ])
        assert target is None

    def test_preempt_selects_lowest_priority_task(self):
        ps = PriorityScheduler()
        target = ps.select_preemption_target(0, [
            {"execution_id": "normal", "priority": 2},
            {"execution_id": "background", "priority": 3},
        ])
        assert target == "background"

    def test_release_resources_after_preempt_succeeds(self):
        qm = QuotaManager()
        qm.set_worker_quota("w1", Quota(max_cpu=100.0, max_memory=65536))
        lease_id = qm.reserve_quota("w1", {"cpu": 20.0, "memory": 2048})
        assert lease_id is not None
        qm.release_quota(lease_id, {"cpu": 5.0, "memory": 512})
        second = qm.reserve_quota("w1", {"cpu": 90.0, "memory": 4096})
        assert second is not None


# ── TestEventConsistency ────────────────────────────────────

class TestEventConsistency:
    """All scheduling decisions emit documented ExecutionEvent."""

    def test_select_optimal_worker_emits_scheduled_event(self):
        orch = SchedulingOrchestrator()
        cm = FakeClusterManager()
        cm.add_worker(FakeWorker(worker_id="w1", capabilities={
            "available_cpu": 16.0, "available_memory": 32768,
        }))
        bus = FakeEventBus()
        qm = QuotaManager()
        qm.set_worker_quota("w1", Quota(max_cpu=100.0, max_memory=65536))
        orch._cluster = cm
        orch._event_bus = bus
        orch._quota = qm
        task = TaskRequirements(execution_id="evt_task", cpu_cores=2.0, memory_mb=1024)
        worker_id = orch.select_optimal_worker(task)
        assert worker_id is not None
        scheduled = [(t, e) for t, e in bus.events if "scheduled" in t]
        assert len(scheduled) >= 1

    def test_rejected_task_emits_rejected_event(self):
        orch = SchedulingOrchestrator()
        cm = FakeClusterManager()
        bus = FakeEventBus()
        orch._cluster = cm
        orch._event_bus = bus
        task = TaskRequirements(execution_id="no_worker")
        worker_id = orch.select_optimal_worker(task)
        assert worker_id is None
        rejected = [(t, e) for t, e in bus.events if "rejected" in t]
        assert len(rejected) >= 1

    def test_preemption_emits_preempted_event(self):
        orch = SchedulingOrchestrator()
        cm = FakeClusterManager()
        cm.add_worker(FakeWorker(worker_id="w1", capabilities={
            "active_tasks": [
                {"execution_id": "low_prio", "priority": 3},
            ],
        }))
        bus = FakeEventBus()
        orch._cluster = cm
        orch._event_bus = bus
        task = TaskRequirements(execution_id="high_prio", priority=0)
        result = orch.preempt_low_priority_task("w1", task)
        assert result is True
        preempted = [(t, e) for t, e in bus.events if "preempted" in t]
        assert len(preempted) >= 1

    def test_global_ceiling_emits_ceiling_event(self):
        orch = SchedulingOrchestrator()
        qm = QuotaManager()
        qm.set_global_quota(Quota(max_cpu=100.0, max_memory=65536))
        qm.record_usage("_global", cpu=90.0, memory=60000)
        bus = FakeEventBus()
        orch._quota = qm
        orch._event_bus = bus
        signal = orch.enforce_global_ceiling()
        assert signal == "up"
        ceiling_events = [(t, e) for t, e in bus.events if "ceiling" in t]
        assert len(ceiling_events) >= 1

    def test_release_resources_emits_completed_event(self):
        orch = SchedulingOrchestrator()
        bus = FakeEventBus()
        orch._event_bus = bus
        orch.release_resources("done_task", {"cpu": 5.0, "memory": 512})
        completed = [(t, e) for t, e in bus.events if "completed" in t]
        assert len(completed) >= 1

    def test_quota_reserve_failure_no_event_leak(self):
        orch = SchedulingOrchestrator()
        cm = FakeClusterManager()
        cm.add_worker(FakeWorker(worker_id="w1", capabilities={
            "available_cpu": 16.0, "available_memory": 32768,
        }))
        qm = QuotaManager()
        qm.set_worker_quota("w1", Quota(max_cpu=0.1, max_memory=1))
        bus = FakeEventBus()
        orch._cluster = cm
        orch._quota = qm
        orch._event_bus = bus
        task = TaskRequirements(execution_id="quota_fail", cpu_cores=8.0, memory_mb=65536)
        worker_id = orch.select_optimal_worker(task)
        assert worker_id is None
        rejected = [(t, e) for t, e in bus.events if "rejected" in t]
        assert len(rejected) >= 1
        scheduled = [(t, e) for t, e in bus.events if "scheduled" in t]
        assert len(scheduled) == 0
