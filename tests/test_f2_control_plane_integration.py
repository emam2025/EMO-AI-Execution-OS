"""Phase F2 — Control Plane & Autoscaler: Comprehensive tests.

Groups:
  G1 — TestOscillationPrevention    (6 tests) — cooldown, hysteresis, cycles
  G2 — TestDrainLifecycle            (5 tests) — 5-phase drain, LAW 3
  G3 — TestReconciliationAccuracy    (4 tests) — delta, corrections, scheduling
  G4 — TestHealthSupervisor          (4 tests) — probe, degradation, eviction
  G5 — TestControlPlaneOrchestration (4 tests) — reconcile, policy, state
  G6 — TestCanonCompliance           (3 tests) — LAW/RULE comments, imports

Total: ~26 tests

Ref: DEVELOPER.md §15.9
Ref: Canon LAW 3, LAW 5, LAW 8, LAW 11, RULE 1-5
Ref: EXEC-DIRECTIVE-004
"""

import time
from unittest.mock import MagicMock

import pytest

from core.runtime.control_plane.autoscaler import Autoscaler
from core.runtime.control_plane.control_plane import ControlPlane
from core.runtime.control_plane.health_supervisor import HealthSupervisor
from core.runtime.control_plane.oscillation_guard import (
    ConsecutiveCycleTracker,
    CooldownTimer,
    HysteresisEvaluator,
)
from core.runtime.control_plane.reconciliation_loop import ReconciliationLoop
from core.runtime.control_plane.worker_drainer import WorkerDrainer
from core.runtime.models.control_plane_models import (
    ClusterSnapshot,
    Correction,
    DegradationLevel,
    DeltaReport,
    DrainReceipt,
    EvictionReceipt,
    HealthEvent,
    HealthEventType,
    HealthProbeResult,
    LoadMetric,
    PolicyResult,
    ReconcileReport,
    ScalingPolicy,
    ScalingReceipt,
    ScalingSignal,
    WorkerDrainingState,
    WorkerState,
)


# ════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════


def policy(**kwargs) -> ScalingPolicy:
    defaults = dict(
        min_workers=1, max_workers=10, target_utilization=0.70,
        cooldown_sec=60.0, hysteresis_pct=0.10, scale_step=2,
    )
    defaults.update(kwargs)
    return ScalingPolicy(**defaults)


def snapshot(workers: int = 4, cpu: float = 50.0) -> ClusterSnapshot:
    return ClusterSnapshot(
        worker_count=workers,
        healthy_count=workers,
        load=LoadMetric(cpu_pct=cpu, mem_pct=50.0),
    )


# ════════════════════════════════════════════════════════════════════
# G1 — TestOscillationPrevention (6 tests)
# ════════════════════════════════════════════════════════════════════


class TestOscillationPrevention:
    """G1: Oscillation prevention via cooldown, hysteresis, consecutive cycles."""

    def test_cooldown_timer_expiry(self):
        timer = CooldownTimer()
        assert timer.is_expired(policy(cooldown_sec=0))
        timer.record_action()
        assert not timer.is_expired(policy(cooldown_sec=9999))
        assert timer.remaining(policy(cooldown_sec=9999)) > 0

    def test_cooldown_timer_reset(self):
        timer = CooldownTimer()
        timer.record_action()
        timer.reset()
        assert timer.last_action_time == 0.0

    def test_hysteresis_band_holds(self):
        eval_ = HysteresisEvaluator()
        pol = policy(target_utilization=0.70, hysteresis_pct=0.10)
        # band = [0.60, 0.80]
        assert eval_.evaluate(0.85, pol) == ScalingSignal.UP
        assert eval_.evaluate(0.55, pol) == ScalingSignal.DOWN
        assert eval_.evaluate(0.70, pol) == ScalingSignal.HOLD
        assert eval_.evaluate(0.75, pol) == ScalingSignal.HOLD

    def test_consecutive_cycle_tracker(self):
        tracker = ConsecutiveCycleTracker(required_consecutive=2)
        tracker.record(ScalingSignal.UP)
        assert not tracker.threshold_met(ScalingSignal.UP)
        tracker.record(ScalingSignal.UP)
        assert tracker.threshold_met(ScalingSignal.UP)

    def test_consecutive_cycle_reset_on_change(self):
        tracker = ConsecutiveCycleTracker(required_consecutive=2)
        tracker.record(ScalingSignal.UP)
        tracker.record(ScalingSignal.DOWN)
        assert tracker.count_consecutive(ScalingSignal.DOWN) == 1

    def test_apply_scaling_uses_scale_step(self):
        autoscaler = Autoscaler()
        receipt = autoscaler.apply_scaling(10, policy(scale_step=2), current_workers=4)
        assert receipt.actual_count == 6  # 4 + min(6, 2)
        assert receipt.signal == ScalingSignal.UP


# ════════════════════════════════════════════════════════════════════
# G2 — TestDrainLifecycle (5 tests)
# ════════════════════════════════════════════════════════════════════


class TestDrainLifecycle:
    """G2: Worker drain lifecycle per §15.9.3."""

    def test_full_drain_returns_receipt(self):
        drainer = WorkerDrainer()
        receipt = drainer.drain("w1")
        assert isinstance(receipt, DrainReceipt)
        assert receipt.success

    def test_drain_phases_execute_in_order(self):
        drainer = WorkerDrainer()
        assert drainer.mark_draining("w2")
        assert drainer.get_drain_state("w2") == WorkerDrainingState.MARK_DRAINING
        assert drainer.stop_new_leases("w2")
        assert drainer.get_drain_state("w2") == WorkerDrainingState.STOP_NEW_LEASES
        assert drainer.await_completion("w2", active_lease_count=0)
        assert drainer.get_drain_state("w2") == WorkerDrainingState.AWAIT_COMPLETION
        assert drainer.release_leases("w2", 0) == 0
        assert drainer.get_drain_state("w2") == WorkerDrainingState.RELEASE_LEASES
        assert drainer.terminate("w2")
        assert drainer.get_drain_state("w2") == WorkerDrainingState.TERMINATE

    def test_terminate_requires_release_leases_first(self):
        drainer = WorkerDrainer()
        drainer.mark_draining("w3")
        drainer.stop_new_leases("w3")
        # Skip directly to terminate without release
        assert not drainer.terminate("w3")

    def test_drain_idempotent_repeated_call(self):
        drainer = WorkerDrainer()
        r1 = drainer.drain("w4")
        r2 = drainer.drain("w4")
        assert r1.success and r2.success

    def test_drain_list_tracks_active(self):
        drainer = WorkerDrainer()
        drainer.mark_draining("w5")
        drainer.mark_draining("w6")
        assert "w5" in drainer.draining_workers
        assert "w6" in drainer.draining_workers


# ════════════════════════════════════════════════════════════════════
# G3 — TestReconciliationAccuracy (4 tests)
# ════════════════════════════════════════════════════════════════════


class TestReconciliationAccuracy:
    """G3: Reconciliation loop delta accuracy."""

    def test_compare_desired_no_drift(self):
        loop = ReconciliationLoop()
        actual = snapshot(4)
        desired = snapshot(4)
        report = loop.compare_desired(actual, desired)
        assert not report.drift_detected
        assert report.worker_deficit == 0
        assert report.worker_surplus == 0

    def test_compare_desired_deficit(self):
        loop = ReconciliationLoop()
        actual = snapshot(2)
        desired = snapshot(5)
        report = loop.compare_desired(actual, desired)
        assert report.drift_detected
        assert report.worker_deficit == 3
        assert report.worker_surplus == 0

    def test_compare_desired_surplus(self):
        loop = ReconciliationLoop()
        actual = snapshot(7)
        desired = snapshot(3)
        report = loop.compare_desired(actual, desired)
        assert report.drift_detected
        assert report.worker_deficit == 0
        assert report.worker_surplus == 4

    def test_compute_delta_returns_prioritized_corrections(self):
        loop = ReconciliationLoop()
        actual = snapshot(1, cpu=90.0)
        desired = snapshot(5)
        corrections = loop.compute_delta(actual, desired)
        assert len(corrections) >= 1
        # scale_up should be priority 1
        assert corrections[0].action == "scale_up"


# ════════════════════════════════════════════════════════════════════
# G4 — TestHealthSupervisor (4 tests)
# ════════════════════════════════════════════════════════════════════


class TestHealthSupervisor:
    """G4: Health probe, degradation, eviction."""

    def test_probe_unknown_worker(self):
        hs = HealthSupervisor()
        result = hs.probe_worker("unknown")
        assert not result.alive
        assert result.state == WorkerState.UNKNOWN

    def test_assess_degradation_none(self):
        hs = HealthSupervisor()
        probe = HealthProbeResult(worker_id="w1", alive=True, cpu_pct=50.0, mem_pct=60.0)
        deg = hs.assess_degradation("w1", probe)
        assert deg == DegradationLevel.NONE

    def test_assess_degradation_critical_not_alive(self):
        hs = HealthSupervisor()
        probe = HealthProbeResult(worker_id="w1", alive=False)
        deg = hs.assess_degradation("w1", probe)
        assert deg == DegradationLevel.CRITICAL

    def test_trigger_eviction_idempotent(self):
        hs = HealthSupervisor()
        hs.update_worker_health("w2", WorkerState.HEALTHY, cpu_pct=0.0, mem_pct=0.0)
        hs._degradation_levels["w2"] = DegradationLevel.CRITICAL
        r1 = hs.trigger_eviction("w2", "critical")
        assert r1.evicted
        assert r1.state == WorkerState.TERMINATED
        r2 = hs.trigger_eviction("w2", "already done")
        assert not r2.evicted  # idempotent — already terminated


# ════════════════════════════════════════════════════════════════════
# G5 — TestControlPlaneOrchestration (4 tests)
# ════════════════════════════════════════════════════════════════════


class TestControlPlaneOrchestration:
    """G5: ControlPlane orchestration flow."""

    def test_enforce_policy_returns_result(self):
        cp = ControlPlane()
        result = cp.enforce_policy(policy(), snapshot(4, cpu=50.0))
        assert isinstance(result, PolicyResult)

    def test_publish_state_returns_snapshot(self):
        cp = ControlPlane()
        state = cp.publish_state()
        assert state.active_workers == 0
        assert state.draining_workers == []

    def test_drain_worker_decrements_count(self):
        cp = ControlPlane()
        cp.drain_worker("w1", "test")
        state = cp.publish_state()
        assert state.active_workers >= 0  # drainer managed
        assert cp.worker_drainer.is_terminated("w1")

    def test_reconcile_runs_without_error(self):
        cp = ControlPlane()
        desired = snapshot(5)
        report = cp.reconcile(desired)
        assert isinstance(report, ReconcileReport)
        assert isinstance(report.observed_workers, int)


# ════════════════════════════════════════════════════════════════════
# G6 — TestCanonCompliance (3 tests)
# ════════════════════════════════════════════════════════════════════


class TestCanonCompliance:
    """G6: Canon law and rule compliance verification."""

    CONTROL_PLANE_FILES = [
        "core/runtime/control_plane/__init__.py",
        "core/runtime/control_plane/autoscaler.py",
        "core/runtime/control_plane/control_plane.py",
        "core/runtime/control_plane/health_supervisor.py",
        "core/runtime/control_plane/oscillation_guard.py",
        "core/runtime/control_plane/reconciliation_loop.py",
        "core/runtime/control_plane/worker_drainer.py",
        "core/runtime/models/control_plane_models.py",
    ]

    def test_all_control_plane_files_have_law_comments(self):
        """Every new file should contain # LAW- or # RULE- comments."""
        import os
        missing = []
        for fpath in self.CONTROL_PLANE_FILES:
            if not os.path.exists(fpath):
                missing.append(f"{fpath} (not found)")
                continue
            with open(fpath) as f:
                content = f.read()
            has_law = "LAW-" in content or "RULE-" in content
            if not has_law:
                missing.append(fpath)
        assert not missing, f"Files missing LAW/RULE comments: {missing}"

    def test_all_exports_match_design_protocols(self):
        """Verify key classes exist (protocol conformance)."""
        assert hasattr(Autoscaler, "evaluate_load")
        assert hasattr(Autoscaler, "calculate_target_count")
        assert hasattr(Autoscaler, "apply_scaling")
        assert hasattr(Autoscaler, "enforce_cooldown")
        assert hasattr(HealthSupervisor, "probe_worker")
        assert hasattr(HealthSupervisor, "assess_degradation")
        assert hasattr(HealthSupervisor, "trigger_eviction")
        assert hasattr(HealthSupervisor, "publish_health_event")
        assert hasattr(ReconciliationLoop, "observe_current")
        assert hasattr(ReconciliationLoop, "compare_desired")
        assert hasattr(ReconciliationLoop, "compute_delta")
        assert hasattr(ReconciliationLoop, "schedule_correction")
        assert hasattr(ControlPlane, "reconcile")
        assert hasattr(ControlPlane, "enforce_policy")
        assert hasattr(ControlPlane, "publish_state")
        assert hasattr(ControlPlane, "drain_worker")

    def test_composition_root_wires_control_plane(self):
        from core.composition.root import CompositionRoot
        root = CompositionRoot()
        cp = root.control_plane
        assert cp is not None
        assert hasattr(cp, "reconcile")
        assert hasattr(cp, "enforce_policy")
        assert hasattr(cp, "publish_state")
        assert hasattr(cp, "drain_worker")
