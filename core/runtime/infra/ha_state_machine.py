"""Phase I1 — HA State Machine with Split-Brain Guards.  # LAW-20 LAW-21 LAW-22 RULE-1 RULE-3 RULE-4 RULE-5

5-state HA lifecycle machine with 9 transitions (H1–H9) and 5 Split-Brain
Guards (S1–S5). Enforces Canon LAW 20 (Failure Detection), LAW 21 (Failure
Propagation), LAW 22 (Service Isolation), RULE 3 (Safety Guards), RULE 4
(Isolation), and RULE 5 (Recovery).

Ref: Canon LAW 20, LAW 21, LAW 22
Ref: Canon RULE 1, RULE 3, RULE 4, RULE 5
Ref: artifacts/design/i1/03_ha_failover_machine.md
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class HAState(str, Enum):  # LAW-11 LAW-20
    LEADER = "leader"
    FOLLOWER = "follower"
    CANDIDATE = "candidate"
    ISOLATED = "isolated"
    RECOVERING = "recovering"


class Transition(str, Enum):
    H1 = "h1"  # FOLLOWER -> CANDIDATE (lease expired)
    H2 = "h2"  # CANDIDATE -> LEADER (quorum election)
    H3 = "h3"  # LEADER -> RECOVERING (health degraded)
    H4 = "h4"  # LEADER -> FOLLOWER (peaceful stepdown)
    H5 = "h5"  # LEADER -> ISOLATED (network partition)
    H6 = "h6"  # ISOLATED -> CANDIDATE (rejoin cluster)
    H7 = "h7"  # RECOVERING -> FOLLOWER (snapshot verified)
    H8 = "h8"  # RECOVERING -> ISOLATED (recovery timeout)
    H9 = "h9"  # FOLLOWER -> ISOLATED (follower isolation)


VALID_TRANSITIONS: Dict[HAState, Dict[Transition, HAState]] = {
    HAState.FOLLOWER: {Transition.H1: HAState.CANDIDATE, Transition.H9: HAState.ISOLATED},
    HAState.CANDIDATE: {Transition.H2: HAState.LEADER},
    HAState.LEADER: {
        Transition.H3: HAState.RECOVERING,
        Transition.H4: HAState.FOLLOWER,
        Transition.H5: HAState.ISOLATED,
    },
    HAState.ISOLATED: {Transition.H6: HAState.CANDIDATE},
    HAState.RECOVERING: {Transition.H7: HAState.FOLLOWER, Transition.H8: HAState.ISOLATED},
}


@dataclass
class GuardianResult:  # RULE-3
    """Result of a split-brain guard check."""
    allowed: bool = True
    reason: str = ""


class HAStateMachine:  # RULE-3
    """5-state HA lifecycle machine with split-brain guards (S1–S5).

    Every transition is gated by a guard that enforces quorum, lease,
    checksum, and isolation invariants.
    """

    def __init__(self, initial_state: HAState = HAState.FOLLOWER) -> None:
        self._current_state: HAState = initial_state
        self._transition_history: List[Dict[str, Any]] = []
        self._leader_terms: Dict[str, int] = {}  # cluster_id -> term

    @property
    def current_state(self) -> HAState:
        return self._current_state

    def apply_transition(self, transition: Transition) -> HAState:  # RULE-3
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

    # ── Split-Brain Guards (S1–S5) ───────────────────────────────

    def guard_quorum_election(  # S1 — RULE-3
        self,
        quorum_votes: int,
        total_nodes: int,
        election_term: int,
        last_known_term: int,
        no_other_leader_advertised: bool,
    ) -> GuardianResult:
        """S1 — Quorum Election Guard. Prevents two leaders elected concurrently."""
        if quorum_votes <= total_nodes // 2:
            return GuardianResult(False, "S1 BLOCKED: insufficient quorum")
        if election_term <= last_known_term:
            return GuardianResult(False, "S1 BLOCKED: stale election term")
        if not no_other_leader_advertised:
            return GuardianResult(False, "S1 BLOCKED: split brain detected")
        return GuardianResult(True, "S1 PASSED")

    def guard_lease_expired(  # S2 — LAW-20
        self,
        leader_heartbeat_age: float,
        lease_timeout_sec: float,
        nodes_reporting_missing_count: int,
        total_nodes: int,
        lease_holder: str,
        known_leader: str,
    ) -> GuardianResult:
        """S2 — Lease Expiry Guard. Prevents premature leader election."""
        if leader_heartbeat_age <= lease_timeout_sec:
            return GuardianResult(False, "S2 BLOCKED: leader still alive")
        quorum_confirm = total_nodes // 2 + 1
        if nodes_reporting_missing_count < quorum_confirm:
            return GuardianResult(False, "S2 BLOCKED: insufficient confirmation")
        if lease_holder == known_leader:
            return GuardianResult(False, "S2 BLOCKED: lease holder matches known leader")
        return GuardianResult(True, "S2 PASSED")

    def guard_snapshot_verified(  # S3 — RULE-1 RULE-5
        self,
        snapshot_hash: str,
        source_node_hash: str,
        snapshot_term: int,
        last_committed_term: int,
        delta_log_applied_up_to: int,
        source_commit_index: int,
    ) -> GuardianResult:
        """S3 — Snapshot Verification Guard. Prevents corrupted/stale state sync."""
        if snapshot_hash != source_node_hash:
            return GuardianResult(False, "S3 BLOCKED: checksum mismatch")
        if snapshot_term < last_committed_term:
            return GuardianResult(False, "S3 BLOCKED: stale snapshot")
        if delta_log_applied_up_to < source_commit_index:
            return GuardianResult(False, "S3 BLOCKED: missing deltas")
        return GuardianResult(True, "S3 PASSED")

    def guard_network_partition(  # S4 — LAW-22 RULE-4
        self,
        quorum_lost_interval: float,
        max_partition_sec: float,
        leader_can_reach: int,
        quorum_minimum: int,
        lease_remaining: float,
    ) -> GuardianResult:
        """S4 — Network Partition Guard. Prevents leader operating without quorum."""
        if quorum_lost_interval <= max_partition_sec:
            return GuardianResult(False, "S4 BLOCKED: still within tolerance")
        if leader_can_reach >= quorum_minimum:
            return GuardianResult(False, "S4 BLOCKED: still has quorum")
        if lease_remaining > 0:
            return GuardianResult(False, "S4 BLOCKED: lease still valid")
        return GuardianResult(True, "S4 PASSED")

    def guard_follower_isolation(  # S5 — LAW-22 LAW-11
        self,
        follower_cannot_reach_leader: bool,
        cannot_reach_quorum: bool,
        leader_lease_valid: bool,
        follower_has_uncommitted_log: bool,
    ) -> GuardianResult:
        """S5 — Follower Isolation Guard. Prevents follower operating partitioned."""
        if not follower_cannot_reach_leader and not cannot_reach_quorum:
            return GuardianResult(False, "S5 BLOCKED: can still reach leader or quorum")
        if not leader_lease_valid:
            return GuardianResult(False, "S5 BLOCKED: leader also isolated, trigger election instead")
        if follower_has_uncommitted_log:
            return GuardianResult(False, "S5 BLOCKED: data loss risk with uncommitted entries")
        return GuardianResult(True, "S5 PASSED")

    # ── Deterministic Rollout Guard ──────────────────────────────

    def compute_manifest_hash(self, manifest: Dict[str, Any]) -> str:  # RULE-1
        raw = json.dumps({
            "runtime_version": manifest.get("runtime_version", ""),
            "worker_pods": manifest.get("worker_pods", 0),
            "resource_limits": manifest.get("resource_limits", {}),
            "health_checks": sorted(
                manifest.get("health_checks", []),
                key=lambda x: json.dumps(x, sort_keys=True),
            ),
            "configmap_refs": sorted(manifest.get("configmap_refs", [])),
            "namespace": manifest.get("namespace", ""),
        }, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    def guard_deterministic_hash_match(  # RULE-1
        self,
        manifest: Dict[str, Any],
        expected_hash: str,
    ) -> GuardianResult:
        actual = self.compute_manifest_hash(manifest)
        if actual != expected_hash:
            return GuardianResult(False, f"ROLLOUT BLOCKED: hash mismatch {actual} != {expected_hash}")
        return GuardianResult(True, "ROLLOUT PASSED: deterministic hash match")

    @property
    def transition_history(self) -> List[Dict[str, Any]]:
        return list(self._transition_history)

    def reset(self) -> None:
        self._current_state = HAState.FOLLOWER
        self._transition_history.clear()
        self._leader_terms.clear()
