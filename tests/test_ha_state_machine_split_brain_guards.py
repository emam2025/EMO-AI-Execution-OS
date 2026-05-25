"""Phase I1 — HA State Machine & Split-Brain Guard Tests.  # LAW-20 LAW-21 LAW-22 RULE-1 RULE-3 RULE-4 RULE-5

Tests the 5-state HA lifecycle machine with all 9 transitions (H1–H9)
and 5 Split-Brain Guards (S1–S5). Verifies that quorum, lease, checksum,
partition, and isolation invariants are enforced.

Ref: Canon LAW 20, LAW 21, LAW 22
Ref: Canon RULE 1, RULE 3, RULE 4, RULE 5
Ref: artifacts/design/i1/03_ha_failover_machine.md
"""

from __future__ import annotations

import pytest

from core.runtime.infra.ha_state_machine import (
    HAStateMachine,
    HAState,
    Transition,
    GuardianResult,
)


# ── Test Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture
def sm() -> HAStateMachine:
    return HAStateMachine()


# ── TestStateMachineTransitions (9 tests for H1–H9) ─────────────────────────


class TestStateMachineTransitions:
    """Tests all 9 state transitions (H1–H9)."""

    def test_h1_follower_to_candidate(self, sm: HAStateMachine):
        assert sm.current_state == HAState.FOLLOWER
        result = sm.apply_transition(Transition.H1)
        assert result == HAState.CANDIDATE

    def test_h2_candidate_to_leader(self, sm: HAStateMachine):
        sm.apply_transition(Transition.H1)
        result = sm.apply_transition(Transition.H2)
        assert result == HAState.LEADER

    def test_h3_leader_to_recovering(self, sm: HAStateMachine):
        sm.apply_transition(Transition.H1)
        sm.apply_transition(Transition.H2)
        result = sm.apply_transition(Transition.H3)
        assert result == HAState.RECOVERING

    def test_h4_leader_to_follower(self, sm: HAStateMachine):
        sm.apply_transition(Transition.H1)
        sm.apply_transition(Transition.H2)
        result = sm.apply_transition(Transition.H4)
        assert result == HAState.FOLLOWER

    def test_h5_leader_to_isolated(self, sm: HAStateMachine):
        sm.apply_transition(Transition.H1)
        sm.apply_transition(Transition.H2)
        result = sm.apply_transition(Transition.H5)
        assert result == HAState.ISOLATED

    def test_h6_isolated_to_candidate(self, sm: HAStateMachine):
        sm.apply_transition(Transition.H1)
        sm.apply_transition(Transition.H2)
        sm.apply_transition(Transition.H5)
        result = sm.apply_transition(Transition.H6)
        assert result == HAState.CANDIDATE

    def test_h7_recovering_to_follower(self, sm: HAStateMachine):
        sm.apply_transition(Transition.H1)
        sm.apply_transition(Transition.H2)
        sm.apply_transition(Transition.H3)
        result = sm.apply_transition(Transition.H7)
        assert result == HAState.FOLLOWER

    def test_h8_recovering_to_isolated(self, sm: HAStateMachine):
        sm.apply_transition(Transition.H1)
        sm.apply_transition(Transition.H2)
        sm.apply_transition(Transition.H3)
        result = sm.apply_transition(Transition.H8)
        assert result == HAState.ISOLATED

    def test_h9_follower_to_isolated(self, sm: HAStateMachine):
        assert sm.current_state == HAState.FOLLOWER
        result = sm.apply_transition(Transition.H9)
        assert result == HAState.ISOLATED


# ── TestInvalidTransitions (5 tests) ────────────────────────────────────────


class TestInvalidTransitions:
    def test_cannot_transition_from_leader_to_candidate(self, sm: HAStateMachine):
        sm.apply_transition(Transition.H1)  # -> CANDIDATE
        sm.apply_transition(Transition.H2)  # -> LEADER
        with pytest.raises(ValueError, match="Invalid transition"):
            sm.apply_transition(Transition.H1)  # H1 not valid from LEADER

    def test_cannot_transition_from_follower_to_leader(self, sm: HAStateMachine):
        with pytest.raises(ValueError, match="Invalid transition"):
            sm.apply_transition(Transition.H2)  # H2 not valid from FOLLOWER

    def test_cannot_transition_from_candidate_to_recovering(self, sm: HAStateMachine):
        sm.apply_transition(Transition.H1)  # -> CANDIDATE
        with pytest.raises(ValueError, match="Invalid transition"):
            sm.apply_transition(Transition.H3)  # H3 not valid from CANDIDATE

    def test_cannot_transition_from_isolated_to_leader(self, sm: HAStateMachine):
        sm.apply_transition(Transition.H1)
        sm.apply_transition(Transition.H2)
        sm.apply_transition(Transition.H5)  # -> ISOLATED
        with pytest.raises(ValueError, match="Invalid transition"):
            sm.apply_transition(Transition.H2)  # H2 not valid from ISOLATED

    def test_cannot_transition_from_recovering_to_leader(self, sm: HAStateMachine):
        sm.apply_transition(Transition.H1)
        sm.apply_transition(Transition.H2)
        sm.apply_transition(Transition.H3)  # -> RECOVERING
        with pytest.raises(ValueError, match="Invalid transition"):
            sm.apply_transition(Transition.H2)  # H2 not valid from RECOVERING


# ── TestSplitBrainGuardS1 (quorum election) ─────────────────────────────────


class TestSplitBrainGuardS1:
    """S1 — Quorum Election Guard. Prevents two leaders elected concurrently."""

    def test_passes_with_sufficient_quorum(self, sm: HAStateMachine):
        result = sm.guard_quorum_election(
            quorum_votes=4, total_nodes=5, election_term=2,
            last_known_term=1, no_other_leader_advertised=True,
        )
        assert result.allowed

    def test_blocks_insufficient_quorum(self, sm: HAStateMachine):
        result = sm.guard_quorum_election(
            quorum_votes=2, total_nodes=5, election_term=2,
            last_known_term=1, no_other_leader_advertised=True,
        )
        assert not result.allowed
        assert "insufficient quorum" in result.reason

    def test_blocks_stale_term(self, sm: HAStateMachine):
        result = sm.guard_quorum_election(
            quorum_votes=4, total_nodes=5, election_term=1,
            last_known_term=2, no_other_leader_advertised=True,
        )
        assert not result.allowed
        assert "stale election term" in result.reason

    def test_blocks_split_brain_detected(self, sm: HAStateMachine):
        result = sm.guard_quorum_election(
            quorum_votes=4, total_nodes=5, election_term=2,
            last_known_term=1, no_other_leader_advertised=False,
        )
        assert not result.allowed
        assert "split brain detected" in result.reason

    def test_ties_do_not_constitute_quorum(self, sm: HAStateMachine):
        result = sm.guard_quorum_election(
            quorum_votes=2, total_nodes=4, election_term=2,
            last_known_term=1, no_other_leader_advertised=True,
        )
        assert not result.allowed  # 2 <= 4/2


# ── TestSplitBrainGuardS2 (lease expiry) ────────────────────────────────────


class TestSplitBrainGuardS2:
    """S2 — Lease Expiry Guard. Prevents premature leader election."""

    def test_passes_lease_truly_expired(self, sm: HAStateMachine):
        result = sm.guard_lease_expired(
            leader_heartbeat_age=60.0, lease_timeout_sec=30.0,
            nodes_reporting_missing_count=4, total_nodes=5,
            lease_holder="other", known_leader="leader1",
        )
        assert result.allowed

    def test_blocks_when_leader_still_alive(self, sm: HAStateMachine):
        result = sm.guard_lease_expired(
            leader_heartbeat_age=20.0, lease_timeout_sec=30.0,
            nodes_reporting_missing_count=1, total_nodes=5,
            lease_holder="other", known_leader="leader1",
        )
        assert not result.allowed
        assert "leader still alive" in result.reason

    def test_blocks_insufficient_confirmation(self, sm: HAStateMachine):
        result = sm.guard_lease_expired(
            leader_heartbeat_age=60.0, lease_timeout_sec=30.0,
            nodes_reporting_missing_count=1, total_nodes=5,
            lease_holder="other", known_leader="leader1",
        )
        assert not result.allowed
        assert "insufficient confirmation" in result.reason

    def test_blocks_lease_holder_matches_leader(self, sm: HAStateMachine):
        result = sm.guard_lease_expired(
            leader_heartbeat_age=60.0, lease_timeout_sec=30.0,
            nodes_reporting_missing_count=4, total_nodes=5,
            lease_holder="leader1", known_leader="leader1",
        )
        assert not result.allowed
        assert "lease holder matches" in result.reason


# ── TestSplitBrainGuardS3 (snapshot verification) ───────────────────────────


class TestSplitBrainGuardS3:
    """S3 — Snapshot Verification Guard. Prevents corrupted/stale state sync."""

    def test_passes_with_valid_snapshot(self, sm: HAStateMachine):
        result = sm.guard_snapshot_verified(
            snapshot_hash="abc123", source_node_hash="abc123",
            snapshot_term=5, last_committed_term=4,
            delta_log_applied_up_to=100, source_commit_index=100,
        )
        assert result.allowed

    def test_blocks_checksum_mismatch(self, sm: HAStateMachine):
        result = sm.guard_snapshot_verified(
            snapshot_hash="abc123", source_node_hash="def456",
            snapshot_term=5, last_committed_term=4,
            delta_log_applied_up_to=100, source_commit_index=100,
        )
        assert not result.allowed
        assert "checksum mismatch" in result.reason

    def test_blocks_stale_snapshot(self, sm: HAStateMachine):
        result = sm.guard_snapshot_verified(
            snapshot_hash="abc123", source_node_hash="abc123",
            snapshot_term=3, last_committed_term=4,
            delta_log_applied_up_to=100, source_commit_index=100,
        )
        assert not result.allowed
        assert "stale snapshot" in result.reason

    def test_blocks_missing_deltas(self, sm: HAStateMachine):
        result = sm.guard_snapshot_verified(
            snapshot_hash="abc123", source_node_hash="abc123",
            snapshot_term=5, last_committed_term=4,
            delta_log_applied_up_to=80, source_commit_index=100,
        )
        assert not result.allowed
        assert "missing deltas" in result.reason


# ── TestSplitBrainGuardS4 (network partition) ───────────────────────────────


class TestSplitBrainGuardS4:
    """S4 — Network Partition Guard. Prevents leader operating without quorum."""

    def test_passes_partition_exceeded(self, sm: HAStateMachine):
        result = sm.guard_network_partition(
            quorum_lost_interval=60.0, max_partition_sec=30.0,
            leader_can_reach=1, quorum_minimum=3,
            lease_remaining=0.0,
        )
        assert result.allowed

    def test_blocks_within_tolerance(self, sm: HAStateMachine):
        result = sm.guard_network_partition(
            quorum_lost_interval=20.0, max_partition_sec=30.0,
            leader_can_reach=1, quorum_minimum=3,
            lease_remaining=0.0,
        )
        assert not result.allowed
        assert "within tolerance" in result.reason

    def test_blocks_still_has_quorum(self, sm: HAStateMachine):
        result = sm.guard_network_partition(
            quorum_lost_interval=60.0, max_partition_sec=30.0,
            leader_can_reach=3, quorum_minimum=3,
            lease_remaining=0.0,
        )
        assert not result.allowed
        assert "still has quorum" in result.reason

    def test_blocks_lease_still_valid(self, sm: HAStateMachine):
        result = sm.guard_network_partition(
            quorum_lost_interval=60.0, max_partition_sec=30.0,
            leader_can_reach=1, quorum_minimum=3,
            lease_remaining=10.0,
        )
        assert not result.allowed
        assert "lease still valid" in result.reason


# ── TestSplitBrainGuardS5 (follower isolation) ──────────────────────────────


class TestSplitBrainGuardS5:
    """S5 — Follower Isolation Guard. Prevents follower operating partitioned."""

    def test_passes_follower_truly_isolated(self, sm: HAStateMachine):
        result = sm.guard_follower_isolation(
            follower_cannot_reach_leader=True, cannot_reach_quorum=True,
            leader_lease_valid=True, follower_has_uncommitted_log=False,
        )
        assert result.allowed

    def test_blocks_if_can_reach_leader_or_quorum(self, sm: HAStateMachine):
        result = sm.guard_follower_isolation(
            follower_cannot_reach_leader=False, cannot_reach_quorum=False,
            leader_lease_valid=True, follower_has_uncommitted_log=False,
        )
        assert not result.allowed
        assert "can still reach leader or quorum" in result.reason

    def test_blocks_if_leader_also_isolated(self, sm: HAStateMachine):
        result = sm.guard_follower_isolation(
            follower_cannot_reach_leader=True, cannot_reach_quorum=True,
            leader_lease_valid=False, follower_has_uncommitted_log=False,
        )
        assert not result.allowed
        assert "trigger election instead" in result.reason

    def test_blocks_if_uncommitted_log(self, sm: HAStateMachine):
        result = sm.guard_follower_isolation(
            follower_cannot_reach_leader=True, cannot_reach_quorum=True,
            leader_lease_valid=True, follower_has_uncommitted_log=True,
        )
        assert not result.allowed
        assert "data loss risk" in result.reason


# ── TestDeterministicRolloutGuard ───────────────────────────────────────────


class TestDeterministicRolloutGuard:
    """RULE 1: Same manifest → same hash deterministically."""

    def test_same_manifest_produces_same_hash(self, sm: HAStateMachine):
        manifest = {"runtime_version": "v1.0.0", "worker_pods": 5, "namespace": "emo-test"}
        h1 = sm.compute_manifest_hash(manifest)
        h2 = sm.compute_manifest_hash(manifest)
        assert h1 == h2

    def test_different_manifest_produces_different_hash(self, sm: HAStateMachine):
        m1 = {"runtime_version": "v1.0.0", "worker_pods": 5, "namespace": "emo-test"}
        m2 = {"runtime_version": "v1.0.1", "worker_pods": 5, "namespace": "emo-test"}
        assert sm.compute_manifest_hash(m1) != sm.compute_manifest_hash(m2)

    def test_hash_match_passes(self, sm: HAStateMachine):
        manifest = {"runtime_version": "v1.0.0", "worker_pods": 3, "namespace": "emo-test"}
        h = sm.compute_manifest_hash(manifest)
        result = sm.guard_deterministic_hash_match(manifest, h)
        assert result.allowed

    def test_hash_mismatch_blocks(self, sm: HAStateMachine):
        manifest = {"runtime_version": "v1.0.0", "worker_pods": 3, "namespace": "emo-test"}
        result = sm.guard_deterministic_hash_match(manifest, "wrong_hash")
        assert not result.allowed
        assert "hash mismatch" in result.reason

    def test_manifest_with_health_checks_deterministic(self, sm: HAStateMachine):
        m1 = {"runtime_version": "v1", "worker_pods": 3, "namespace": "test",
              "health_checks": [{"path": "/healthz", "port": 8080}, {"path": "/readyz", "port": 8081}]}
        m2 = {"runtime_version": "v1", "worker_pods": 3, "namespace": "test",
              "health_checks": [{"path": "/readyz", "port": 8081}, {"path": "/healthz", "port": 8080}]}
        h1 = sm.compute_manifest_hash(m1)
        h2 = sm.compute_manifest_hash(m2)
        assert h1 == h2  # sorted keys ensure determinism


# ── TestTransitionHistory ───────────────────────────────────────────────────


class TestTransitionHistory:
    def test_records_all_transitions(self, sm: HAStateMachine):
        sm.apply_transition(Transition.H1)
        sm.apply_transition(Transition.H2)
        history = sm.transition_history
        assert len(history) == 2
        assert history[0]["transition"] == "h1"
        assert history[1]["transition"] == "h2"

    def test_reset_clears_history(self, sm: HAStateMachine):
        sm.apply_transition(Transition.H1)
        sm.reset()
        assert sm.current_state == HAState.FOLLOWER
        assert len(sm.transition_history) == 0
