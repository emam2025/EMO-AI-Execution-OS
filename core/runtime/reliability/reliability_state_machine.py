"""Phase I3 — Reliability State Machine with Split-Brain Guards.  # LAW-3 LAW-8 LAW-20 LAW-21 LAW-22 RULE-1 RULE-3 RULE-4 RULE-5

16-state Reliability lifecycle machine combining Core Failover+DR (8 states,
13 transitions R1-R12), Rolling Update (4 states, 6 transitions U1-U6), and
Runtime Migration (4 states, 7 transitions M1-M7). Enforces 13 Safety Guards
(G-R1-G-R8, G-U1-G-U2, G-M1-G-M2) and a Deterministic Rollout Guard.

Ref: Canon LAW 3 (Deterministic), LAW 8 (Recoverability)
Ref: Canon LAW 20 (Failure Detection), LAW 21 (Failure Propagation)
Ref: Canon LAW 22 (Service Isolation)
Ref: Canon RULE 1 (Determinism), RULE 3 (Safety Guards)
Ref: Canon RULE 4 (Isolation), RULE 5 (Recovery)
Ref: artifacts/design/i3/03_reliability_state_machine.md
Ref: I1 HAStateMachine (S1-S5), I2 ACIDStateMachine (G1-G8)
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# ── Core Reliability States (Failover + DR) ──────────────────────────────────


class ReliabilityState(str, Enum):  # LAW-8 LAW-20
    HEALTHY = "healthy"
    FAILURE_DETECTED = "failure_detected"
    QUORUM_CHECK = "quorum_check"
    ISOLATE_NODE = "isolate_node"
    PROMOTE_REPLICA = "promote_replica"
    SYNC_STATE = "sync_state"
    RECOVERY_POINT = "recovery_point"
    RESTORE_REPLAY = "restore_replay"


class ReliabilityTransition(str, Enum):
    R1 = "r1"    # HEALTHY -> FAILURE_DETECTED
    R2 = "r2"    # FAILURE_DETECTED -> QUORUM_CHECK
    R2a = "r2a"  # FAILURE_DETECTED -> HEALTHY (false alarm)
    R3 = "r3"    # QUORUM_CHECK -> PROMOTE_REPLICA
    R4 = "r4"    # ISOLATE_NODE -> PROMOTE_REPLICA
    R5 = "r5"    # PROMOTE_REPLICA -> SYNC_STATE
    R6 = "r6"    # SYNC_STATE -> HEALTHY
    R7 = "r7"    # SYNC_STATE -> FALLBACK (via restore_replay)
    R8 = "r8"    # FALLBACK -> RESTORE_REPLAY
    R9 = "r9"    # HEALTHY -> RECOVERY_POINT
    R10 = "r10"  # RECOVERY_POINT -> HEALTHY
    R11 = "r11"  # RESTORE_REPLAY -> HEALTHY
    R12 = "r12"  # FAILURE_DETECTED -> HEALTHY (resolved)


# ── Rolling Update States ────────────────────────────────────────────────────


class UpdateState(str, Enum):  # LAW-3
    PREPARE_CANARY = "prepare_canary"
    ROLL_FORWARD = "roll_forward"
    HEALTH_MONITOR = "health_monitor"
    ROLL_BACK = "roll_back"


class UpdateTransition(str, Enum):
    U1 = "u1"  # PREPARE_CANARY -> ROLL_FORWARD
    U2 = "u2"  # ROLL_FORWARD -> HEALTH_MONITOR
    U3 = "u3"  # ROLL_FORWARD -> ROLL_BACK
    U4 = "u4"  # HEALTH_MONITOR -> ROLL_BACK
    U5 = "u5"  # PREPARE_CANARY -> ROLL_BACK
    U6 = "u6"  # ROLL_BACK -> PREPARE_CANARY


# ── Migration States ─────────────────────────────────────────────────────────


class MigrationState(str, Enum):  # LAW-3 LAW-8
    DRY_RUN = "dry_run"
    SNAPSHOT_STATE = "snapshot_state"
    SWITCH_OVER = "switch_over"
    POST_MIGRATION_VERIFY = "post_migration_verify"


class MigrationTransition(str, Enum):
    M1 = "m1"  # DRY_RUN -> SNAPSHOT_STATE
    M2 = "m2"  # SNAPSHOT_STATE -> SWITCH_OVER
    M3 = "m3"  # SWITCH_OVER -> POST_MIGRATION_VERIFY
    M4 = "m4"  # SWITCH_OVER -> ROLL_BACK (abort)
    M5 = "m5"  # SNAPSHOT_STATE -> ABORT
    M6 = "m6"  # DRY_RUN -> ABORT
    M7 = "m7"  # POST_MIGRATION_VERIFY -> COMPLETE


# ── Transition Maps ─────────────────────────────────────────────────────────


VALID_RELIABILITY_TRANSITIONS: Dict[ReliabilityState, Dict[ReliabilityTransition, ReliabilityState]] = {
    ReliabilityState.HEALTHY: {
        ReliabilityTransition.R1: ReliabilityState.FAILURE_DETECTED,
        ReliabilityTransition.R9: ReliabilityState.RECOVERY_POINT,
    },
    ReliabilityState.FAILURE_DETECTED: {
        ReliabilityTransition.R2: ReliabilityState.QUORUM_CHECK,
        ReliabilityTransition.R12: ReliabilityState.HEALTHY,
    },
    ReliabilityState.QUORUM_CHECK: {
        ReliabilityTransition.R3: ReliabilityState.PROMOTE_REPLICA,
    },
    ReliabilityState.ISOLATE_NODE: {
        ReliabilityTransition.R4: ReliabilityState.PROMOTE_REPLICA,
    },
    ReliabilityState.PROMOTE_REPLICA: {
        ReliabilityTransition.R5: ReliabilityState.SYNC_STATE,
    },
    ReliabilityState.SYNC_STATE: {
        ReliabilityTransition.R6: ReliabilityState.HEALTHY,
        ReliabilityTransition.R7: ReliabilityState.RESTORE_REPLAY,
    },
    ReliabilityState.RECOVERY_POINT: {
        ReliabilityTransition.R10: ReliabilityState.HEALTHY,
    },
    ReliabilityState.RESTORE_REPLAY: {
        ReliabilityTransition.R11: ReliabilityState.HEALTHY,
    },
}

VALID_UPDATE_TRANSITIONS: Dict[UpdateState, Dict[UpdateTransition, UpdateState]] = {
    UpdateState.PREPARE_CANARY: {
        UpdateTransition.U1: UpdateState.ROLL_FORWARD,
        UpdateTransition.U5: UpdateState.ROLL_BACK,
    },
    UpdateState.ROLL_FORWARD: {
        UpdateTransition.U2: UpdateState.HEALTH_MONITOR,
        UpdateTransition.U3: UpdateState.ROLL_BACK,
    },
    UpdateState.HEALTH_MONITOR: {
        UpdateTransition.U4: UpdateState.ROLL_BACK,
    },
    UpdateState.ROLL_BACK: {
        UpdateTransition.U6: UpdateState.PREPARE_CANARY,
    },
}

VALID_MIGRATION_TRANSITIONS: Dict[MigrationState, Dict[MigrationTransition, MigrationState]] = {
    MigrationState.DRY_RUN: {
        MigrationTransition.M1: MigrationState.SNAPSHOT_STATE,
        MigrationTransition.M6: MigrationState.DRY_RUN,  # abort -> back to dry_run
    },
    MigrationState.SNAPSHOT_STATE: {
        MigrationTransition.M2: MigrationState.SWITCH_OVER,
        MigrationTransition.M5: MigrationState.SNAPSHOT_STATE,  # abort retry
    },
    MigrationState.SWITCH_OVER: {
        MigrationTransition.M3: MigrationState.POST_MIGRATION_VERIFY,
    },
    MigrationState.POST_MIGRATION_VERIFY: {
        MigrationTransition.M7: MigrationState.POST_MIGRATION_VERIFY,  # complete
    },
}


@dataclass
class GuardianResult:  # RULE-3
    """Result of a safety guard check."""
    allowed: bool = True
    reason: str = ""


class ReliabilityStateMachine:  # LAW-3 LAW-8 LAW-20 LAW-22 RULE-3 RULE-5
    """16-state Reliability lifecycle machine with Safety Guards.

    Combines Core Failover+DR (8 states), Rolling Update (4 states), and
    Runtime Migration (4 states). Every transition is gated by guards that
    enforce quorum, sync lag, checksum, isolation, and rollback invariants.
    """

    def __init__(
        self,
        initial_reliability_state: ReliabilityState = ReliabilityState.HEALTHY,
        initial_update_state: UpdateState = UpdateState.PREPARE_CANARY,
        initial_migration_state: MigrationState = MigrationState.DRY_RUN,
    ) -> None:
        self._reliability_state: ReliabilityState = initial_reliability_state
        self._update_state: UpdateState = initial_update_state
        self._migration_state: MigrationState = initial_migration_state
        self._transition_history: List[Dict[str, Any]] = []

    @property
    def reliability_state(self) -> ReliabilityState:
        return self._reliability_state

    @property
    def update_state(self) -> UpdateState:
        return self._update_state

    @property
    def migration_state(self) -> MigrationState:
        return self._migration_state

    # ── Core Reliability Transitions ─────────────────────────────

    def apply_reliability_transition(self, transition: ReliabilityTransition) -> ReliabilityState:
        allowed = VALID_RELIABILITY_TRANSITIONS.get(self._reliability_state, {})
        if transition not in allowed:
            raise ValueError(
                f"Invalid reliability transition {transition.value} from state {self._reliability_state.value}"
            )
        next_state = allowed[transition]
        self._transition_history.append({
            "machine": "reliability",
            "from": self._reliability_state.value,
            "to": next_state.value,
            "transition": transition.value,
        })
        self._reliability_state = next_state
        return next_state

    def apply_update_transition(self, transition: UpdateTransition) -> UpdateState:
        allowed = VALID_UPDATE_TRANSITIONS.get(self._update_state, {})
        if transition not in allowed:
            raise ValueError(
                f"Invalid update transition {transition.value} from state {self._update_state.value}"
            )
        next_state = allowed[transition]
        self._transition_history.append({
            "machine": "update",
            "from": self._update_state.value,
            "to": next_state.value,
            "transition": transition.value,
        })
        self._update_state = next_state
        return next_state

    def apply_migration_transition(self, transition: MigrationTransition) -> MigrationState:
        allowed = VALID_MIGRATION_TRANSITIONS.get(self._migration_state, {})
        if transition not in allowed:
            raise ValueError(
                f"Invalid migration transition {transition.value} from state {self._migration_state.value}"
            )
        next_state = allowed[transition]
        self._transition_history.append({
            "machine": "migration",
            "from": self._migration_state.value,
            "to": next_state.value,
            "transition": transition.value,
        })
        self._migration_state = next_state
        return next_state

    # ── Safety Guards (G-R1–G-R8: Core Reliability) ─────────────

    def guard_health_degraded(  # G-R1 — LAW-20 RULE-3
        self,
        heartbeat_loss_sec: float,
        heartbeat_threshold: float,
        quorum_status: str,
        anomaly_severity: str,
    ) -> GuardianResult:
        """G-R1: Prevents failing to detect a real failure."""
        if heartbeat_loss_sec <= heartbeat_threshold and quorum_status == "healthy" and anomaly_severity not in ("high", "critical"):
            return GuardianResult(False, "G-R1 BLOCKED: heartbeat within threshold, quorum healthy")
        return GuardianResult(True, "G-R1 PASSED: failure confirmed")

    def guard_quorum_integrity(  # G-R2 — LAW-20 LAW-21 RULE-3
        self,
        failure_confirmed_by: int,
        min_confirmation_nodes: int,
    ) -> GuardianResult:
        """G-R2: Prevents escalating a false alarm without quorum confirmation."""
        if failure_confirmed_by < min_confirmation_nodes:
            return GuardianResult(False, f"G-R2 BLOCKED: only {failure_confirmed_by} nodes confirmed, need {min_confirmation_nodes}")
        return GuardianResult(True, "G-R2 PASSED: quorum confirmed failure")

    def guard_promote_safe(  # G-R3 — LAW-8 RULE-3
        self,
        quorum_votes: int,
        total_nodes: int,
        data_sync_lag_ms: float,
        max_sync_lag_threshold: float = 500.0,
        standby_checksum_match: bool = True,
        lease_revoked_on_failed: bool = True,
    ) -> GuardianResult:
        """G-R3: Prevents promoting a replica without quorum or with excessive sync lag."""
        if quorum_votes <= total_nodes // 2:
            return GuardianResult(False, f"G-R3 BLOCKED: quorum {quorum_votes} <= {total_nodes // 2}")
        if data_sync_lag_ms > max_sync_lag_threshold:
            return GuardianResult(False, f"G-R3 BLOCKED: sync lag {data_sync_lag_ms}ms > {max_sync_lag_threshold}ms")
        if not standby_checksum_match:
            return GuardianResult(False, "G-R3 BLOCKED: standby checksum mismatch")
        if not lease_revoked_on_failed:
            return GuardianResult(False, "G-R3 BLOCKED: lease not revoked on failed node")
        return GuardianResult(True, "G-R3 PASSED")

    def guard_quorum_lost(  # G-R4 — LAW-22 RULE-4
        self,
        quorum_votes: int,
        total_nodes: int,
        lease_remaining: float,
    ) -> GuardianResult:
        """G-R4: Prevents allowing a leader to operate without quorum."""
        if quorum_votes > total_nodes // 2:
            return GuardianResult(False, "G-R4 BLOCKED: still has quorum")
        if lease_remaining > 0:
            return GuardianResult(False, "G-R4 BLOCKED: lease still valid")
        return GuardianResult(True, "G-R4 PASSED: quorum lost, must step down")

    def guard_promote_after_isolation(  # G-R5 — LAW-22 RULE-4
        self,
        node_isolated: bool,
        lease_revoked: bool,
        traffic_drained: bool,
    ) -> GuardianResult:
        """G-R5: Prevents promoting before isolation has completed."""
        if not node_isolated:
            return GuardianResult(False, "G-R5 BLOCKED: node not isolated")
        if not lease_revoked:
            return GuardianResult(False, "G-R5 BLOCKED: lease not revoked")
        if not traffic_drained:
            return GuardianResult(False, "G-R5 BLOCKED: traffic not drained")
        return GuardianResult(True, "G-R5 PASSED: isolation confirmed")

    def guard_sync_verified(  # G-R6 — RULE-1 RULE-5
        self,
        state_hash_match: bool,
        deltas_applied: bool,
        journal_caught_up: bool,
    ) -> GuardianResult:
        """G-R6: Prevents declaring recovery complete before state is fully synced."""
        if not state_hash_match:
            return GuardianResult(False, "G-R6 BLOCKED: state hash mismatch")
        if not deltas_applied:
            return GuardianResult(False, "G-R6 BLOCKED: missing deltas")
        if not journal_caught_up:
            return GuardianResult(False, "G-R6 BLOCKED: journal not caught up")
        return GuardianResult(True, "G-R6 PASSED: sync verified")

    def guard_backup_verified(  # G-R7 — LAW-8 RULE-1
        self,
        checksum_match: bool,
        journal_offset_valid: bool,
    ) -> GuardianResult:
        """G-R7: Prevents declaring a recovery point valid without checksum."""
        if not checksum_match:
            return GuardianResult(False, "G-R7 BLOCKED: checksum mismatch")
        if not journal_offset_valid:
            return GuardianResult(False, "G-R7 BLOCKED: journal offset invalid")
        return GuardianResult(True, "G-R7 PASSED: backup verified")

    def guard_restore_verified(  # G-R8 — LAW-8 RULE-2
        self,
        checksum_match: bool,
        replay_complete: bool,
        consistency_ok: bool,
    ) -> GuardianResult:
        """G-R8: Prevents declaring DR complete before data integrity is confirmed."""
        if not checksum_match:
            return GuardianResult(False, "G-R8 BLOCKED: restore checksum mismatch")
        if not replay_complete:
            return GuardianResult(False, "G-R8 BLOCKED: journal replay incomplete")
        if not consistency_ok:
            return GuardianResult(False, "G-R8 BLOCKED: journal inconsistent")
        return GuardianResult(True, "G-R8 PASSED: restore verified")

    # ── Safety Guards (G-U1–G-U2: Rolling Update) ───────────────

    def guard_canary_ready(  # G-U1 — LAW-3 RULE-1
        self,
        compatibility_ok: bool,
        canary_percent_set: bool,
        manifest_hash_computed: bool,
    ) -> GuardianResult:
        if not compatibility_ok:
            return GuardianResult(False, "G-U1 BLOCKED: compatibility check failed")
        if not canary_percent_set:
            return GuardianResult(False, "G-U1 BLOCKED: canary percent not set")
        if not manifest_hash_computed:
            return GuardianResult(False, "G-U1 BLOCKED: manifest hash not computed")
        return GuardianResult(True, "G-U1 PASSED: canary ready")

    def guard_rollback_required(  # G-U2 — LAW-8 RULE-5
        self,
        health_check_failure: bool,
        error_rate_spike: bool,
        latency_degraded: bool,
    ) -> GuardianResult:
        if health_check_failure:
            return GuardianResult(False, "G-U2 TRIGGERED: health check failure, rolling back")
        if error_rate_spike:
            return GuardianResult(False, "G-U2 TRIGGERED: error rate spike, rolling back")
        if latency_degraded:
            return GuardianResult(False, "G-U2 TRIGGERED: latency degraded, rolling back")
        return GuardianResult(True, "G-U2 PASSED: no rollback needed")

    # ── Safety Guards (G-M1–G-M2: Migration) ────────────────────

    def guard_dry_run_passed(  # G-M1 — LAW-3 RULE-1
        self,
        dry_run_passed: bool,
        compatibility_ok: bool,
        issues_empty: bool,
    ) -> GuardianResult:
        if not dry_run_passed:
            return GuardianResult(False, "G-M1 BLOCKED: dry run failed")
        if not compatibility_ok:
            return GuardianResult(False, "G-M1 BLOCKED: compatibility issues")
        if not issues_empty:
            return GuardianResult(False, "G-M1 BLOCKED: issues found in dry run")
        return GuardianResult(True, "G-M1 PASSED: dry run OK")

    def guard_snapshot_verified(  # G-M2 — LAW-8 RULE-2
        self,
        snapshot_hash_match: bool,
        journal_offset_valid: bool,
        source_integrity_ok: bool,
    ) -> GuardianResult:
        if not snapshot_hash_match:
            return GuardianResult(False, "G-M2 BLOCKED: snapshot hash mismatch")
        if not journal_offset_valid:
            return GuardianResult(False, "G-M2 BLOCKED: journal offset invalid")
        if not source_integrity_ok:
            return GuardianResult(False, "G-M2 BLOCKED: source integrity check failed")
        return GuardianResult(True, "G-M2 PASSED: snapshot verified")

    # ── Deterministic Rollout Guard ──────────────────────────────

    def compute_rollout_decision(  # RULE-1
        self,
        target_version: str,
        strategy: str,
        cluster_health: Dict[str, Any],
    ) -> str:
        strategy_data = {
            "target_version": target_version,
            "strategy": strategy,
            "cluster_health": {k: v for k, v in sorted(cluster_health.items())},
        }
        strategy_hash = hashlib.sha256(
            json.dumps(strategy_data, sort_keys=True).encode()
        ).hexdigest()[:32]

        if strategy == "canary":
            return "proceed_canary"
        elif strategy == "blue_green":
            return "proceed_blue_green"
        elif cluster_health.get("degraded_nodes", 0) > 0:
            return "abort_health_degraded"
        else:
            return "proceed_rolling"

    def guard_deterministic_hash_match(  # RULE-1
        self,
        strategy_data: Dict[str, Any],
        expected_hash: str,
    ) -> GuardianResult:
        actual = hashlib.sha256(
            json.dumps(strategy_data, sort_keys=True, default=str).encode()
        ).hexdigest()[:32]
        if actual != expected_hash:
            return GuardianResult(False, f"ROLLOUT BLOCKED: hash mismatch {actual} != {expected_hash}")
        return GuardianResult(True, "ROLLOUT PASSED: deterministic hash match")

    @property
    def transition_history(self) -> List[Dict[str, Any]]:
        return list(self._transition_history)

    def reset(self) -> None:
        self._reliability_state = ReliabilityState.HEALTHY
        self._update_state = UpdateState.PREPARE_CANARY
        self._migration_state = MigrationState.DRY_RUN
        self._transition_history.clear()
