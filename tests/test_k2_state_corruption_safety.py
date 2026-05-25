"""Tests for K2 State Corruption Safety — lease, WAL, consistency, graceful degradation."""

# LAW-5: Observable — test event publication
# LAW-8: Recoverability — test zero data loss
# LAW-20: Fault scoped — test no cross-contamination
# RULE-3: Deterministic — test consistency recovery

import pytest
from unittest.mock import MagicMock

from scripts.chaos.state_corruptor import StateCorruptor


@pytest.fixture
def state_corruptor():
    return StateCorruptor()


# ── TestLeaseStoreCorruption ───────────────────

class TestLeaseStoreCorruption:
    """4 tests: corruption injection, fallback, consistency, errors."""

    def test_lease_corruption_injects_bytes(self, state_corruptor):
        event = state_corruptor.corrupt_lease_store(5.0)
        assert event.target == "lease_store"
        assert event.bytes_corrupted > 0

    def test_lease_corruption_triggers_fallback(self, state_corruptor):
        event = state_corruptor.corrupt_lease_store(5.0)
        assert event.fallback_activated is True
        assert event.fallback_activation_time_ms > 0

    def test_lease_corruption_high_consistency(self, state_corruptor):
        for _ in range(20):
            event = state_corruptor.corrupt_lease_store(5.0)
            assert event.consistency_recovery_rate >= 0.98

    def test_lease_corruption_minimal_user_errors(self, state_corruptor):
        event = state_corruptor.corrupt_lease_store(5.0)
        assert event.user_visible_errors <= 2


# ── TestWALCorruption ──────────────────────────

class TestWALCorruption:
    """4 tests: WAL corruption, fallback, consistency, zero user errors."""

    def test_wal_corruption_targets_db_log(self, state_corruptor):
        event = state_corruptor.corrupt_wal_file()
        assert event.target == "execution_memory_db_wal"

    def test_wal_corruption_triggers_fallback(self, state_corruptor):
        event = state_corruptor.corrupt_wal_file()
        assert event.fallback_activated is True
        assert event.fallback_activation_time_ms > 0

    def test_wal_corruption_high_consistency(self, state_corruptor):
        for _ in range(20):
            event = state_corruptor.corrupt_wal_file()
            assert event.consistency_recovery_rate >= 0.99

    def test_wal_corruption_zero_user_errors(self, state_corruptor):
        event = state_corruptor.corrupt_wal_file()
        assert event.user_visible_errors == 0


# ── TestGracefulDegradation ────────────────────

class TestGracefulDegradation:
    """4 tests: overall consistency, error count, pass/fail, trace_id."""

    def test_corruption_suite_overall_consistency(self, state_corruptor):
        result = state_corruptor.run_corruption_suite()
        assert result.overall_consistency_recovery_rate >= 0.99

    def test_corruption_suite_errors_under_limit(self, state_corruptor):
        result = state_corruptor.run_corruption_suite()
        assert result.total_user_visible_errors <= 2

    def test_corruption_suite_passes(self, state_corruptor):
        result = state_corruptor.run_corruption_suite()
        assert result.passed is True

    def test_k2_trace_id_propagation(self, state_corruptor):
        assert state_corruptor.k2_trace_id.startswith("k2_")
        result = state_corruptor.run_corruption_suite()
        assert result.k2_trace_id == state_corruptor.k2_trace_id


# ── TestStorageAndRecovery ─────────────────────

class TestStorageAndRecovery:
    """3 tests: results storage, multiple runs, events stored."""

    def test_results_stored_after_suite(self, state_corruptor):
        assert len(state_corruptor.get_results()) == 0
        state_corruptor.run_corruption_suite()
        assert len(state_corruptor.get_results()) == 1

    def test_multiple_runs_accumulate(self, state_corruptor):
        state_corruptor.run_corruption_suite()
        state_corruptor.run_corruption_suite()
        assert len(state_corruptor.get_results()) == 2

    def test_lease_and_wal_both_tested(self, state_corruptor):
        result = state_corruptor.run_corruption_suite()
        assert len(result.events) == 2
        targets = {e.target for e in result.events}
        assert "lease_store" in targets
        assert "execution_memory_db_wal" in targets
