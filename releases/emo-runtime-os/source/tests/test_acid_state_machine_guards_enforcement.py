"""Phase I2 — ACID State Machine & Guard Enforcement Tests.  # LAW-14 LAW-20 LAW-21 RULE-1 RULE-3 RULE-4 RULE-5

Tests the 7-state ACID lifecycle machine with all 8 transitions (A1–A8)
and 8 ACID Guards (G1–G8). Verifies that isolation level, quorum,
partition key, and deadlock invariants are enforced.

Ref: Canon LAW 14, LAW 20, LAW 21
Ref: Canon RULE 1, RULE 3, RULE 4, RULE 5
Ref: artifacts/design/i2/03_acid_sync_machine.md
"""

from __future__ import annotations

import pytest

from core.runtime.data.acid_state_machine import (
    ACIDStateMachine,
    ACIDState,
    ACIDTransition,
    GuardianResult,
)


@pytest.fixture
def sm() -> ACIDStateMachine:
    return ACIDStateMachine()


# ── TestStateMachineTransitions (8 tests for A1–A8) ─────────────────────────


class TestStateMachineTransitions:
    def test_a1_tx_start_to_validation(self, sm: ACIDStateMachine):
        assert sm.current_state == ACIDState.TX_START
        result = sm.apply_transition(ACIDTransition.A1)
        assert result == ACIDState.VALIDATION

    def test_a2_validation_to_partition_routing(self, sm: ACIDStateMachine):
        sm.apply_transition(ACIDTransition.A1)
        result = sm.apply_transition(ACIDTransition.A2)
        assert result == ACIDState.PARTITION_ROUTING

    def test_a3_partition_routing_to_commit(self, sm: ACIDStateMachine):
        sm.apply_transition(ACIDTransition.A1)
        sm.apply_transition(ACIDTransition.A2)
        result = sm.apply_transition(ACIDTransition.A3)
        assert result == ACIDState.COMMIT

    def test_a4_commit_to_ack_replica(self, sm: ACIDStateMachine):
        sm.apply_transition(ACIDTransition.A1)
        sm.apply_transition(ACIDTransition.A2)
        sm.apply_transition(ACIDTransition.A3)
        result = sm.apply_transition(ACIDTransition.A4)
        assert result == ACIDState.ACK_REPLICA

    def test_a5_commit_to_rollback(self, sm: ACIDStateMachine):
        sm.apply_transition(ACIDTransition.A1)
        sm.apply_transition(ACIDTransition.A2)
        sm.apply_transition(ACIDTransition.A3)
        result = sm.apply_transition(ACIDTransition.A5)
        assert result == ACIDState.ROLLBACK

    def test_a7_validation_to_rollback(self, sm: ACIDStateMachine):
        sm.apply_transition(ACIDTransition.A1)
        result = sm.apply_transition(ACIDTransition.A7)
        assert result == ACIDState.ROLLBACK

    def test_a8_ack_replica_to_rollback(self, sm: ACIDStateMachine):
        sm.apply_transition(ACIDTransition.A1)
        sm.apply_transition(ACIDTransition.A2)
        sm.apply_transition(ACIDTransition.A3)
        sm.apply_transition(ACIDTransition.A4)
        result = sm.apply_transition(ACIDTransition.A8)
        assert result == ACIDState.ROLLBACK

    def test_a6_deadlock_to_tx_start(self, sm: ACIDStateMachine):
        sm.apply_transition(ACIDTransition.A1)
        sm.apply_transition(ACIDTransition.A2)
        sm.apply_transition(ACIDTransition.A3)
        sm.apply_transition(ACIDTransition.A5)
        # Force DEADLOCK state (normally reached via guard logic)
        sm._current_state = ACIDState.DEADLOCK
        result = sm.apply_transition(ACIDTransition.A6)
        assert result == ACIDState.TX_START


# ── TestInvalidTransitions (4 tests) ────────────────────────────────────────


class TestInvalidTransitions:
    def test_cannot_commit_from_validation(self, sm: ACIDStateMachine):
        sm.apply_transition(ACIDTransition.A1)
        with pytest.raises(ValueError, match="Invalid transition"):
            sm.apply_transition(ACIDTransition.A3)

    def test_cannot_ack_from_partition_routing(self, sm: ACIDStateMachine):
        sm.apply_transition(ACIDTransition.A1)
        sm.apply_transition(ACIDTransition.A2)
        with pytest.raises(ValueError, match="Invalid transition"):
            sm.apply_transition(ACIDTransition.A4)

    def test_cannot_rollback_from_tx_start(self, sm: ACIDStateMachine):
        with pytest.raises(ValueError, match="Invalid transition"):
            sm.apply_transition(ACIDTransition.A5)

    def test_cannot_transition_from_rollback(self, sm: ACIDStateMachine):
        sm.apply_transition(ACIDTransition.A1)
        sm.apply_transition(ACIDTransition.A7)
        with pytest.raises(ValueError, match="Invalid transition"):
            sm.apply_transition(ACIDTransition.A1)


# ── TestGuardG1 (tx initiation) ─────────────────────────────────────────────


class TestGuardG1:
    def test_passes_with_all_conditions(self, sm: ACIDStateMachine):
        r = sm.guard_tx_initiated(connection_acquired=True, pool_has_room=True, data_trace_id_provided=True)
        assert r.allowed

    def test_blocks_pool_exhausted(self, sm: ACIDStateMachine):
        r = sm.guard_tx_initiated(False, True, True)
        assert not r.allowed and "pool exhausted" in r.reason

    def test_blocks_no_room(self, sm: ACIDStateMachine):
        r = sm.guard_tx_initiated(True, False, True)
        assert not r.allowed and "queue and wait" in r.reason

    def test_blocks_missing_trace_id(self, sm: ACIDStateMachine):
        r = sm.guard_tx_initiated(True, True, False)
        assert not r.allowed and "data_trace_id" in r.reason


# ── TestGuardG2 (isolation level) ───────────────────────────────────────────


class TestGuardG2:
    def test_passes_with_isolation_set(self, sm: ACIDStateMachine):
        r = sm.guard_isolation_level("SERIALIZABLE", True, True)
        assert r.allowed

    def test_blocks_missing_isolation(self, sm: ACIDStateMachine):
        r = sm.guard_isolation_level(None, True, True)
        assert not r.allowed and "isolation not set" in r.reason

    def test_blocks_insufficient_isolation(self, sm: ACIDStateMachine):
        r = sm.guard_isolation_level("READ_COMMITTED", False, True)
        assert not r.allowed and "insufficient" in r.reason

    def test_blocks_unverified_partition_key(self, sm: ACIDStateMachine):
        r = sm.guard_isolation_level("SERIALIZABLE", True, False)
        assert not r.allowed and "partition key unverified" in r.reason


# ── TestGuardG3 (partition key) ─────────────────────────────────────────────


class TestGuardG3:
    def test_passes_valid_key(self, sm: ACIDStateMachine):
        r = sm.guard_partition_key(True, True, True)
        assert r.allowed

    def test_blocks_invalid_key(self, sm: ACIDStateMachine):
        r = sm.guard_partition_key(False, True, True)
        assert not r.allowed and "invalid partition key" in r.reason

    def test_blocks_no_partition(self, sm: ACIDStateMachine):
        r = sm.guard_partition_key(True, False, True)
        assert not r.allowed and "no matching partition" in r.reason

    def test_blocks_routing_mismatch(self, sm: ACIDStateMachine):
        r = sm.guard_partition_key(True, True, False)
        assert not r.allowed and "routing mismatch" in r.reason


# ── TestGuardG4 (quorum ack) ────────────────────────────────────────────────


class TestGuardG4:
    def test_passes_majority_ack(self, sm: ACIDStateMachine):
        r = sm.guard_quorum_ack(3, 5, True, True)
        assert r.allowed

    def test_blocks_insufficient_acks(self, sm: ACIDStateMachine):
        r = sm.guard_quorum_ack(1, 5, True, True)
        assert not r.allowed and "insufficient acks" in r.reason

    def test_blocks_mode_not_met(self, sm: ACIDStateMachine):
        r = sm.guard_quorum_ack(3, 5, False, True)
        assert not r.allowed and "mode not satisfied" in r.reason

    def test_blocks_ack_timeout(self, sm: ACIDStateMachine):
        r = sm.guard_quorum_ack(3, 5, True, False)
        assert not r.allowed and "ack timeout" in r.reason


# ── TestGuardG5 (commit failed) ─────────────────────────────────────────────


class TestGuardG5:
    def test_passes_no_errors(self, sm: ACIDStateMachine):
        r = sm.guard_commit_failed(False, False, False)
        assert r.allowed

    def test_blocks_query_error(self, sm: ACIDStateMachine):
        r = sm.guard_commit_failed(True, False, False)
        assert not r.allowed and "query error" in r.reason

    def test_blocks_constraint_violation(self, sm: ACIDStateMachine):
        r = sm.guard_commit_failed(False, True, False)
        assert not r.allowed and "constraint violation" in r.reason

    def test_blocks_timeout(self, sm: ACIDStateMachine):
        r = sm.guard_commit_failed(False, False, True)
        assert not r.allowed and "timeout" in r.reason


# ── TestGuardG6 (deadlock retry) ────────────────────────────────────────────


class TestGuardG6:
    def test_passes_retry_valid(self, sm: ACIDStateMachine):
        r = sm.guard_deadlock_retry("tx1", 1, 3, True, True)
        assert r.allowed

    def test_blocks_max_retries(self, sm: ACIDStateMachine):
        r = sm.guard_deadlock_retry("tx1", 3, 3, True, True)
        assert not r.allowed and "max retries" in r.reason

    def test_blocks_backoff_not_waited(self, sm: ACIDStateMachine):
        r = sm.guard_deadlock_retry("tx1", 1, 3, False, True)
        assert not r.allowed and "too soon" in r.reason

    def test_not_triggered_no_deadlock(self, sm: ACIDStateMachine):
        r = sm.guard_deadlock_retry("tx1", 1, 3, True, False)
        assert not r.allowed and "not a deadlock" in r.reason


# ── TestGuardG7 (validation failed) ─────────────────────────────────────────


class TestGuardG7:
    def test_passes_all_valid(self, sm: ACIDStateMachine):
        r = sm.guard_validation_failed(False, False, False)
        assert r.allowed

    def test_triggers_invalid_isolation(self, sm: ACIDStateMachine):
        r = sm.guard_validation_failed(True, False, False)
        assert not r.allowed and "isolation level" in r.reason

    def test_triggers_missing_partition_key(self, sm: ACIDStateMachine):
        r = sm.guard_validation_failed(False, True, False)
        assert not r.allowed and "partition key" in r.reason

    def test_triggers_missing_trace_id(self, sm: ACIDStateMachine):
        r = sm.guard_validation_failed(False, False, True)
        assert not r.allowed and "data_trace_id" in r.reason


# ── TestGuardG8 (replica failed) ────────────────────────────────────────────


class TestGuardG8:
    def test_passes_no_errors(self, sm: ACIDStateMachine):
        r = sm.guard_replica_failed(False, False, True, False)
        assert r.allowed

    def test_triggers_replica_nack(self, sm: ACIDStateMachine):
        r = sm.guard_replica_failed(True, False, True, False)
        assert not r.allowed and "replica nack" in r.reason

    def test_blocks_timeout_no_fallback(self, sm: ACIDStateMachine):
        r = sm.guard_replica_failed(False, True, False, False)
        assert not r.allowed and "without fallback" in r.reason

    def test_blocks_force_commit(self, sm: ACIDStateMachine):
        r = sm.guard_replica_failed(False, False, True, True)
        assert not r.allowed and "no force commit" in r.reason


# ── TestDeterministicMigrationGuard ─────────────────────────────────────────


class TestDeterministicMigrationGuard:
    def test_same_snapshot_same_hash(self, sm: ACIDStateMachine):
        data = {"table": "test", "rows": [{"id": 1, "name": "x"}]}
        h1 = sm.compute_snapshot_hash(data)
        h2 = sm.compute_snapshot_hash(data)
        assert h1 == h2

    def test_different_snapshot_different_hash(self, sm: ACIDStateMachine):
        d1 = {"table": "test", "rows": [{"id": 1}]}
        d2 = {"table": "test", "rows": [{"id": 2}]}
        assert sm.compute_snapshot_hash(d1) != sm.compute_snapshot_hash(d2)

    def test_migration_passes(self, sm: ACIDStateMachine):
        h = sm.compute_snapshot_hash({"data": "test"})
        mh = sm.compute_mapping_hash([{"source": "a", "target": "b"}])
        r = sm.guard_migration_deterministic(h, h, mh, mh, 100, 100)
        assert r.allowed

    def test_migration_blocks_checksum(self, sm: ACIDStateMachine):
        r = sm.guard_migration_deterministic("abc", "def", "h1", "h1", 100, 100)
        assert not r.allowed and "snapshot hash mismatch" in r.reason

    def test_migration_blocks_row_count(self, sm: ACIDStateMachine):
        h = sm.compute_snapshot_hash({"data": "test"})
        mh = sm.compute_mapping_hash([])
        r = sm.guard_migration_deterministic(h, h, mh, mh, 100, 50)
        assert not r.allowed and "row count drift" in r.reason

    def test_same_mapping_same_hash(self, sm: ACIDStateMachine):
        rules = [{"source": "x", "target": "y", "transform": "identity"}]
        h1 = sm.compute_mapping_hash(rules)
        h2 = sm.compute_mapping_hash(rules)
        assert h1 == h2


# ── TestCompactionGuard ─────────────────────────────────────────────────────


class TestCompactionGuard:
    def test_passes_conditions_met(self, sm: ACIDStateMachine):
        r = sm.guard_compaction_allowed(100.0, 50.0, True, True)
        assert r.allowed

    def test_blocks_retention_not_met(self, sm: ACIDStateMachine):
        r = sm.guard_compaction_allowed(30.0, 50.0, True, True)
        assert not r.allowed and "retention" in r.reason

    def test_blocks_segment_in_use(self, sm: ACIDStateMachine):
        r = sm.guard_compaction_allowed(100.0, 50.0, False, True)
        assert not r.allowed and "segment in use" in r.reason

    def test_blocks_corruption(self, sm: ACIDStateMachine):
        r = sm.guard_compaction_allowed(100.0, 50.0, True, False)
        assert not r.allowed and "corruption" in r.reason


# ── TestTransitionHistory ───────────────────────────────────────────────────


class TestTransitionHistory:
    def test_records_all_transitions(self, sm: ACIDStateMachine):
        sm.apply_transition(ACIDTransition.A1)
        sm.apply_transition(ACIDTransition.A2)
        history = sm.transition_history
        assert len(history) == 2
        assert history[0]["transition"] == "a1"
        assert history[1]["transition"] == "a2"

    def test_reset_clears(self, sm: ACIDStateMachine):
        sm.apply_transition(ACIDTransition.A1)
        sm.reset()
        assert sm.current_state == ACIDState.TX_START
        assert len(sm.transition_history) == 0
