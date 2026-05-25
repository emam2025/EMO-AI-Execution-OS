"""Phase I2 — ACID Sync State Machine with Guards G1–G8.  # LAW-14 LAW-20 LAW-21 RULE-1 RULE-3 RULE-4 RULE-5

7-state ACID lifecycle machine with 8 transitions (A1–A8) and 8 ACID
Guards (G1–G8). Enforces Canon LAW 14 (DAG Integrity), LAW 20 (Failure
Detection), LAW 21 (Failure Propagation), RULE 3 (Safety Guards),
RULE 4 (Isolation), and RULE 5 (Recovery).

Ref: Canon LAW 14, LAW 20, LAW 21
Ref: Canon RULE 1, RULE 3, RULE 4, RULE 5
Ref: artifacts/design/i2/03_acid_sync_machine.md
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ACIDState(str, Enum):
    TX_START = "tx_start"
    VALIDATION = "validation"
    PARTITION_ROUTING = "partition_routing"
    COMMIT = "commit"
    ACK_REPLICA = "ack_replica"
    ROLLBACK = "rollback"
    DEADLOCK = "deadlock"


class ACIDTransition(str, Enum):
    A1 = "a1"  # TX_START -> VALIDATION
    A2 = "a2"  # VALIDATION -> PARTITION_ROUTING
    A3 = "a3"  # PARTITION_ROUTING -> COMMIT
    A4 = "a4"  # COMMIT -> ACK_REPLICA
    A5 = "a5"  # COMMIT -> ROLLBACK
    A6 = "a6"  # DEADLOCK -> TX_START
    A7 = "a7"  # VALIDATION -> ROLLBACK
    A8 = "a8"  # ACK_REPLICA -> ROLLBACK


VALID_TRANSITIONS: Dict[ACIDState, Dict[ACIDTransition, ACIDState]] = {
    ACIDState.TX_START: {ACIDTransition.A1: ACIDState.VALIDATION},
    ACIDState.VALIDATION: {
        ACIDTransition.A2: ACIDState.PARTITION_ROUTING,
        ACIDTransition.A7: ACIDState.ROLLBACK,
    },
    ACIDState.PARTITION_ROUTING: {ACIDTransition.A3: ACIDState.COMMIT},
    ACIDState.COMMIT: {
        ACIDTransition.A4: ACIDState.ACK_REPLICA,
        ACIDTransition.A5: ACIDState.ROLLBACK,
    },
    ACIDState.ACK_REPLICA: {ACIDTransition.A8: ACIDState.ROLLBACK},
    ACIDState.ROLLBACK: {},
    ACIDState.DEADLOCK: {ACIDTransition.A6: ACIDState.TX_START},
}


@dataclass
class GuardianResult:
    allowed: bool = True
    reason: str = ""


class ACIDStateMachine:
    """7-state ACID lifecycle machine with guards G1–G8.

    Every transaction transition is gated by ACID Guards that enforce
    isolation, quorum, partition key, and deadlock invariants.
    """

    def __init__(self, initial_state: ACIDState = ACIDState.TX_START) -> None:
        self._current_state: ACIDState = initial_state
        self._transition_history: List[Dict[str, Any]] = []
        self._deadlock_retries: Dict[str, int] = {}

    @property
    def current_state(self) -> ACIDState:
        return self._current_state

    def apply_transition(self, transition: ACIDTransition) -> ACIDState:
        allowed = VALID_TRANSITIONS.get(self._current_state, {})
        if transition not in allowed:
            raise ValueError(
                f"Invalid transition {transition.value} from state {self._current_state.value}"
            )
        next_state = allowed[transition]
        self._transition_history.append({
            "from": self._current_state.value,
            "to": next_state.value,
            "transition": transition.value,
        })
        self._current_state = next_state
        return next_state

    # ── ACID Guards (G1–G8) ────────────────────────────────────

    def guard_tx_initiated(  # G1 — LAW-14 RULE-3
        self,
        connection_acquired: bool,
        pool_has_room: bool,
        data_trace_id_provided: bool,
    ) -> GuardianResult:
        """G1: Prevents starting a tx without pool capacity or trace ID."""
        if not connection_acquired:
            return GuardianResult(False, "G1 BLOCKED: pool exhausted")
        if not pool_has_room:
            return GuardianResult(False, "G1 BLOCKED: queue and wait")
        if not data_trace_id_provided:
            return GuardianResult(False, "G1 BLOCKED: missing data_trace_id")
        return GuardianResult(True, "G1 PASSED")

    def guard_isolation_level(  # G2 — RULE-3
        self,
        isolation_level: Optional[str],
        meets_tx_requirement: bool,
        partition_key_verified: bool,
    ) -> GuardianResult:
        """G2: Prevents executing a tx without explicit isolation level."""
        if not isolation_level:
            return GuardianResult(False, "G2 BLOCKED: isolation not set")
        if not meets_tx_requirement:
            return GuardianResult(False, "G2 BLOCKED: insufficient isolation level")
        if not partition_key_verified:
            return GuardianResult(False, "G2 BLOCKED: partition key unverified")
        return GuardianResult(True, "G2 PASSED")

    def guard_partition_key(  # G3 — LAW-11 RULE-4
        self,
        partition_key_valid: bool,
        partition_exists: bool,
        rows_routed_correctly: bool,
    ) -> GuardianResult:
        """G3: Prevents routing rows to incorrect partitions."""
        if not partition_key_valid:
            return GuardianResult(False, "G3 BLOCKED: invalid partition key")
        if not partition_exists:
            return GuardianResult(False, "G3 BLOCKED: no matching partition")
        if not rows_routed_correctly:
            return GuardianResult(False, "G3 BLOCKED: routing mismatch")
        return GuardianResult(True, "G3 PASSED")

    def guard_quorum_ack(  # G4 — LAW-21 RULE-4
        self,
        quorum_ack_count: int,
        total_replicas: int,
        replication_mode_met: bool,
        ack_timeout_not_exceeded: bool,
    ) -> GuardianResult:
        """G4: Prevents committing without majority replica acknowledgement."""
        majority = total_replicas // 2 + 1
        if quorum_ack_count < majority:
            return GuardianResult(False, f"G4 BLOCKED: insufficient acks {quorum_ack_count}/{majority}")
        if not replication_mode_met:
            return GuardianResult(False, "G4 BLOCKED: replication mode not satisfied")
        if not ack_timeout_not_exceeded:
            return GuardianResult(False, "G4 BLOCKED: ack timeout")
        return GuardianResult(True, "G4 PASSED")

    def guard_commit_failed(  # G5 — RULE-5
        self,
        any_query_error: bool,
        constraint_violation: bool,
        timeout_exceeded: bool,
    ) -> GuardianResult:
        """G5: Prevents allowing partial commit when queries fail."""
        if any_query_error:
            return GuardianResult(False, "G5 TRIGGERED: query error, rolling back")
        if constraint_violation:
            return GuardianResult(False, "G5 TRIGGERED: constraint violation, rolling back")
        if timeout_exceeded:
            return GuardianResult(False, "G5 TRIGGERED: timeout exceeded, rolling back")
        return GuardianResult(True, "G5 PASSED")

    def guard_deadlock_retry(  # G6 — LAW-20 RULE-5
        self,
        tx_id: str,
        retry_count: int,
        max_retries: int,
        backoff_waited: bool,
        deadlock_detected: bool,
    ) -> GuardianResult:
        """G6: Prevents infinite retry loops on deadlock."""
        if not deadlock_detected:
            return GuardianResult(False, "G6 NOT TRIGGERED: not a deadlock situation")
        if retry_count >= max_retries:
            return GuardianResult(False, "G6 BLOCKED: max retries exceeded")
        if not backoff_waited:
            return GuardianResult(False, "G6 BLOCKED: retry too soon")
        self._deadlock_retries[tx_id] = retry_count + 1
        return GuardianResult(True, "G6 PASSED")

    def guard_validation_failed(  # G7 — RULE-3
        self,
        isolation_level_invalid: bool,
        partition_key_missing: bool,
        data_trace_id_missing: bool,
    ) -> GuardianResult:
        """G7: Prevents proceeding with invalid transaction parameters."""
        if isolation_level_invalid:
            return GuardianResult(False, "G7 TRIGGERED: invalid isolation level, rolling back")
        if partition_key_missing:
            return GuardianResult(False, "G7 TRIGGERED: partition key missing, rolling back")
        if data_trace_id_missing:
            return GuardianResult(False, "G7 TRIGGERED: data_trace_id missing, rolling back")
        return GuardianResult(True, "G7 PASSED")

    def guard_replica_failed(  # G8 — LAW-21 RULE-5
        self,
        replica_nack: bool,
        replica_timeout_exceeded: bool,
        fallback_to_rollback: bool,
        leader_can_force_commit: bool,
    ) -> GuardianResult:
        """G8: Prevents committing when replica ack fails without fallback."""
        if replica_nack:
            return GuardianResult(False, "G8 TRIGGERED: replica nack, rolling back")
        if replica_timeout_exceeded and not fallback_to_rollback:
            return GuardianResult(False, "G8 BLOCKED: replica timeout without fallback")
        if leader_can_force_commit:
            return GuardianResult(False, "G8 BLOCKED: no force commit without replica ack")
        return GuardianResult(True, "G8 PASSED")

    # ── Deterministic Migration Guard ──────────────────────────

    def compute_snapshot_hash(  # RULE-1
        self,
        tables_data: Dict[str, Any],
    ) -> str:
        raw = json.dumps(tables_data, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    def compute_mapping_hash(  # RULE-1
        self,
        mapping_rules: List[Dict[str, Any]],
    ) -> str:
        raw = json.dumps(mapping_rules, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    def guard_migration_deterministic(  # RULE-1 LAW-14
        self,
        snapshot_hash: str,
        expected_snapshot_hash: str,
        mapping_hash: str,
        expected_mapping_hash: str,
        source_row_count: int,
        expected_row_count: int,
    ) -> GuardianResult:
        if snapshot_hash != expected_snapshot_hash:
            return GuardianResult(False, "MIGRATION BLOCKED: snapshot hash mismatch")
        if mapping_hash != expected_mapping_hash:
            return GuardianResult(False, "MIGRATION BLOCKED: mapping hash mismatch")
        if source_row_count != expected_row_count:
            return GuardianResult(False, "MIGRATION BLOCKED: row count drift")
        return GuardianResult(True, "MIGRATION PASSED: deterministic")

    # ── Compaction Guard ───────────────────────────────────────

    def guard_compaction_allowed(  # RULE-5
        self,
        retention_sec_elapsed: float,
        retention_policy_sec: float,
        no_active_readers: bool,
        compacted_hash_matches_source: bool,
    ) -> GuardianResult:
        if retention_sec_elapsed < retention_policy_sec:
            return GuardianResult(False, "COMPACTION BLOCKED: retention not met")
        if not no_active_readers:
            return GuardianResult(False, "COMPACTION BLOCKED: segment in use")
        if not compacted_hash_matches_source:
            return GuardianResult(False, "COMPACTION BLOCKED: corruption detected")
        return GuardianResult(True, "COMPACTION PASSED")

    @property
    def transition_history(self) -> List[Dict[str, Any]]:
        return list(self._transition_history)

    def reset(self) -> None:
        self._current_state = ACIDState.TX_START
        self._transition_history.clear()
        self._deadlock_retries.clear()
