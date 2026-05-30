"""Phase 6 — Control Plane Brain tests.

Tests all 4 subsystems:
  6.1 — SystemStateBrain
  6.2 — Reconciler
  6.3 — ExecutionOrchestrator
  6.4 — HealthManager
  + ControlPlaneBrain integration
"""

import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from core.control_plane import (
    ControlPlaneBrain,
    SystemStateBrain,
    WorkerInfo,
    ExecutionInfo,
    NodeInfo,
    FailureCluster,
    LoadMetrics,
    Reconciler,
    DesiredState,
    Correction,
    ExecutionOrchestrator,
    NodeScore,
    HealthManager,
    HealthReport,
    TopologyEvent,
)


# ═══════════════════════════════════════════════════════════════════
# 6.1 — SystemStateBrain
# ═══════════════════════════════════════════════════════════════════

class TestSystemStateBrain:
    def test_register_worker(self):
        brain = SystemStateBrain()
        w = brain.register_worker("w1", node_id="n1", capacity=10, tags={"role": "compute"})
        assert w.worker_id == "w1"
        assert w.node_id == "n1"
        assert w.capacity == 10
        assert w.tags["role"] == "compute"

    def test_remove_worker(self):
        brain = SystemStateBrain()
        brain.register_worker("w1")
        assert brain.remove_worker("w1") is True
        assert brain.remove_worker("nonexistent") is False

    def test_update_worker_heartbeat(self):
        brain = SystemStateBrain()
        brain.register_worker("w1")
        assert brain.update_worker_heartbeat("w1", cpu_load=0.5, memory_used=256) is True
        assert brain.update_worker_heartbeat("nonexistent") is False
        w = brain.get_worker("w1")
        assert w.cpu_load == 0.5

    def test_healthy_workers(self):
        brain = SystemStateBrain()
        brain.register_worker("w1")
        brain.register_worker("w2")
        assert len(brain.healthy_workers()) == 2

    def test_register_execution(self):
        brain = SystemStateBrain()
        ex = brain.register_execution("e1", dag_id="dag-1", strategy="fast")
        assert ex.execution_id == "e1"
        assert ex.status == "submitted"

    def test_update_execution(self):
        brain = SystemStateBrain()
        brain.register_execution("e1")
        assert brain.update_execution("e1", status="running", worker_id="w1") is True
        assert brain.update_execution("nonexistent") is False
        ex = brain.get_execution("e1")
        assert ex.status == "running"
        assert ex.worker_id == "w1"

    def test_active_executions(self):
        brain = SystemStateBrain()
        brain.register_execution("e1")
        brain.update_execution("e1", status="running")
        brain.register_execution("e2")
        assert len(brain.active_executions()) == 1

    def test_register_node(self):
        brain = SystemStateBrain()
        n = brain.register_node("n1", host="10.0.0.1", port=9001)
        assert n.node_id == "n1"
        assert n.host == "10.0.0.1"

    def test_update_node_health(self):
        brain = SystemStateBrain()
        brain.register_node("n1")
        assert brain.update_node_health("n1", status="degraded", latency_ms=150) is True
        assert brain.update_node_health("nonexistent") is False
        n = brain.get_node("n1")
        assert n.status == "degraded"

    def test_healthy_nodes(self):
        brain = SystemStateBrain()
        brain.register_node("n1")
        brain.register_node("n2")
        assert len(brain.healthy_nodes()) == 2

    def test_workers_by_node(self):
        brain = SystemStateBrain()
        brain.register_worker("w1", node_id="n1")
        brain.register_worker("w2", node_id="n1")
        brain.register_worker("w3", node_id="n2")
        assert len(brain.workers_by_node("n1")) == 2
        assert len(brain.workers_by_node("n2")) == 1

    def test_record_failure(self):
        brain = SystemStateBrain()
        cid = brain.record_failure("n1", "e1", "timeout error")
        assert cid != ""
        clusters = brain.failure_clusters()
        assert len(clusters) == 1

    def test_record_multiple_failures(self):
        brain = SystemStateBrain()
        cid = brain.record_failure("n1", "e1", "timeout")
        brain.record_failure("n1", "e2", "timeout")
        brain.record_failure("n1", "e3", "timeout")
        fc = brain.failure_clusters()[cid]
        assert fc.count == 3

    def test_load_metrics(self):
        brain = SystemStateBrain()
        m = LoadMetrics(cpu_avg=0.5, error_rate=0.01, active_workers=4)
        brain.update_load_metrics("n1", m)
        brain.update_load_metrics("n2", LoadMetrics(cpu_avg=0.3))
        assert brain.get_load_metrics("n1") is not None
        agg = brain.aggregate_load()
        assert agg.cpu_avg == 0.4

    def test_snapshot(self):
        brain = SystemStateBrain()
        brain.register_worker("w1", node_id="n1")
        brain.register_node("n1")
        brain.register_execution("e1")
        snap = brain.snapshot()
        assert "workers" in snap
        assert "nodes" in snap
        assert "executions" in snap
        assert "load_metrics" in snap

    def test_state_change_events(self):
        brain = SystemStateBrain()
        events = []
        brain.on_state_change(lambda e: events.append(e["type"]))
        brain.register_worker("w1")
        assert "worker_registered" in events


# ═══════════════════════════════════════════════════════════════════
# 6.2 — Reconciler
# ═══════════════════════════════════════════════════════════════════

class TestReconciler:
    def test_no_corrections_when_healthy(self):
        brain = SystemStateBrain()
        brain.register_worker("w1", capacity=10)
        brain.register_node("n1")

        recon = Reconciler(DesiredState(min_workers=1))
        corrections = recon.reconcile(brain)
        assert corrections == []

    def test_scale_up_when_below_min(self):
        brain = SystemStateBrain()
        recon = Reconciler(DesiredState(min_workers=3))
        corrections = recon.reconcile(brain)
        assert any(c.action == "scale_up" for c in corrections)

    def test_scale_down_when_above_max(self):
        brain = SystemStateBrain()
        recon = Reconciler(DesiredState(max_workers=1))
        brain.register_worker("w1")
        brain.register_worker("w2")
        corrections = recon.reconcile(brain)
        assert any(c.action == "scale_down" for c in corrections)

    def test_restart_dead_worker(self):
        brain = SystemStateBrain()
        w = brain.register_worker("w1")
        w.last_heartbeat = time.time() - 100  # expired
        recon = Reconciler(DesiredState(heartbeat_timeout_seconds=30))
        corrections = recon.reconcile(brain)
        assert any(c.action == "restart_worker" for c in corrections)

    def test_escalate_retry(self):
        brain = SystemStateBrain()
        brain.register_execution("e1")
        brain.update_execution("e1", retry_count=5)
        recon = Reconciler(DesiredState(max_execution_retries=3))
        corrections = recon.reconcile(brain)
        assert any(c.action == "escalate_retry" for c in corrections)

    def test_blacklist_down_node(self):
        brain = SystemStateBrain()
        brain.register_node("n1")
        brain.update_node_health("n1", status="down")
        recon = Reconciler()
        corrections = recon.reconcile(brain)
        assert any(c.action == "blacklist_node" for c in corrections)

    def test_desired_property(self):
        d = DesiredState(min_workers=5)
        recon = Reconciler(d)
        assert recon.desired.min_workers == 5


# ═══════════════════════════════════════════════════════════════════
# 6.3 — ExecutionOrchestrator
# ═══════════════════════════════════════════════════════════════════

class TestExecutionOrchestrator:
    def test_no_available_nodes_raises(self):
        orch = ExecutionOrchestrator()
        state = SystemStateBrain()
        with pytest.raises(RuntimeError, match="No suitable node available"):
            orch.select_node({"dag_id": "test"}, state)

    def test_selects_healthy_node(self):
        state = SystemStateBrain()
        state.register_node("n1")
        state.register_worker("w1", node_id="n1", capacity=10)
        state.update_load_metrics("n1", LoadMetrics(cpu_avg=0.3, error_rate=0.01))

        orch = ExecutionOrchestrator()
        node = orch.select_node({"dag_id": "test"}, state)
        assert node == "n1"

    def test_selects_least_loaded_node(self):
        state = SystemStateBrain()
        state.register_node("n1")
        state.register_node("n2")
        state.register_worker("w1", node_id="n1", capacity=5)
        state.register_worker("w2", node_id="n2", capacity=5)
        state.update_load_metrics("n1", LoadMetrics(cpu_avg=0.9, error_rate=0.1))
        state.update_load_metrics("n2", LoadMetrics(cpu_avg=0.2, error_rate=0.01))

        orch = ExecutionOrchestrator()
        node = orch.select_node({"dag_id": "test"}, state)
        assert node == "n2"

    def test_preferred_nodes_boosted(self):
        state = SystemStateBrain()
        state.register_node("n1")
        state.register_node("n2")
        state.register_worker("w1", node_id="n1", capacity=5)
        state.register_worker("w2", node_id="n2", capacity=5)
        state.update_load_metrics("n1", LoadMetrics(cpu_avg=0.3))
        state.update_load_metrics("n2", LoadMetrics(cpu_avg=0.3))

        orch = ExecutionOrchestrator()
        node = orch.select_node({"dag_id": "test"}, state, preferred_nodes=["n1"])
        assert node == "n1"

    def test_select_worker_least_loaded(self):
        state = SystemStateBrain()
        state.register_node("n1")
        state.register_worker("w1", node_id="n1", capacity=5)
        state.register_worker("w2", node_id="n1", capacity=5)
        state.update_worker_heartbeat("w2", cpu_load=0.9)

        orch = ExecutionOrchestrator()
        # Both start with active_tasks=0, so w1 is picked first
        wid = orch.select_worker("n1", {}, state)
        assert wid == "w1"

    def test_decisions_history(self):
        state = SystemStateBrain()
        state.register_node("n1")
        state.register_worker("w1", node_id="n1")
        state.update_load_metrics("n1", LoadMetrics(cpu_avg=0.3))

        orch = ExecutionOrchestrator()
        orch.select_node({"dag_id": "t1"}, state)
        assert len(orch.decisions()) == 1


# ═══════════════════════════════════════════════════════════════════
# 6.4 — HealthManager
# ═══════════════════════════════════════════════════════════════════

class TestHealthManager:
    def test_check_unknown_node(self):
        hm = HealthManager()
        report = hm.check_node("unknown")
        assert report.alive is False
        assert "not registered" in report.alerts[0].lower()

    def test_check_healthy_node(self):
        state = SystemStateBrain()
        state.register_node("n1")
        state.register_worker("w1", node_id="n1")

        hm = HealthManager(state=state)
        report = hm.check_node("n1")
        assert report.alive is True
        assert report.status == "healthy"

    def test_check_degraded_node(self):
        state = SystemStateBrain()
        state.register_node("n1")
        n = state.get_node("n1")
        n.last_seen = time.time() - 120

        hm = HealthManager(state=state)
        report = hm.check_node("n1")
        assert report.alive is False
        assert report.status in ("degraded", "unknown")

    def test_hotspot_detection(self):
        state = SystemStateBrain()
        state.register_node("n1")
        state.register_worker("w1", node_id="n1")
        state.update_worker_heartbeat("w1", cpu_load=0.95)

        hm = HealthManager(state=state)
        report = hm.check_node("n1")
        assert any("CPU" in a for a in report.alerts)

    def test_topology_join_event(self):
        hm = HealthManager()
        event = hm.record_topology_event("join", "n1", {"host": "10.0.0.1"})
        assert event.event_type == "join"
        assert hm.state.get_node("n1") is not None

    def test_topology_leave_event(self):
        hm = HealthManager()
        hm.record_topology_event("join", "n1")
        hm.record_topology_event("leave", "n1")
        n = hm.state.get_node("n1")
        assert n.status == "down"

    def test_alerts_fired(self):
        hm = HealthManager()
        alerts = []
        hm.on_alert(lambda a: alerts.append(a))
        hm.record_topology_event("join", "n1")
        # Manually set node to trigger alert
        state = hm.state
        n = state.get_node("n1")
        n.last_seen = time.time() - 120
        hm.check_node("n1")
        assert len(alerts) > 0

    def test_status_summary(self):
        hm = HealthManager()
        hm.record_topology_event("join", "n1")
        summary = hm.status_summary()
        assert summary["total_nodes"] >= 1


# ═══════════════════════════════════════════════════════════════════
# ControlPlaneBrain Integration
# ═══════════════════════════════════════════════════════════════════

class TestControlPlaneBrain:
    def test_create_brain(self):
        brain = ControlPlaneBrain()
        assert brain.state is not None
        assert brain.reconciler is not None
        assert brain.orchestrator is not None
        assert brain.health is not None

    def test_decide_placement_no_nodes(self):
        brain = ControlPlaneBrain()
        result = brain.decide_placement({"dag_id": "test"})
        assert result.node_id == ""
        assert result.score < 0

    def test_decide_placement_with_node(self):
        brain = ControlPlaneBrain()
        brain.state.register_node("n1")
        brain.state.register_worker("w1", node_id="n1")
        brain.state.update_load_metrics("n1", LoadMetrics(cpu_avg=0.3))

        # Register worker with resource scheduler too
        brain.register_worker_resources("w1", "n1")

        result = brain.decide_placement({"dag_id": "test"})
        assert result.node_id == "n1"
        assert result.worker_id == "w1"
        assert result.score >= 0

    def test_record_execution_lifecycle(self):
        brain = ControlPlaneBrain()
        brain.record_execution_start("e1", "dag-1")
        ex = brain.state.get_execution("e1")
        assert ex.status == "submitted"

        brain.record_execution_end("e1", "completed", worker_id="w1", node_id="n1")
        ex = brain.state.get_execution("e1")
        assert ex.status == "completed"
        assert ex.worker_id == "w1"

    def test_record_failure(self):
        brain = ControlPlaneBrain()
        cid = brain.record_failure("n1", "e1", "timeout")
        assert cid != ""

    def test_snapshot(self):
        brain = ControlPlaneBrain()
        snap = brain.snapshot()
        assert "system_state" in snap
        assert "health" in snap
        assert "reconciler" in snap

    def test_correction_handler_called(self):
        brain = ControlPlaneBrain()
        corrections = []
        brain.on_correction(lambda c: corrections.append(c))

        # Run a tick — should find no healthy workers and suggest scale_up
        brain.state.register_worker("w1")
        w = brain.state.get_worker("w1")
        w.last_heartbeat = time.time() - 100
        brain._tick()

        assert len(corrections) > 0
        assert corrections[0].action == "restart_worker"

    def test_start_and_shutdown(self):
        brain = ControlPlaneBrain()
        brain.start(interval=0.1)
        assert brain._running is True
        time.sleep(0.2)
        brain.shutdown()
        assert brain._running is False
