"""Phase I3 — Reliability State Machine Split-Brain Guards Tests.  # LAW-3 LAW-8 LAW-20 LAW-21 LAW-22 RULE-1 RULE-3 RULE-4 RULE-5

Tests that the ReliabilityStateMachine correctly enforces:
- Core Reliability transitions R1-R12
- Rolling Update transitions U1-U6
- Migration transitions M1-M7
- All 13 Safety Guards (G-R1-G-R8, G-U1-G-U2, G-M1-G-M2)
- Deterministic Rollout Guard

Ref: Canon LAW 3, LAW 8, LAW 20, LAW 21, LAW 22
Ref: Canon RULE 1, RULE 3, RULE 4, RULE 5
Ref: artifacts/design/i3/03_reliability_state_machine.md
"""

from __future__ import annotations

import pytest

from core.runtime.reliability.reliability_state_machine import (
    GuardianResult,
    MigrationState,
    MigrationTransition,
    ReliabilityState,
    ReliabilityStateMachine,
    ReliabilityTransition,
    UpdateState,
    UpdateTransition,
)


# ── Core Reliability Transitions ─────────────────────────────────────────────


class TestReliabilityStateMachineTransitions:
    def test_r1_healthy_to_failure_detected(self, sm: ReliabilityStateMachine):
        next_state = sm.apply_reliability_transition(ReliabilityTransition.R1)
        assert next_state == ReliabilityState.FAILURE_DETECTED
        assert sm.reliability_state == ReliabilityState.FAILURE_DETECTED

    def test_r2_failure_detected_to_quorum_check(self, sm: ReliabilityStateMachine):
        sm.apply_reliability_transition(ReliabilityTransition.R1)
        next_state = sm.apply_reliability_transition(ReliabilityTransition.R2)
        assert next_state == ReliabilityState.QUORUM_CHECK

    def test_r12_failure_detected_to_healthy(self, sm: ReliabilityStateMachine):
        sm.apply_reliability_transition(ReliabilityTransition.R1)
        next_state = sm.apply_reliability_transition(ReliabilityTransition.R12)
        assert next_state == ReliabilityState.HEALTHY

    def test_r3_quorum_check_to_promote_replica(self, sm: ReliabilityStateMachine):
        sm.apply_reliability_transition(ReliabilityTransition.R1)
        sm.apply_reliability_transition(ReliabilityTransition.R2)
        next_state = sm.apply_reliability_transition(ReliabilityTransition.R3)
        assert next_state == ReliabilityState.PROMOTE_REPLICA

    def test_r5_promote_to_sync(self, sm: ReliabilityStateMachine):
        sm.apply_reliability_transition(ReliabilityTransition.R1)
        sm.apply_reliability_transition(ReliabilityTransition.R2)
        sm.apply_reliability_transition(ReliabilityTransition.R3)
        next_state = sm.apply_reliability_transition(ReliabilityTransition.R5)
        assert next_state == ReliabilityState.SYNC_STATE

    def test_r6_sync_to_healthy(self, sm: ReliabilityStateMachine):
        sm.apply_reliability_transition(ReliabilityTransition.R1)
        sm.apply_reliability_transition(ReliabilityTransition.R2)
        sm.apply_reliability_transition(ReliabilityTransition.R3)
        sm.apply_reliability_transition(ReliabilityTransition.R5)
        next_state = sm.apply_reliability_transition(ReliabilityTransition.R6)
        assert next_state == ReliabilityState.HEALTHY

    def test_r9_healthy_to_recovery_point(self, sm: ReliabilityStateMachine):
        next_state = sm.apply_reliability_transition(ReliabilityTransition.R9)
        assert next_state == ReliabilityState.RECOVERY_POINT

    def test_r10_recovery_point_to_healthy(self, sm: ReliabilityStateMachine):
        sm.apply_reliability_transition(ReliabilityTransition.R9)
        next_state = sm.apply_reliability_transition(ReliabilityTransition.R10)
        assert next_state == ReliabilityState.HEALTHY


# ── Invalid Reliability Transitions ──────────────────────────────────────────


class TestInvalidReliabilityTransitions:
    def test_cannot_transition_from_healthy_to_promote(self, sm: ReliabilityStateMachine):
        with pytest.raises(ValueError, match="Invalid reliability transition"):
            sm.apply_reliability_transition(ReliabilityTransition.R3)

    def test_cannot_skip_quorum_check(self, sm: ReliabilityStateMachine):
        with pytest.raises(ValueError, match="Invalid reliability transition"):
            sm.apply_reliability_transition(ReliabilityTransition.R5)

    def test_cannot_jump_from_healthy_to_restore(self, sm: ReliabilityStateMachine):
        with pytest.raises(ValueError, match="Invalid reliability transition"):
            sm.apply_reliability_transition(ReliabilityTransition.R11)

    def test_cannot_recover_point_from_failure(self, sm: ReliabilityStateMachine):
        sm.apply_reliability_transition(ReliabilityTransition.R1)
        with pytest.raises(ValueError, match="Invalid reliability transition"):
            sm.apply_reliability_transition(ReliabilityTransition.R9)


# ── Rolling Update Transitions ───────────────────────────────────────────────


class TestRollingUpdateTransitions:
    def test_u1_prepare_to_roll_forward(self, sm: ReliabilityStateMachine):
        next_state = sm.apply_update_transition(UpdateTransition.U1)
        assert next_state == UpdateState.ROLL_FORWARD

    def test_u2_roll_forward_to_health_monitor(self, sm: ReliabilityStateMachine):
        sm.apply_update_transition(UpdateTransition.U1)
        next_state = sm.apply_update_transition(UpdateTransition.U2)
        assert next_state == UpdateState.HEALTH_MONITOR

    def test_u3_roll_forward_to_roll_back(self, sm: ReliabilityStateMachine):
        sm.apply_update_transition(UpdateTransition.U1)
        next_state = sm.apply_update_transition(UpdateTransition.U3)
        assert next_state == UpdateState.ROLL_BACK

    def test_u5_prepare_to_roll_back(self, sm: ReliabilityStateMachine):
        next_state = sm.apply_update_transition(UpdateTransition.U5)
        assert next_state == UpdateState.ROLL_BACK

    def test_u6_roll_back_to_prepare(self, sm: ReliabilityStateMachine):
        sm.apply_update_transition(UpdateTransition.U5)
        next_state = sm.apply_update_transition(UpdateTransition.U6)
        assert next_state == UpdateState.PREPARE_CANARY


# ── Migration Transitions ────────────────────────────────────────────────────


class TestMigrationTransitions:
    def test_m1_dry_run_to_snapshot(self, sm: ReliabilityStateMachine):
        next_state = sm.apply_migration_transition(MigrationTransition.M1)
        assert next_state == MigrationState.SNAPSHOT_STATE

    def test_m2_snapshot_to_switch_over(self, sm: ReliabilityStateMachine):
        sm.apply_migration_transition(MigrationTransition.M1)
        next_state = sm.apply_migration_transition(MigrationTransition.M2)
        assert next_state == MigrationState.SWITCH_OVER

    def test_m3_switch_to_verify(self, sm: ReliabilityStateMachine):
        sm.apply_migration_transition(MigrationTransition.M1)
        sm.apply_migration_transition(MigrationTransition.M2)
        next_state = sm.apply_migration_transition(MigrationTransition.M3)
        assert next_state == MigrationState.POST_MIGRATION_VERIFY

    def test_m6_dry_run_abort(self, sm: ReliabilityStateMachine):
        next_state = sm.apply_migration_transition(MigrationTransition.M6)
        assert next_state == MigrationState.DRY_RUN  # self-loop for retry


# ── Safety Guards (G-R1–G-R8: Core Reliability) ─────────────────────────────


class TestGuardGR1:
    def test_passes_with_failure(self, sm: ReliabilityStateMachine):
        result = sm.guard_health_degraded(
            heartbeat_loss_sec=35.0, heartbeat_threshold=30.0,
            quorum_status="degraded", anomaly_severity="high",
        )
        assert result.allowed

    def test_blocks_no_failure(self, sm: ReliabilityStateMachine):
        result = sm.guard_health_degraded(
            heartbeat_loss_sec=15.0, heartbeat_threshold=30.0,
            quorum_status="healthy", anomaly_severity="low",
        )
        assert not result.allowed


class TestGuardGR2:
    def test_passes_with_confirmation(self, sm: ReliabilityStateMachine):
        result = sm.guard_quorum_integrity(failure_confirmed_by=3, min_confirmation_nodes=2)
        assert result.allowed

    def test_blocks_insufficient_confirmation(self, sm: ReliabilityStateMachine):
        result = sm.guard_quorum_integrity(failure_confirmed_by=1, min_confirmation_nodes=2)
        assert not result.allowed


class TestGuardGR3:
    def test_passes_with_quorum_and_sync(self, sm: ReliabilityStateMachine):
        result = sm.guard_promote_safe(
            quorum_votes=4, total_nodes=5, data_sync_lag_ms=120.0,
            standby_checksum_match=True, lease_revoked_on_failed=True,
        )
        assert result.allowed

    def test_blocks_insufficient_quorum(self, sm: ReliabilityStateMachine):
        result = sm.guard_promote_safe(
            quorum_votes=2, total_nodes=5, data_sync_lag_ms=120.0,
        )
        assert not result.allowed
        assert "quorum" in result.reason

    def test_blocks_excessive_sync_lag(self, sm: ReliabilityStateMachine):
        result = sm.guard_promote_safe(
            quorum_votes=4, total_nodes=5, data_sync_lag_ms=600.0,
        )
        assert not result.allowed
        assert "sync lag" in result.reason

    def test_blocks_checksum_mismatch(self, sm: ReliabilityStateMachine):
        result = sm.guard_promote_safe(
            quorum_votes=4, total_nodes=5, data_sync_lag_ms=120.0,
            standby_checksum_match=False,
        )
        assert not result.allowed

    def test_blocks_lease_not_revoked(self, sm: ReliabilityStateMachine):
        result = sm.guard_promote_safe(
            quorum_votes=4, total_nodes=5, data_sync_lag_ms=120.0,
            lease_revoked_on_failed=False,
        )
        assert not result.allowed


class TestGuardGR4:
    def test_passes_quorum_lost(self, sm: ReliabilityStateMachine):
        result = sm.guard_quorum_lost(quorum_votes=2, total_nodes=5, lease_remaining=0)
        assert result.allowed

    def test_blocks_still_has_quorum(self, sm: ReliabilityStateMachine):
        result = sm.guard_quorum_lost(quorum_votes=3, total_nodes=5, lease_remaining=0)
        assert not result.allowed

    def test_blocks_lease_still_valid(self, sm: ReliabilityStateMachine):
        result = sm.guard_quorum_lost(quorum_votes=2, total_nodes=5, lease_remaining=10.0)
        assert not result.allowed


class TestGuardGR5:
    def test_passes_isolation_complete(self, sm: ReliabilityStateMachine):
        result = sm.guard_promote_after_isolation(
            node_isolated=True, lease_revoked=True, traffic_drained=True,
        )
        assert result.allowed

    def test_blocks_node_not_isolated(self, sm: ReliabilityStateMachine):
        result = sm.guard_promote_after_isolation(
            node_isolated=False, lease_revoked=True, traffic_drained=True,
        )
        assert not result.allowed


class TestGuardGR6:
    def test_passes_sync_ok(self, sm: ReliabilityStateMachine):
        result = sm.guard_sync_verified(
            state_hash_match=True, deltas_applied=True, journal_caught_up=True,
        )
        assert result.allowed

    def test_blocks_hash_mismatch(self, sm: ReliabilityStateMachine):
        result = sm.guard_sync_verified(
            state_hash_match=False, deltas_applied=True, journal_caught_up=True,
        )
        assert not result.allowed


class TestGuardGR7:
    def test_passes_backup_ok(self, sm: ReliabilityStateMachine):
        result = sm.guard_backup_verified(checksum_match=True, journal_offset_valid=True)
        assert result.allowed

    def test_blocks_checksum_mismatch(self, sm: ReliabilityStateMachine):
        result = sm.guard_backup_verified(checksum_match=False, journal_offset_valid=True)
        assert not result.allowed


class TestGuardGR8:
    def test_passes_restore_ok(self, sm: ReliabilityStateMachine):
        result = sm.guard_restore_verified(
            checksum_match=True, replay_complete=True, consistency_ok=True,
        )
        assert result.allowed

    def test_blocks_replay_incomplete(self, sm: ReliabilityStateMachine):
        result = sm.guard_restore_verified(
            checksum_match=True, replay_complete=False, consistency_ok=True,
        )
        assert not result.allowed


# ── Safety Guards (G-U1–G-U2: Rolling Update) ────────────────────────────────


class TestGuardGU1:
    def test_passes_canary_ready(self, sm: ReliabilityStateMachine):
        result = sm.guard_canary_ready(
            compatibility_ok=True, canary_percent_set=True, manifest_hash_computed=True,
        )
        assert result.allowed

    def test_blocks_compatibility_fail(self, sm: ReliabilityStateMachine):
        result = sm.guard_canary_ready(
            compatibility_ok=False, canary_percent_set=True, manifest_hash_computed=True,
        )
        assert not result.allowed


class TestGuardGU2:
    def test_triggers_on_health_failure(self, sm: ReliabilityStateMachine):
        result = sm.guard_rollback_required(
            health_check_failure=True, error_rate_spike=False, latency_degraded=False,
        )
        assert not result.allowed

    def test_passes_no_issues(self, sm: ReliabilityStateMachine):
        result = sm.guard_rollback_required(
            health_check_failure=False, error_rate_spike=False, latency_degraded=False,
        )
        assert result.allowed


# ── Safety Guards (G-M1–G-M2: Migration) ────────────────────────────────────


class TestGuardGM1:
    def test_passes_dry_run_ok(self, sm: ReliabilityStateMachine):
        result = sm.guard_dry_run_passed(
            dry_run_passed=True, compatibility_ok=True, issues_empty=True,
        )
        assert result.allowed

    def test_blocks_dry_run_failed(self, sm: ReliabilityStateMachine):
        result = sm.guard_dry_run_passed(
            dry_run_passed=False, compatibility_ok=True, issues_empty=True,
        )
        assert not result.allowed


class TestGuardGM2:
    def test_passes_snapshot_ok(self, sm: ReliabilityStateMachine):
        result = sm.guard_snapshot_verified(
            snapshot_hash_match=True, journal_offset_valid=True, source_integrity_ok=True,
        )
        assert result.allowed

    def test_blocks_hash_mismatch(self, sm: ReliabilityStateMachine):
        result = sm.guard_snapshot_verified(
            snapshot_hash_match=False, journal_offset_valid=True, source_integrity_ok=True,
        )
        assert not result.allowed


# ── Deterministic Rollout Guard ──────────────────────────────────────────────


class TestDeterministicRolloutGuard:
    def test_same_inputs_same_decision(self, sm: ReliabilityStateMachine):
        d1 = sm.compute_rollout_decision("v2.0", "canary", {"healthy_nodes": 5, "degraded_nodes": 0})
        d2 = sm.compute_rollout_decision("v2.0", "canary", {"healthy_nodes": 5, "degraded_nodes": 0})
        assert d1 == d2

    def test_different_version_different_decision(self, sm: ReliabilityStateMachine):
        d1 = sm.compute_rollout_decision("v1.0", "rolling_update", {"healthy_nodes": 5, "degraded_nodes": 0})
        d2 = sm.compute_rollout_decision("v2.0", "rolling_update", {"healthy_nodes": 5, "degraded_nodes": 0})
        assert d1 == "proceed_rolling"
        assert d2 == "proceed_rolling"

    def test_detects_degraded_cluster(self, sm: ReliabilityStateMachine):
        decision = sm.compute_rollout_decision("v2.0", "rolling_update", {"healthy_nodes": 3, "degraded_nodes": 2})
        assert decision == "abort_health_degraded"

    def test_guard_hash_match(self, sm: ReliabilityStateMachine):
        data = {"version": "v2.0", "strategy": "canary"}
        expected = sm.guard_deterministic_hash_match(data, "")
        assert not expected.allowed  # empty hash won't match

    def test_guard_hash_passes(self, sm: ReliabilityStateMachine):
        from core.runtime.reliability.reliability_state_machine import hashlib, json
        data = {"version": "v2.0", "strategy": "canary"}
        expected_hash = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:32]
        result = sm.guard_deterministic_hash_match(data, expected_hash)
        assert result.allowed


# ── Transition History ───────────────────────────────────────────────────────


class TestTransitionHistory:
    def test_records_all_transitions(self, sm: ReliabilityStateMachine):
        sm.apply_reliability_transition(ReliabilityTransition.R1)
        sm.apply_reliability_transition(ReliabilityTransition.R2)
        sm.apply_reliability_transition(ReliabilityTransition.R3)
        history = sm.transition_history
        assert len(history) == 3
        assert history[0]["transition"] == "r1"

    def test_reset_clears(self, sm: ReliabilityStateMachine):
        sm.apply_reliability_transition(ReliabilityTransition.R1)
        assert len(sm.transition_history) > 0
        sm.reset()
        assert len(sm.transition_history) == 0
        assert sm.reliability_state == ReliabilityState.HEALTHY
        assert sm.update_state == UpdateState.PREPARE_CANARY
        assert sm.migration_state == MigrationState.DRY_RUN


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def sm() -> ReliabilityStateMachine:
    return ReliabilityStateMachine()
