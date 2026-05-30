"""Tests for F2 — Control Plane components (ClusterManager, Autoscaler, WorkerDrainer, HealthSupervisor, Coordinator)."""

from __future__ import annotations

import time
import pytest
from core.control_plane.cluster_manager import ClusterManager
from core.control_plane.autoscaler import Autoscaler, AutoscalerConfig, ScalingDecision, ScalingDirection
from core.control_plane.worker_drainer import WorkerDrainer, DrainState
from core.control_plane.health_supervisor import (
    HealthSupervisor, HealthCheckConfig, RecoveryAction, ProbeResult,
)
from core.control_plane.coordinator import RuntimeCoordinator
from core.control_plane.brain import ControlPlaneBrain


# ── ClusterManager ──────────────────────────────────────────────

class TestClusterManager:
    def test_create_cluster(self):
        cm = ClusterManager()
        cluster = cm.create_cluster("prod", {"region": "us-east"})
        assert cluster.name == "prod"
        assert cluster.labels["region"] == "us-east"
        assert "prod" in cm.list_clusters()

    def test_delete_cluster(self):
        cm = ClusterManager()
        cm.create_cluster("test")
        assert cm.delete_cluster("test")
        assert not cm.delete_cluster("nonexistent")

    def test_add_remove_node(self):
        cm = ClusterManager()
        cm.create_cluster("c1")
        assert cm.add_node_to_cluster("c1", "n1")
        assert cm.add_node_to_cluster("c1", "n2")
        assert len(cm.get_cluster("c1").node_ids) == 2
        assert cm.remove_node_from_cluster("c1", "n1")
        assert "n1" not in cm.get_cluster("c1").node_ids

    def test_clusters_for_node(self):
        cm = ClusterManager()
        cm.create_cluster("c1")
        cm.create_cluster("c2")
        cm.add_node_to_cluster("c1", "n1")
        cm.add_node_to_cluster("c2", "n1")
        assert len(cm.clusters_for_node("n1")) == 2
        assert len(cm.clusters_for_node("n2")) == 0

    def test_update_health(self):
        cm = ClusterManager()
        cm.create_cluster("c1")
        cm.add_node_to_cluster("c1", "n1")
        cm.add_node_to_cluster("c1", "n2")
        cm.update_cluster_health("c1", 1, 2)
        cluster = cm.get_cluster("c1")
        assert cluster.health_status == "degraded"
        assert cluster.healthy_node_count == 1

    def test_recommend_node(self):
        cm = ClusterManager()
        cm.create_cluster("c1")
        cm.add_node_to_cluster("c1", "n1")
        cm.add_node_to_cluster("c1", "n2")
        assert cm.recommend_node("c1") in ("n1", "n2")
        assert cm.recommend_node("c1", ["n2"]) == "n2"
        assert cm.recommend_node("nonexistent") is None

    def test_cluster_summary(self):
        cm = ClusterManager()
        cm.create_cluster("c1")
        s = cm.cluster_summary()
        assert "c1" in s


# ── Autoscaler ──────────────────────────────────────────────────

class TestAutoscaler:
    def test_no_scale_when_balanced(self):
        a = Autoscaler()
        decision = a.evaluate(current_workers=10, worker_utilization=0.5)
        assert decision.direction == ScalingDirection.NONE

    def test_scale_up_on_high_utilization(self):
        a = Autoscaler()
        a.reset_cooldown()
        decision = a.evaluate(current_workers=5, worker_utilization=0.85)
        assert decision.direction == ScalingDirection.UP
        assert decision.count > 0

    def test_scale_down_on_low_utilization(self):
        a = Autoscaler()
        a.reset_cooldown()
        decision = a.evaluate(current_workers=10, worker_utilization=0.1)
        assert decision.direction == ScalingDirection.DOWN

    def test_no_scale_below_min(self):
        a = Autoscaler(config=AutoscalerConfig(min_workers=5))
        a.reset_cooldown()
        decision = a.evaluate(current_workers=5, worker_utilization=0.1)
        assert decision.direction == ScalingDirection.NONE

    def test_no_scale_above_max(self):
        a = Autoscaler(config=AutoscalerConfig(max_workers=10))
        decision = a.evaluate(current_workers=10, worker_utilization=0.9)
        assert decision.direction == ScalingDirection.NONE

    def test_scale_up_with_pending_tasks(self):
        a = Autoscaler()
        a.reset_cooldown()
        decision = a.evaluate(current_workers=2, pending_tasks=20, worker_utilization=0.5)
        assert decision.direction == ScalingDirection.UP

    def test_cooldown(self):
        a = Autoscaler(config=AutoscalerConfig(cooldown_seconds=60))
        a.record_scaling(ScalingDirection.UP)
        decision = a.evaluate(current_workers=5, worker_utilization=0.9)
        assert decision.direction == ScalingDirection.NONE

    def test_reset_cooldown(self):
        a = Autoscaler()
        a.record_scaling(ScalingDirection.UP)
        a.reset_cooldown()
        decision = a.evaluate(current_workers=5, worker_utilization=0.9)
        assert decision.direction == ScalingDirection.UP

    def test_scaling_history(self):
        a = Autoscaler()
        a.reset_cooldown()
        a.evaluate(current_workers=5, worker_utilization=0.9)
        assert len(a.scaling_history()) >= 1


# ── WorkerDrainer ───────────────────────────────────────────────

class TestWorkerDrainer:
    def test_start_drain(self):
        state = ControlPlaneBrain().state
        d = WorkerDrainer(state)
        state.register_worker("w1", "n1")
        op = d.start_drain("w1")
        assert op.state == DrainState.DRAINING
        assert d.is_draining("w1")

    def test_drain_completes_when_tasks_done(self):
        state = ControlPlaneBrain().state
        d = WorkerDrainer(state)
        state.register_worker("w1", "n1", capacity=10)
        op = d.start_drain("w1")
        op.active_tasks = 0
        completed = d.tick()
        assert len(completed) == 1
        assert completed[0].state == DrainState.DRAINED
        assert not d.is_draining("w1")

    def test_drain_timeout(self):
        state = ControlPlaneBrain().state
        d = WorkerDrainer(state)
        state.register_worker("w1", "n1")
        # Give worker active tasks in state so tick() sees them
        w = state.get_worker("w1")
        w.active_tasks = 1
        op = d.start_drain("w1", timeout_seconds=0.01)
        op.active_tasks = 1
        time.sleep(0.02)
        completed = d.tick()
        assert len(completed) == 1
        assert completed[0].state == DrainState.FAILED

    def test_cancel_drain(self):
        state = ControlPlaneBrain().state
        d = WorkerDrainer(state)
        state.register_worker("w1", "n1")
        d.start_drain("w1")
        assert d.cancel_drain("w1")
        assert not d.is_draining("w1")

    def test_drain_summary(self):
        state = ControlPlaneBrain().state
        d = WorkerDrainer(state)
        state.register_worker("w1", "n1")
        d.start_drain("w1")
        s = d.drain_summary()
        assert s["active_drains"] == 1

    def test_drain_status(self):
        state = ControlPlaneBrain().state
        d = WorkerDrainer(state)
        state.register_worker("w1", "n1")
        op = d.start_drain("w1")
        assert d.drain_status("w1") is op
        assert d.drain_status("nonexistent") is None

    def test_complete_drain(self):
        state = ControlPlaneBrain().state
        d = WorkerDrainer(state)
        state.register_worker("w1", "n1")
        d.start_drain("w1")
        assert d.complete_drain("w1")
        assert not d.is_draining("w1")


# ── HealthSupervisor ────────────────────────────────────────────

class TestHealthSupervisor:
    def test_probe_alive_by_default(self):
        hs = HealthSupervisor()
        result = hs.probe("w1")
        assert result.alive

    def test_probe_with_function(self):
        def probe(target: str) -> ProbeResult:
            return ProbeResult(target, alive=(target != "bad"))
        hs = HealthSupervisor(probe_fn=probe)
        assert hs.probe("good").alive
        assert not hs.probe("bad").alive

    def test_failure_counting(self):
        hs = HealthSupervisor()
        assert hs.record_failure("w1") == 1
        assert hs.record_failure("w1") == 2
        hs.record_success("w1")
        assert hs._failure_counts["w1"] == 0

    def test_assess_ignore_when_healthy(self):
        hs = HealthSupervisor()
        action = hs.assess("w1")
        assert action == RecoveryAction.IGNORE

    def test_assess_notify_on_few_failures(self):
        hs = HealthSupervisor()
        hs.set_config("w1", HealthCheckConfig(max_failures=3))
        hs.record_failure("w1")
        action = hs.assess("w1")
        assert action == RecoveryAction.NOTIFY

    def test_assess_restart_on_max_failures(self):
        hs = HealthSupervisor()
        hs.set_config("w1", HealthCheckConfig(max_failures=2, recovery_action=RecoveryAction.RESTART))
        hs.record_failure("w1")
        hs.record_failure("w1")
        action = hs.assess("w1")
        assert action == RecoveryAction.RESTART

    def test_quarantine(self):
        hs = HealthSupervisor()
        hs.quarantine("w1")
        assert hs.is_quarantined("w1")
        action = hs.assess("w1")
        assert action == RecoveryAction.QUARANTINE
        hs.unquarantine("w1")
        assert not hs.is_quarantined("w1")

    def test_recovery_history(self):
        hs = HealthSupervisor()
        hs.set_config("w1", HealthCheckConfig(max_failures=1, recovery_action=RecoveryAction.RESTART))
        hs.record_failure("w1")
        hs.assess("w1")
        assert len(hs.recovery_history()) >= 1

    def test_tick(self):
        calls = []
        def probe(target: str) -> ProbeResult:
            calls.append(target)
            return ProbeResult(target, alive=False)
        hs = HealthSupervisor(probe_fn=probe)
        hs.set_config("w1", HealthCheckConfig(interval_seconds=0, max_failures=1))
        actions = hs.tick()
        assert "w1" in calls
        assert len(actions) >= 1

    def test_clear_failures(self):
        hs = HealthSupervisor()
        hs.record_failure("w1")
        hs.clear_failures("w1")
        assert hs._failure_counts["w1"] == 0


# ── RuntimeCoordinator ──────────────────────────────────────────

class TestRuntimeCoordinator:
    def test_create(self):
        brain = ControlPlaneBrain()
        coord = RuntimeCoordinator(brain)
        assert coord.brain is brain
        assert coord.autoscaler is not None
        assert coord.drainer is not None
        assert coord.supervisor is not None

    def test_evaluate_scaling(self):
        brain = ControlPlaneBrain()
        coord = RuntimeCoordinator(brain)
        decision = coord.evaluate_scaling(current_workers=5, worker_utilization=0.1)
        assert decision is not None

    def test_scale_to(self):
        brain = ControlPlaneBrain()
        coord = RuntimeCoordinator(brain)
        result = coord.scale_to(3)
        assert result == 3

    def test_supervise_health(self):
        brain = ControlPlaneBrain()
        coord = RuntimeCoordinator(brain)
        actions = coord.supervise_health()
        assert actions == []

    def test_status_summary(self):
        brain = ControlPlaneBrain()
        coord = RuntimeCoordinator(brain)
        s = coord.status_summary()
        assert "autoscaler" in s
        assert "drainer" in s
        assert "supervisor" in s
