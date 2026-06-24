"""Tests for F3 — ResourceScheduler subsystem."""

from __future__ import annotations

import time
import pytest
from core.runtime.resource_scheduler import (
    ResourceScheduler,
    ResourceRequirements,
    SchedulingResult,
    Priority,
    PriorityScheduler,
    FairnessModel,
    WorkerResource,
    UserQuota,
)


class TestWorkerResource:
    def test_can_fit_basic(self):
        w = WorkerResource(worker_id="w1", node_id="n1", total_cpu=8, total_memory=16384)
        req = ResourceRequirements(cpu_cores=2, memory_mb=4096)
        assert w.can_fit(req)

    def test_cannot_fit_over_cpu(self):
        w = WorkerResource(worker_id="w1", node_id="n1", total_cpu=4, used_cpu=3.8)
        req = ResourceRequirements(cpu_cores=1)
        assert not w.can_fit(req)

    def test_cannot_fit_over_memory(self):
        w = WorkerResource(worker_id="w1", node_id="n1", total_memory=4096, used_memory=4000)
        req = ResourceRequirements(memory_mb=512)
        assert not w.can_fit(req)

    def test_gpu_worker(self):
        w = WorkerResource(worker_id="w1", node_id="n1", total_gpu=4, total_gpu_memory=16384)
        req = ResourceRequirements(gpu_cores=2, gpu_memory_mb=8192)
        assert w.can_fit(req)
        assert req.requires_gpu()

    def test_cannot_fit_over_gpu(self):
        w = WorkerResource(worker_id="w1", node_id="n1", total_gpu=2, used_gpu=2)
        req = ResourceRequirements(gpu_cores=1)
        assert not w.can_fit(req)

    def test_cannot_fit_over_capacity(self):
        w = WorkerResource(worker_id="w1", node_id="n1", active_tasks=10, capacity=10)
        req = ResourceRequirements()
        assert not w.can_fit(req)

    def test_allocate_release(self):
        w = WorkerResource(worker_id="w1", node_id="n1", total_cpu=8, total_memory=16384)
        req = ResourceRequirements(cpu_cores=2, memory_mb=4096)
        w.allocate(req)
        assert w.active_tasks == 1
        assert w.used_cpu == 2.0
        assert w.used_memory == 4096.0

        w.release(req)
        assert w.active_tasks == 0
        assert w.used_cpu == 0.0
        assert w.used_memory == 0.0

    def test_utilization(self):
        w = WorkerResource(worker_id="w1", node_id="n1", total_cpu=8, used_cpu=4)
        assert w.cpu_utilization == 0.5
        assert w.cpu_available == 4.0


class TestUserQuota:
    def test_has_quota(self):
        q = UserQuota(user_id="u1", max_cpu=16, max_memory=16384)
        req = ResourceRequirements(cpu_cores=4, memory_mb=4096)
        assert q.has_quota(req)

    def test_exceeds_cpu_quota(self):
        q = UserQuota(user_id="u1", max_cpu=8, used_cpu=7)
        req = ResourceRequirements(cpu_cores=2)
        assert not q.has_quota(req)

    def test_exceeds_execution_quota(self):
        q = UserQuota(user_id="u1", max_executions=3, active_executions=3)
        req = ResourceRequirements()
        assert not q.has_quota(req)

    def test_consume_release(self):
        q = UserQuota(user_id="u1", max_cpu=16)
        req = ResourceRequirements(cpu_cores=4, memory_mb=4096)
        q.consume(req)
        assert q.used_cpu == 4.0
        assert q.active_executions == 1

        q.release(req)
        assert q.used_cpu == 0.0
        assert q.active_executions == 0


class TestFairnessModel:
    def test_fairness_score_default(self):
        f = FairnessModel()
        assert f.fairness_score("u1") == 1.0

    def test_fairness_score_below_fair(self):
        f = FairnessModel()
        f.set_weight("u1", 2.0)
        f.set_weight("u2", 1.0)
        f.record_usage("u1", 10.0)
        f.record_usage("u2", 20.0)
        # u1 has 2/3 weight but only 10/30 usage = 0.33 → below fair share → 1.0
        assert f.fairness_score("u1") == 1.0

    def test_fairness_score_above_fair(self):
        f = FairnessModel()
        f.set_weight("u1", 1.0)
        f.set_weight("u2", 1.0)
        f.record_usage("u1", 80.0)
        f.record_usage("u2", 20.0)
        # u1 has 0.5 weight but 0.8 usage → above fair share
        score = f.fairness_score("u1")
        assert score < 1.0
        assert score > 0.1

    def test_release_usage(self):
        f = FairnessModel()
        f.set_weight("u1", 1.0)
        f.record_usage("u1", 50.0)
        f.record_release("u1", 20.0)
        assert f._usage["u1"] == 30.0


class TestPriorityScheduler:
    def test_submit_and_select(self):
        ps = PriorityScheduler()
        ps.submit({"id": "task1"}, Priority.CRITICAL)
        ps.submit({"id": "task2"}, Priority.LOW)

        selected = ps.select()
        assert selected is not None
        assert selected["id"] == "task1"

    def test_priority_order(self):
        ps = PriorityScheduler()
        ps.submit({"id": "low"}, Priority.LOW)
        ps.submit({"id": "normal"}, Priority.NORMAL)
        ps.submit({"id": "high"}, Priority.HIGH)

        assert ps.select()["id"] == "high"
        assert ps.select()["id"] == "normal"
        assert ps.select()["id"] == "low"

    def test_empty_select(self):
        ps = PriorityScheduler()
        assert ps.select() is None

    def test_priority_score(self):
        ps = PriorityScheduler()
        task = {"id": "t1", "_priority": Priority.CRITICAL}
        score = ps.priority_score(task)
        assert score == 100

        task2 = {"id": "t2", "_priority": Priority.BACKGROUND}
        assert ps.priority_score(task2) == 10

    def test_aging(self):
        ps = PriorityScheduler()
        # Manually add a task with an old submission time
        old_task = {"id": "aged", "_submitted_at": time.time() - 30, "_priority": Priority.LOW}
        ps._queues[Priority.LOW].push(old_task)
        # Force aging
        ps._last_aging = 0
        ps._age_tasks()
        assert ps._queues[Priority.LOW].items[0].get("_aging_boost", 0) >= 3


class TestResourceScheduler:
    def test_register_worker(self):
        rs = ResourceScheduler()
        rs.register_worker("w1", "n1")
        assert "w1" in rs._workers

    def test_register_gpu_worker(self):
        rs = ResourceScheduler()
        rs.register_worker("w1", "n1", total_gpu=4, total_gpu_memory=16384)
        assert "n1" in rs._gpu_nodes

    def test_unregister_worker(self):
        rs = ResourceScheduler()
        rs.register_worker("w1", "n1")
        rs.unregister_worker("w1")
        assert "w1" not in rs._workers

    def test_select_worker_simple(self):
        rs = ResourceScheduler()
        rs.register_worker("w1", "n1", total_cpu=8, total_memory=16384)
        rs.register_worker("w2", "n2", total_cpu=8, total_memory=16384)

        result = rs.select_worker({"dag_id": "test"}, "user1")
        assert result.worker_id in ("w1", "w2")
        assert result.node_id in ("n1", "n2")
        assert result.score >= 0

    def test_select_worker_prefers_lower_load(self):
        rs = ResourceScheduler()
        rs.register_worker("w1", "n1", total_cpu=8)
        rs.register_worker("w2", "n2", total_cpu=8)
        rs.update_worker_load("w1", used_cpu=7.5)
        rs.update_worker_load("w2", used_cpu=0.5)

        result = rs.select_worker({"dag_id": "test"}, "user1")
        assert result.worker_id == "w2"
        assert result.score >= 0

    def test_select_worker_no_suitable(self):
        rs = ResourceScheduler()
        rs.register_worker("w1", "n1", total_cpu=2)
        rs.update_worker_load("w1", used_cpu=2)
        result = rs.select_worker({"dag_id": "test"}, "user1")
        assert result.score < 0
        assert "No suitable worker" in result.reason

    def test_select_worker_respects_quota(self):
        rs = ResourceScheduler()
        rs.register_worker("w1", "n1", total_cpu=8)
        rs.set_quota("user1", max_cpu=1)
        rs.allocate("w1", ResourceRequirements(cpu_cores=1), "user1")

        req = ResourceRequirements(cpu_cores=1)
        result = rs.select_worker({"dag_id": "test"}, "user1", requirements=req)
        assert result.score < 0
        assert "quota" in result.reason.lower()

    def test_gpu_routing(self):
        rs = ResourceScheduler()
        rs.register_worker("w_cpu", "n1", total_cpu=8, total_gpu=0)
        rs.register_worker("w_gpu", "n2", total_cpu=8, total_gpu=4, total_gpu_memory=16384)

        # GPU task should go to GPU worker
        req = ResourceRequirements(gpu_cores=2)
        result = rs.select_worker({"dag_id": "test"}, "user1", requirements=req)
        assert result.worker_id == "w_gpu"

    def test_cpu_task_not_on_gpu_worker(self):
        rs = ResourceScheduler()
        rs.register_worker("w_cpu", "n1", total_cpu=8, total_gpu=0)
        rs.register_worker("w_gpu", "n2", total_cpu=8, total_gpu=4)

        # CPU task should go to non-GPU worker
        req = ResourceRequirements(gpu_cores=0)
        result = rs.select_worker({"dag_id": "test"}, "user1", requirements=req)
        assert result.worker_id == "w_cpu"

    def test_allocate_release(self):
        rs = ResourceScheduler()
        rs.register_worker("w1", "n1", total_cpu=8)
        rs.set_quota("user1", max_cpu=16)

        req = ResourceRequirements(cpu_cores=2, memory_mb=4096)
        assert rs.allocate("w1", req, "user1")
        assert rs._workers["w1"].used_cpu == 2.0

        rs.release("w1", req, "user1")
        assert rs._workers["w1"].used_cpu == 0.0

    def test_quota_enforcement_on_allocate(self):
        rs = ResourceScheduler()
        rs.register_worker("w1", "n1", total_cpu=8)
        rs.set_quota("user1", max_cpu=4)
        rs.allocate("w1", ResourceRequirements(cpu_cores=4), "user1")

        # Over quota — should fail
        assert not rs.allocate("w1", ResourceRequirements(cpu_cores=1), "user1")

    def test_cluster_summary(self):
        rs = ResourceScheduler()
        rs.register_worker("w1", "n1", total_cpu=8, total_memory=16384)
        rs.register_worker("w2", "n2", total_cpu=16, total_memory=32768, total_gpu=4)
        summary = rs.cluster_summary()
        assert summary["workers"] == 2
        assert summary["gpu_nodes"] == 1

    def test_worker_summary(self):
        rs = ResourceScheduler()
        rs.register_worker("w1", "n1", total_cpu=8, total_memory=16384)
        s = rs.worker_summary("w1")
        assert s is not None
        assert s["node_id"] == "n1"
        assert "8.0" in s["cpu"]

        assert rs.worker_summary("nonexistent") is None

    def test_submit_task_priority(self):
        rs = ResourceScheduler()
        rs.submit_task({"id": "t1"}, Priority.CRITICAL)
        rs.submit_task({"id": "t2"}, Priority.LOW)
        selected = rs.select_next_task()
        assert selected is not None
        assert selected["id"] == "t1"

    def test_update_worker_load(self):
        rs = ResourceScheduler()
        rs.register_worker("w1", "n1", total_cpu=8)
        rs.update_worker_load("w1", used_cpu=4.0)
        assert rs._workers["w1"].used_cpu == 4.0

    def test_set_user_weight(self):
        rs = ResourceScheduler()
        rs.set_user_weight("u1", 2.0)
        assert rs._fairness_model._weights["u1"] == 2.0

    def test_empty_cluster_summary(self):
        rs = ResourceScheduler()
        summary = rs.cluster_summary()
        assert summary["workers"] == 0
        assert summary["gpu_nodes"] == 0
