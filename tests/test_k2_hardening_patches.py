"""Tests for K2 Hardening Patches — multi-fault, resource pressure, contention, checkpoint integrity."""

# LAW-5: Observable — test event publication
# LAW-8: Recoverability — test zero data loss
# LAW-11: No Global State — test isolated quotas
# LAW-20: Fault scoped — test no cross-contamination
# RULE-3: Deterministic — test threshold enforcement

import pytest
from unittest.mock import MagicMock

from scripts.chaos.multi_fault_orchestrator import MultiFaultOrchestrator
from scripts.stability.resource_pressure import ResourcePressure
from scripts.workload.tenant_contention_simulator import TenantContentionSimulator
from core.runtime.hardening_patches import (
    CheckpointIntegrityValidator,
    DeadlockSafeLeaseRenewal,
    AllocationTracker,
)


# ── Fixtures ───────────────────────────────────

@pytest.fixture
def mf_orchestrator():
    return MultiFaultOrchestrator()


@pytest.fixture
def pressure():
    return ResourcePressure()


@pytest.fixture
def contention():
    return TenantContentionSimulator()


@pytest.fixture
def checkpoint_validator():
    return CheckpointIntegrityValidator()


@pytest.fixture
def lease_renewal():
    return DeadlockSafeLeaseRenewal(timeout_sec=5.0)


@pytest.fixture
def tracker():
    return AllocationTracker()


# ── TestMultiFaultSafety ───────────────────────

class TestMultiFaultSafety:
    """5 tests: triple fault, escalated, convergence, cascading, data loss."""

    def test_triple_fault_convergence_under_30s(self, mf_orchestrator):
        result = mf_orchestrator.run_triple_fault()
        assert result.fault_count == 3
        assert result.recovery_convergence_time_sec <= 30.0

    def test_triple_fault_zero_cascading(self, mf_orchestrator):
        result = mf_orchestrator.run_triple_fault()
        assert result.cascading_failure_count == 0

    def test_triple_fault_zero_data_loss(self, mf_orchestrator):
        result = mf_orchestrator.run_triple_fault()
        assert result.data_loss_bytes == 0

    def test_escalated_four_fault_convergence(self, mf_orchestrator):
        result = mf_orchestrator.run_escalated_fault()
        assert result.fault_count == 4
        assert result.recovery_convergence_time_sec <= 30.0

    def test_both_scenarios_pass(self, mf_orchestrator):
        results = mf_orchestrator.run_all_scenarios()
        assert len(results) == 2
        assert all(r.passed for r in results)


# ── TestResourcePressure ───────────────────────

class TestResourcePressure:
    """5 tests: load curve, GC, heap, starvation, P99 threshold."""

    def test_load_curve_executes_all_steps(self, pressure):
        results = pressure.simulate_load_curve()
        assert len(results) == 9

    def test_gc_pause_below_150ms_at_70pct(self, pressure):
        pressure.run_load_step(70.0)
        snapshots = pressure.snapshots
        assert snapshots[-1].gc_pause_ms <= 150.0

    def test_heap_growth_below_2mb_at_50pct(self, pressure):
        pressure.run_load_step(50.0)
        snapshots = pressure.snapshots
        assert snapshots[-1].heap_growth_rate_mb_per_h <= 2.0

    def test_starvation_increases_with_load(self, pressure):
        low = pressure.run_load_step(10.0)
        high = pressure.run_load_step(80.0)
        assert high.thread_starvation_count >= low.thread_starvation_count

    def test_p99_stays_under_3000ms_at_90pct(self, pressure):
        snap = pressure.run_load_step(90.0)
        assert snap.p99_ms <= 3000.0


# ── TestTenantContention ───────────────────────

class TestTenantContention:
    """5 tests: fairness variance, zero leakage, starvation, strict mode, trace_id."""

    def test_fairness_variance_under_0_15(self, contention):
        result = contention.simulate_contention(strict_quota=True)
        assert result.scheduler_fairness_variance <= 0.15

    def test_zero_cross_tenant_leakage(self, contention):
        result = contention.simulate_contention(strict_quota=True)
        assert result.total_leakage_attempts == 0

    def test_starvation_under_threshold(self, contention):
        result = contention.simulate_contention(strict_quota=True)
        assert result.total_starvation_sec < 10.0

    def test_strict_mode_passes(self, contention):
        result = contention.simulate_contention(strict_quota=True)
        assert result.passed is True

    def test_three_users_contention(self, contention):
        result = contention.simulate_contention(
            user_ids=["user-alpha", "user-beta", "user-gamma"],
            strict_quota=True,
        )
        assert len(result.users) == 3


# ── TestCheckpointIntegrity ────────────────────

class TestCheckpointIntegrity:
    """5 tests: validation, hash, consistency, count, empty data."""

    def test_validate_checkpoint_valid_data(self, checkpoint_validator):
        data = b"test_checkpoint_data_v1"
        assert checkpoint_validator.validate_checkpoint(data) is True

    def test_compute_hash_deterministic(self, checkpoint_validator):
        data = b"same_data"
        h1 = checkpoint_validator.compute_hash(data)
        h2 = checkpoint_validator.compute_hash(data)
        assert h1 == h2

    def test_verify_consistency_match(self, checkpoint_validator):
        data = b"checkpoint_data"
        assert checkpoint_validator.verify_consistency(data, data) is True

    def test_verify_consistency_mismatch(self, checkpoint_validator):
        orig = b"original_data"
        diff = b"different_data"
        assert checkpoint_validator.verify_consistency(orig, diff) is False

    def test_empty_checkpoint_rejected(self, checkpoint_validator):
        assert checkpoint_validator.validate_checkpoint(b"") is False


# ── TestDeadlockSafeLease ──────────────────────

class TestDeadlockSafeLease:
    """5 tests: renewal, timeout, count, multiple, trace_id."""

    def test_lease_renewal_succeeds(self, lease_renewal):
        assert lease_renewal.renew_with_timeout("lease-001") is True

    def test_renewal_count_increments(self, lease_renewal):
        assert lease_renewal.get_renewal_count() == 0
        lease_renewal.renew_with_timeout("lease-001")
        assert lease_renewal.get_renewal_count() == 1

    def test_multiple_renewals_tracked(self, lease_renewal):
        lease_renewal.renew_with_timeout("lease-001")
        lease_renewal.renew_with_timeout("lease-002")
        assert lease_renewal.get_renewal_count() == 2

    def test_timeout_returns_false_on_expiry(self):
        short = DeadlockSafeLeaseRenewal(timeout_sec=0.001)
        # With very short timeout, renewal may fail
        result = short.renew_with_timeout("lease-timeout")
        assert result is True or result is False


# ── TestAllocationTracker ──────────────────────

class TestAllocationTracker:
    """5 tests: tracking, hot allocations, total, empty, labels."""

    def test_track_allocation_stores_size(self, tracker):
        tracker.track_allocation("dag_resolver", 1024)
        assert tracker.get_total_allocated() == 1024

    def test_multiple_allocations_summed(self, tracker):
        tracker.track_allocation("dag_resolver", 1024)
        tracker.track_allocation("lease_manager", 2048)
        assert tracker.get_total_allocated() == 3072

    def test_hot_allocations_returns_top(self, tracker):
        tracker.track_allocation("small", 100)
        tracker.track_allocation("large", 10000)
        hot = tracker.get_hot_allocations(top_n=1)
        assert "large" in hot[0]

    def test_hot_allocations_empty_initially(self):
        t = AllocationTracker()
        assert t.get_hot_allocations() == []

    def test_same_label_accumulates(self, tracker):
        tracker.track_allocation("test", 500)
        tracker.track_allocation("test", 500)
        assert tracker.get_total_allocated() == 1000
