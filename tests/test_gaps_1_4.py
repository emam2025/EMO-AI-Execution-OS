"""Tests for GAP 1-4: Service Mesh, Control Plane, Runtime OS, Evolution.

Covers all 4 critical transformation layers.
"""

import time
from unittest.mock import MagicMock, patch

import pytest

from core.runtime.mesh import (
    ServiceRegistry,
    ServiceMesh,
    ServiceNotAvailable,
    MeshProtocol,
    MeshEnvelope,
    MeshMessageType,
    FailurePropagator,
)
from core.runtime.control import (
    ControlPlane,
    ControlAction,
    SystemState,
    SystemPhase,
    Reconciler,
    DesiredState,
    WorkerOrchestrator,
    WorkerState,
    HealthMonitor,
)
from core.runtime.os import RuntimeOS, ExecutionRecord
from core.runtime.evolution import (
    CanonEvolver,
    EvolutionReport,
    EvolutionPolicy,
    RuleRefiner,
    RefinementSuggestion,
    FeedbackActuator,
    FeedbackReport,
)


# ═══════════════════════════════════════════════════════════════════
# GAP 1 — Service Mesh
# ═══════════════════════════════════════════════════════════════════

class TestMeshProtocol:
    def test_create_request(self):
        env = MeshProtocol.create_request("scheduler", "order", {"dag": "x"}, trace_id="t1")
        assert env.msg_type == MeshMessageType.REQUEST
        assert env.service == "scheduler"
        assert env.method == "order"

    def test_create_response(self):
        req = MeshProtocol.create_request("test", "ping", {})
        resp = MeshProtocol.create_response(req, {"ok": True})
        assert resp.msg_type == MeshMessageType.RESPONSE
        assert resp.payload["ok"] is True

    def test_is_request(self):
        env = MeshProtocol.create_request("s", "m", {})
        assert MeshProtocol.is_request(env)
        assert not MeshProtocol.is_response(env)

    def test_create_error(self):
        req = MeshProtocol.create_request("test", "ping", {})
        err = MeshProtocol.create_error(req, "fail")
        assert err.msg_type == MeshMessageType.ERROR
        assert "fail" in err.payload["error"]


class TestServiceRegistry:
    def test_register(self):
        reg = ServiceRegistry()
        iid = reg.register("scheduler")
        assert iid.startswith("scheduler-")

    def test_deregister(self):
        reg = ServiceRegistry()
        iid = reg.register("scheduler")
        assert reg.deregister("scheduler", iid) is True
        assert reg.deregister("nonexistent", "x") is False

    def test_heartbeat(self):
        reg = ServiceRegistry()
        iid = reg.register("scheduler")
        assert reg.heartbeat("scheduler", iid) is True
        assert reg.heartbeat("nonexistent", "x") is False

    def test_discover_healthy(self):
        reg = ServiceRegistry()
        reg.register("scheduler")
        instances = reg.discover("scheduler")
        assert len(instances) == 1

    def test_discover_nonexistent(self):
        reg = ServiceRegistry()
        assert reg.discover("nonexistent") == []

    def test_discover_by_capability(self):
        reg = ServiceRegistry()
        reg.register("reader", capabilities=["read"])
        reg.register("writer", capabilities=["write"])
        readers = reg.discover_by_capability("read")
        assert len(readers) == 1
        assert readers[0].service_name == "reader"

    def test_prune_expired(self):
        reg = ServiceRegistry()
        iid = reg.register("test", ttl=0.001)
        time.sleep(0.01)
        removed = reg.prune_expired()
        assert removed == 1
        assert reg.discover("test") == []

    def test_all_services(self):
        reg = ServiceRegistry()
        reg.register("a")
        reg.register("b")
        services = reg.all_services()
        assert "a" in services
        assert "b" in services

    def test_get_instance(self):
        reg = ServiceRegistry()
        iid = reg.register("test")
        inst = reg.get_instance("test", iid)
        assert inst is not None
        assert inst.service_name == "test"


class TestServiceMesh:
    def test_call_local_handler(self):
        mesh = ServiceMesh()
        called = []

        def handler(payload):
            called.append(payload)
            return {"result": "ok"}

        mesh.register_local_handler("test", "ping", handler)
        result = mesh.call("test", "ping", {"data": 1})
        assert result == {"result": "ok"}
        assert called == [{"data": 1}]

    def test_call_no_handler_raises(self):
        mesh = ServiceMesh()
        with pytest.raises(ServiceNotAvailable):
            mesh.call("nonexistent", "method", {})

    def test_call_async(self):
        mesh = ServiceMesh()
        trace = mesh.call_async("test", "ping", {})
        assert len(trace) == 12

    def test_registry_property(self):
        mesh = ServiceMesh()
        assert mesh.registry is not None


class TestFailurePropagator:
    def test_propagate_records_failure(self):
        reg = ServiceRegistry()
        iid = reg.register("test")
        prop = FailurePropagator(registry=reg)
        notified = prop.propagate("test", iid, "error msg")
        assert prop.failure_count("test") == 1
        assert isinstance(notified, list)

    def test_recent_failures(self):
        prop = FailurePropagator()
        assert prop.recent_failures() == []
        prop.propagate("t1", "i1", "err")
        assert len(prop.recent_failures()) == 1

    def test_callback_on_failure(self):
        prop = FailurePropagator()
        called = []
        prop.on_failure("dependent", lambda f: called.append(f["service"]))
        prop.propagate("source", "i1", "err")
        assert len(called) == 1
        assert called[0] == "source"

    def test_mark_instance_down(self):
        reg = ServiceRegistry()
        iid = reg.register("test")
        prop = FailurePropagator(registry=reg)
        prop.propagate("test", iid, "err")
        inst = reg.get_instance("test", iid)
        assert inst.status.value == "down"


# ═══════════════════════════════════════════════════════════════════
# GAP 2 — Control Plane
# ═══════════════════════════════════════════════════════════════════

class TestSystemState:
    def test_initial_phase(self):
        state = SystemState()
        assert state.phase == SystemPhase.BOOTING

    def test_set_phase(self):
        state = SystemState()
        state.set_phase(SystemPhase.ACTIVE)
        assert state.phase == SystemPhase.ACTIVE

    def test_snapshot(self):
        state = SystemState()
        state.workers = 4
        snap = state.snapshot()
        assert snap["workers"] == 4
        assert snap["phase"] == "booting"

    def test_increment(self):
        state = SystemState()
        state.increment("completed_executions")
        assert state.completed_executions == 1

    def test_get_and_set(self):
        state = SystemState()
        state.set("workers", 8)
        assert state.get("workers") == 8

    def test_uptime_increases(self):
        state = SystemState()
        snap1 = state.snapshot()
        time.sleep(0.01)
        snap2 = state.snapshot()
        assert snap2["uptime"] >= snap1["uptime"]


class TestReconciler:
    def test_no_diffs_when_state_matches(self):
        recon = Reconciler(DesiredState(min_workers=1))
        state = SystemState()
        state.workers = 2
        diffs = recon.reconcile(state)
        assert diffs == []

    def test_scale_up_when_below_min(self):
        recon = Reconciler(DesiredState(min_workers=5))
        state = SystemState()
        state.workers = 2
        diffs = recon.reconcile(state)
        assert any(d["action"] == "scale_up" for d in diffs)

    def test_scale_down_when_above_max(self):
        recon = Reconciler(DesiredState(max_workers=3))
        state = SystemState()
        state.workers = 10
        diffs = recon.reconcile(state)
        assert any(d["action"] == "scale_down" for d in diffs)

    def test_pending_task_overflow(self):
        recon = Reconciler(DesiredState(max_pending_tasks=10))
        state = SystemState()
        state.pending_tasks = 100
        diffs = recon.reconcile(state)
        assert len(diffs) > 0

    def test_desired_property(self):
        desired = DesiredState(min_workers=3)
        recon = Reconciler(desired)
        assert recon.desired.min_workers == 3


class TestWorkerOrchestrator:
    def test_create_worker(self):
        orch = WorkerOrchestrator()
        w = orch.create_worker()
        assert w.state == WorkerState.ACTIVE
        assert orch.active_count() == 1

    def test_terminate_worker(self):
        orch = WorkerOrchestrator()
        w = orch.create_worker()
        assert orch.terminate_worker(w.worker_id) is True
        assert orch.active_count() == 0

    def test_scale_up(self):
        orch = WorkerOrchestrator()
        workers = orch.scale_up(3)
        assert len(workers) == 3
        assert orch.active_count() == 3

    def test_scale_down(self):
        orch = WorkerOrchestrator()
        orch.scale_up(5)
        terminated = orch.scale_down(2)
        assert terminated == 2
        assert orch.active_count() == 3

    def test_assign_and_complete_task(self):
        orch = WorkerOrchestrator()
        w = orch.create_worker()
        assert orch.assign_task(w.worker_id) is True
        assert orch.get_worker(w.worker_id).active_tasks == 1
        assert orch.complete_task(w.worker_id) is True
        assert orch.get_worker(w.worker_id).active_tasks == 0

    def test_shutdown_all(self):
        orch = WorkerOrchestrator()
        orch.scale_up(4)
        assert orch.shutdown_all() == 4
        assert orch.active_count() == 0


class TestHealthMonitor:
    def test_initial_unknown_is_healthy(self):
        hm = HealthMonitor()
        assert hm.is_healthy("unknown")  # unknown components are healthy

    def test_heartbeat_keeps_healthy(self):
        hm = HealthMonitor(heartbeat_ttl=60.0)
        hm.record_heartbeat("worker-1")
        assert hm.is_healthy("worker-1")

    def test_missing_heartbeat_is_unhealthy(self):
        hm = HealthMonitor(heartbeat_ttl=0.001)
        hm.record_heartbeat("worker-1")
        time.sleep(0.01)
        unhealthy = hm.check_all()
        assert "worker-1" in unhealthy

    def test_mark_unhealthy(self):
        hm = HealthMonitor()
        hm.mark_unhealthy("svc-1", "crashed")
        assert not hm.is_healthy("svc-1")

    def test_recent_alerts(self):
        hm = HealthMonitor()
        hm.mark_degraded("svc-1", "high latency")
        assert len(hm.recent_alerts()) == 1

    def test_status_dict(self):
        hm = HealthMonitor()
        hm.record_heartbeat("worker-1")
        st = hm.status()
        assert "worker-1" in st


class TestControlPlane:
    def test_decide_records_decision(self):
        cp = ControlPlane()
        d = cp.decide(ControlAction.HEALTH_CHECK, "test")
        assert d.action == ControlAction.HEALTH_CHECK
        assert len(cp.decisions()) == 1

    def test_state_property(self):
        cp = ControlPlane()
        assert cp.state.phase == SystemPhase.BOOTING

    def test_start_and_shutdown(self):
        cp = ControlPlane()
        cp.start(interval=0.1)
        assert cp._running
        cp.shutdown()
        assert not cp._running

    def test_tick_runs_without_error(self):
        cp = ControlPlane()
        result = cp._tick()
        assert result is None


# ═══════════════════════════════════════════════════════════════════
# GAP 3 — Runtime OS
# ═══════════════════════════════════════════════════════════════════

class TestRuntimeOS:
    def test_submit_without_engine_returns_error(self):
        os = RuntimeOS()
        from core.models.dag import DependencyGraph
        dag = DependencyGraph()
        eid = os.submit(dag)
        rec = os.observe(eid)
        assert rec["status"] == "failed"

    def test_observe_not_found(self):
        os = RuntimeOS()
        rec = os.observe("nonexistent")
        assert rec["status"] == "not_found"

    def test_cancel_not_found(self):
        os = RuntimeOS()
        assert os.cancel("nonexistent") is False

    def test_scale(self):
        os = RuntimeOS()
        count = os.scale(5)
        assert count == 5

    def test_scale_down(self):
        os = RuntimeOS()
        os.scale(5)
        count = os.scale(2)
        assert count == 2

    def test_list_executions(self):
        os = RuntimeOS()
        assert os.list_executions() == []

    def test_status_summary(self):
        os = RuntimeOS()
        summary = os.status_summary()
        assert "started" in summary
        assert summary["total_executions"] == 0

    def test_start_and_shutdown(self):
        os = RuntimeOS()
        os.start()
        assert os._started
        os.shutdown()
        assert not os._started

    def test_properties(self):
        os = RuntimeOS()
        assert os.mesh is not None
        assert os.registry is not None
        assert os.control is not None

    def test_replay_raises_for_nonexistent(self):
        os = RuntimeOS()
        from core.models.dag import DependencyGraph
        with pytest.raises(ValueError):
            os.replay("nonexistent")

    def test_resume_paused_execution(self):
        os = RuntimeOS()
        from core.models.dag import DependencyGraph, PlanNode
        dag = DependencyGraph()
        dag.add_node(PlanNode(id="n1", tool="echo"))
        eid = os.submit(dag)
        # Mark as paused
        os._executions[eid].status = "paused"
        assert os.resume(eid)
        assert os._executions[eid].status == "resumed"

    def test_resume_failed_execution(self):
        os = RuntimeOS()
        from core.models.dag import DependencyGraph, PlanNode
        dag = DependencyGraph()
        dag.add_node(PlanNode(id="n1", tool="echo"))
        eid = os.submit(dag)
        os._executions[eid].status = "failed"
        assert os.resume(eid)

    def test_resume_nonexistent(self):
        os = RuntimeOS()
        assert not os.resume("nonexistent")

    def test_register_worker(self):
        os = RuntimeOS()
        os.register_worker("test-worker", "test-node",
                            total_cpu=4, total_memory=8192,
                            total_gpu=1, total_gpu_memory=4096,
                            capacity=5)
        assert "test-worker" in os._orchestrator._workers

    def test_register_worker_without_node_id(self):
        os = RuntimeOS()
        os.register_worker("auto-worker", total_cpu=2, total_memory=4096)
        assert "auto-worker" in os._orchestrator._workers


# ═══════════════════════════════════════════════════════════════════
# GAP 4 — Evolution (suggestion-based, no auto-mutation)
# ═══════════════════════════════════════════════════════════════════

class TestRuleRefiner:
    def test_no_data_produces_no_suggestions(self):
        refiner = RuleRefiner()
        suggestions = refiner.analyze_execution_data({})
        assert suggestions == []

    def test_high_failure_rate_suggests_threshold_change(self):
        refiner = RuleRefiner()
        data = {
            "failures": [{"tool": "t1"}] * 30,
            "total_executions": 100,
            "blocked_executions": [],
            "hotspots": [],
        }
        suggestions = refiner.analyze_execution_data(data)
        assert len(suggestions) > 0
        assert any(s.rule_id == "LAW_16" for s in suggestions)

    def test_high_block_rate_suggests_severity_change(self):
        refiner = RuleRefiner()
        data = {
            "failures": [],
            "total_executions": 100,
            "blocked_executions": [{"tool": "t1"}] * 40,
            "hotspots": [],
        }
        suggestions = refiner.analyze_execution_data(data)
        assert any(s.rule_id == "LAW_14" for s in suggestions)

    def test_hotspot_frequency_suggests_tracing_change(self):
        refiner = RuleRefiner()
        data = {
            "failures": [],
            "total_executions": 200,
            "blocked_executions": [],
            "hotspots": [{"tool": "hot_tool", "frequency": 150}],
        }
        suggestions = refiner.analyze_execution_data(data)
        assert any(s.rule_id == "LAW_19" for s in suggestions)

    def test_suggestions_accessible(self):
        refiner = RuleRefiner()
        data = {"failures": [{}] * 50, "total_executions": 100,
                "blocked_executions": [], "hotspots": []}
        refiner.analyze_execution_data(data)
        assert len(refiner.suggestions()) > 0


class TestCanonEvolver:
    def test_evolve_returns_report_not_mutations(self):
        evolver = CanonEvolver()
        data = {"failures": [{}] * 50, "total_executions": 100,
                "blocked_executions": [], "hotspots": []}
        report = evolver.evolve(data)
        assert isinstance(report, EvolutionReport)
        assert not hasattr(report, "mutations")

    def test_evolve_filters_by_confidence(self):
        policy = EvolutionPolicy(mode="conservative")
        evolver = CanonEvolver(policy=policy)
        data = {"failures": [{}] * 5, "total_executions": 100,
                "blocked_executions": [], "hotspots": []}
        report = evolver.evolve(data)
        for s in report.suggestions:
            assert s.confidence >= 0.8

    def test_evolve_verbose_shows_all(self):
        policy = EvolutionPolicy(mode="verbose")
        evolver = CanonEvolver(policy=policy)
        data = {"failures": [{}] * 5, "total_executions": 100,
                "blocked_executions": [], "hotspots": []}
        report = evolver.evolve(data)
        # verbose shows everything (conf >= 0.0)
        assert isinstance(report, EvolutionReport)

    def test_no_suggestions_for_clean_data(self):
        evolver = CanonEvolver()
        data = {"failures": [], "total_executions": 10,
                "blocked_executions": [], "hotspots": []}
        report = evolver.evolve(data)
        assert len(report.suggestions) == 0

    def test_report_contains_data_summary(self):
        evolver = CanonEvolver()
        data = {"failures": [{}], "total_executions": 100,
                "blocked_executions": [], "hotspots": []}
        report = evolver.evolve(data)
        assert "total_executions" in report.data_summary

    # ── LAW 28 — Approval Gate ──

    def test_evolve_without_approval_func_proceeds(self):
        evolver = CanonEvolver()
        data = {"failures": [{}] * 50, "total_executions": 100,
                "blocked_executions": [], "hotspots": []}
        report = evolver.evolve(data)
        assert isinstance(report, EvolutionReport)

    def test_evolve_rejects_when_approval_func_returns_false(self):
        evolver = CanonEvolver(
            approval_func=lambda s: False,
        )
        data = {"failures": [{}] * 50, "total_executions": 100,
                "blocked_executions": [], "hotspots": []}
        report = evolver.evolve(data)
        assert not report.approved

    def test_evolve_accepts_when_approval_func_returns_true(self):
        evolver = CanonEvolver(
            approval_func=lambda s: True,
        )
        data = {"failures": [{}] * 50, "total_executions": 100,
                "blocked_executions": [], "hotspots": []}
        report = evolver.evolve(data, approved_by="alice")
        assert report.approved
        assert report.approved_by == "alice"

    def test_evolve_approval_func_receives_suggestions(self):
        received = []
        def gate(suggestions):
            received.extend(suggestions)
            return True
        evolver = CanonEvolver(approval_func=gate)
        data = {"failures": [{}] * 50, "total_executions": 100,
                "blocked_executions": [], "hotspots": []}
        evolver.evolve(data)
        assert len(received) > 0

    # ── LAW 29 — Audit Trail ──

    def test_evolve_records_audit_trail(self):
        evolver = CanonEvolver()
        data = {"failures": [{}] * 50, "total_executions": 100,
                "blocked_executions": [], "hotspots": []}
        evolver.evolve(data)
        assert len(evolver.audit_trail) == 1
        assert "audit_id" in evolver.audit_trail[0]

    def test_evolve_calls_audit_log_callback(self):
        audit_entries = []
        evolver = CanonEvolver(
            audit_log=lambda e: audit_entries.append(e),
        )
        data = {"failures": [{}] * 50, "total_executions": 100,
                "blocked_executions": [], "hotspots": []}
        evolver.evolve(data)
        assert len(audit_entries) == 1
        assert "suggestions" in audit_entries[0]

    def test_report_contains_audit_id(self):
        evolver = CanonEvolver()
        data = {"failures": [{}] * 50, "total_executions": 100,
                "blocked_executions": [], "hotspots": []}
        report = evolver.evolve(data)
        assert report.audit_id != ""

    # ── LAW 30 — Rollback ──

    def test_rollback_without_func_returns_false(self):
        evolver = CanonEvolver()
        assert evolver.rollback("token") is False

    def test_rollback_with_func(self):
        evolver = CanonEvolver(
            rollback_func=lambda t: t == "valid_token",
        )
        assert evolver.rollback("valid_token") is True
        assert evolver.rollback("invalid") is False

    def test_report_contains_rollback_token_when_approved(self):
        evolver = CanonEvolver(approval_func=lambda s: True)
        data = {"failures": [{}] * 50, "total_executions": 100,
                "blocked_executions": [], "hotspots": []}
        report = evolver.evolve(data, approved_by="bob")
        assert report.rollback_token != ""


class TestFeedbackActuator:
    def test_generate_report(self):
        actuator = FeedbackActuator()
        data = {"failures": [{}] * 50, "total_executions": 100,
                "blocked_executions": [], "hotspots": []}
        report = actuator.generate_report(data)
        assert isinstance(report, FeedbackReport)
        assert isinstance(report.evolution, EvolutionReport)

    def test_callbacks_fired(self):
        actuator = FeedbackActuator()
        called = []
        actuator.on_report(lambda r: called.append(r))
        data = {"failures": [{}] * 50, "total_executions": 100,
                "blocked_executions": [], "hotspots": []}
        actuator.generate_report(data)
        assert len(called) == 1

    def test_recent_reports(self):
        actuator = FeedbackActuator()
        data = {"failures": [{}] * 50, "total_executions": 100,
                "blocked_executions": [], "hotspots": []}
        actuator.generate_report(data)
        assert len(actuator.recent_reports()) == 1

    def test_summarize(self):
        actuator = FeedbackActuator()
        data = {"failures": [{}] * 50, "total_executions": 100,
                "blocked_executions": [], "hotspots": []}
        actuator.generate_report(data)
        summary = actuator.summarize()
        assert summary["total_reports"] >= 1

    def test_no_auto_mutation_method(self):
        actuator = FeedbackActuator()
        assert not hasattr(actuator, "apply_mutation")
        assert not hasattr(actuator, "auto_apply")
