"""Phase I3 — Recovery & Update Models.  # LAW-3 LAW-8 LAW-11 LAW-20 LAW-21 LAW-22 RULE-1 RULE-2 RULE-3 RULE-4 RULE-5

Shared dataclasses and enums for all I3 components: IFailoverOrchestrator,
IDisasterRecovery, IRollingUpdateManager, and IRuntimeMigrator.

Every model carries recovery_trace_id for full back-traceability (LAW 8).
All hashes use SHA-256 for deterministic verification (RULE 1).

Ref: Canon LAW 3 (Deterministic), LAW 8 (Recoverability)
Ref: Canon LAW 11 (No Global State), LAW 20 (Failure Detection)
Ref: Canon LAW 21 (Failure Propagation), LAW 22 (Service Isolation)
Ref: Canon RULE 1-5
Ref: ROADMAP Phase I3 — Production Reliability
Ref: DEVELOPER.md §15.13, §15.15a (D8 Failure Propagation)
Ref: I1 models (infra_models.py), I2 models (data_models.py)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# ── Enums ────────────────────────────────────────────────────────────────────


class FailoverPhase(str, Enum):  # LAW-8 LAW-20
    """Phases of the failover lifecycle."""
    HEALTHY = "healthy"
    FAILURE_DETECTED = "failure_detected"
    QUORUM_CHECK = "quorum_check"
    ISOLATE_NODE = "isolate_node"
    PROMOTE_REPLICA = "promote_replica"
    SYNC_STATE = "sync_state"
    FALLBACK = "fallback"
    SPLIT_BRAIN_ESCALATION = "split_brain_escalation"


class IsolationMode(str, Enum):  # LAW-22 RULE-4
    """Node isolation modes during failover."""
    DRAIN = "drain"          # Graceful traffic drain
    FENCE = "fence"          # Network-level isolation
    TERMINATE = "terminate"  # Force terminate


class PromotionGuardResult(str, Enum):  # RULE-3
    """Result of the promotion safety guard check."""
    PASSED = "passed"
    BLOCKED_QUORUM = "blocked_quorum_insufficient"
    BLOCKED_SYNC_LAG = "blocked_sync_lag_exceeded"
    BLOCKED_NO_STANDBY = "blocked_no_standby_available"
    BLOCKED_LEASE_NOT_REVOKED = "blocked_lease_not_revoked"
    BLOCKED_CHECKSUM_MISMATCH = "blocked_checksum_mismatch"


class RecoveryPointStatus(str, Enum):  # LAW-8
    """Status of a disaster recovery recovery point."""
    CREATING = "creating"
    VERIFIED = "verified"
    CORRUPTED = "corrupted"
    EXPIRED = "expired"
    RESTORING = "restoring"
    RESTORED = "restored"


class DRState(str, Enum):  # LAW-8 RULE-5
    """Disaster recovery lifecycle states."""
    BACKUP_IDLE = "backup_idle"
    BACKUP_IN_PROGRESS = "backup_in_progress"
    BACKUP_VERIFIED = "backup_verified"
    RESTORE_IN_PROGRESS = "restore_in_progress"
    RESTORE_VALIDATED = "restore_validated"
    JOURNAL_REPLAYING = "journal_replaying"
    RESTORE_COMPLETE = "restore_complete"


class UpdateStrategy(str, Enum):  # LAW-3 RULE-1
    """Deployment update strategies."""
    CANARY = "canary"
    BLUE_GREEN = "blue_green"
    PROGRESSIVE = "progressive"
    ROLLING_UPDATE = "rolling_update"
    ROLLBACK = "rollback"


class UpdatePhase(str, Enum):  # LAW-3 RULE-4
    """Phases of the rolling update lifecycle."""
    PREPARE_CANARY = "prepare_canary"
    ROLL_FORWARD = "roll_forward"
    HEALTH_MONITOR = "health_monitor"
    ROLL_BACK = "roll_back"
    UPDATE_COMPLETE = "update_complete"


class RollbackReason(str, Enum):  # LAW-8
    """Reasons for deployment rollback."""
    HEALTH_CHECK_FAILURE = "health_check_failure"
    ERROR_RATE_SPIKE = "error_rate_spike"
    COMPATIBILITY_ISSUE = "compatibility_issue"
    MANUAL = "manual"
    TIMEOUT = "timeout"


class MigrationPhase(str, Enum):  # LAW-3 LAW-8
    """Phases of the runtime migration lifecycle."""
    DRY_RUN = "dry_run"
    DRY_RUN_PASSED = "dry_run_passed"
    DRY_RUN_FAILED = "dry_run_failed"
    SNAPSHOT_STATE = "snapshot_state"
    SWITCH_OVER = "switch_over"
    POST_MIGRATION_VERIFY = "post_migration_verify"
    MIGRATION_COMPLETE = "migration_complete"
    MIGRATION_ROLLED_BACK = "migration_rolled_back"


class SwitchStrategy(str, Enum):  # LAW-8 RULE-4
    """Traffic switch strategies for runtime migration."""
    ATOMIC = "atomic"      # Single cut-over
    GRADUAL = "gradual"    # Percentage-based transition
    SHADOW = "shadow"      # Dual-write before cut


class RolloutDecision(str, Enum):  # LAW-3 RULE-1
    """Deterministic rollout decision from manifest + cluster state."""
    PROCEED_ROLLING = "proceed_rolling"
    PROCEED_BLUE_GREEN = "proceed_blue_green"
    PROCEED_CANARY = "proceed_canary"
    ABORT_INSUFFICIENT_CAPACITY = "abort_insufficient_capacity"
    ABORT_HEALTH_DEGRADED = "abort_health_degraded"
    ROLLBACK_AUTOMATIC = "rollback_automatic"


# ── Dataclasses ──────────────────────────────────────────────────────────────


@dataclass
class RecoveryPoint:  # LAW-8 RULE-1
    """A checksum-verified recovery point for disaster recovery.

    Every recovery point is independently verifiable via state_hash.
    The combination of state_snapshot_hash + journal_offset uniquely
    identifies the exact system state at the point of capture.
    """

    point_id: str = ""
    timestamp_ns: int = 0
    state_snapshot_hash: str = ""   # SHA-256 of state snapshot (RULE 1)
    journal_offset: int = 0
    isolation_context: Dict[str, str] = field(default_factory=lambda: {
        "node_id": "",
        "cluster_id": "",
        "term": "",
    })
    combined_checksum: str = ""      # SHA-256(state_hash || journal_offset)
    size_bytes: int = 0
    status: RecoveryPointStatus = RecoveryPointStatus.CREATING
    recovery_trace_id: str = ""      # LAW 8
    dr_state: DRState = DRState.BACKUP_IDLE


@dataclass
class FailoverPlan:  # LAW-8 LAW-20 LAW-21 RULE-3
    """A complete failover plan with quorum, lease, and sync metadata."""

    failover_id: str = ""
    cluster_id: str = ""
    target_node: str = ""
    quorum_votes: int = 0
    total_nodes: int = 0
    lease_expiry_ns: int = 0
    data_sync_lag_ms: float = 0.0
    isolation_mode: IsolationMode = IsolationMode.DRAIN
    status: FailoverPhase = FailoverPhase.HEALTHY
    promotion_guard: PromotionGuardResult = PromotionGuardResult.PASSED
    recovery_trace_id: str = ""
    failover_duration_ms: float = 0.0
    election_term: int = 0


@dataclass
class UpdateStrategy:  # LAW-3 RULE-1
    """Deployment update strategy configuration with rollback threshold."""

    deployment_id: str = ""
    strategy: str = UpdateStrategy.ROLLING_UPDATE.value
    target_version: str = ""
    current_version: str = ""
    phase: UpdatePhase = UpdatePhase.PREPARE_CANARY
    canary_percent: float = 0.0
    rollback_threshold_error_rate: float = 0.05   # 5% error rate triggers rollback
    rollback_threshold_latency_pct: float = 50.0  # 50% latency increase triggers rollback
    health_check_window_sec: float = 60.0
    max_surge: int = 1
    max_unavailable: int = 0
    compatibility_matrix: Dict[str, Any] = field(default_factory=dict)
    cluster_health_at_rollout: Dict[str, Any] = field(default_factory=dict)
    manifest_hash: str = ""  # SHA-256 of deployment manifest (RULE 1)
    recovery_trace_id: str = ""


@dataclass
class MigrationManifest:  # LAW-3 LAW-8 RULE-1
    """Runtime migration manifest with compatibility and verification data."""

    migration_id: str = ""
    source_backend: str = ""
    target_backend: str = ""
    compatibility_matrix: Dict[str, Any] = field(default_factory=lambda: {
        "schema_version": "",
        "api_version": "",
        "data_format": "",
        "protocol": "",
    })
    dry_run_passed: bool = False
    issues_found: List[str] = field(default_factory=list)
    snapshot_hash: str = ""          # SHA-256 of pre-migration snapshot
    journal_offset: int = 0
    switch_strategy: SwitchStrategy = SwitchStrategy.ATOMIC
    estimated_duration_ms: float = 0.0
    data_volume_bytes: int = 0
    rollback_available: bool = True
    verified: bool = False
    integrity_pct: float = 0.0
    recovery_trace_id: str = ""
    phase: MigrationPhase = MigrationPhase.DRY_RUN
    duration_ms: float = 0.0
    errors: List[str] = field(default_factory=list)


@dataclass
class ClusterHealthReport:  # LAW-20 RULE-3
    """Cluster health snapshot for rollout and failover decisions."""

    cluster_id: str = ""
    healthy_nodes: int = 0
    degraded_nodes: int = 0
    total_nodes: int = 0
    cpu_avg_pct: float = 0.0
    memory_avg_pct: float = 0.0
    disk_avg_pct: float = 0.0
    error_rate: float = 0.0
    avg_latency_ms: float = 0.0
    quorum_healthy: bool = True
    partition_detected: bool = False
    election_term: int = 0
    recovery_trace_id: str = ""


@dataclass
class FencingAction:  # LAW-22 RULE-4
    """Record of a fencing action taken during node isolation."""

    action_id: str = ""
    cluster_id: str = ""
    node_id: str = ""
    isolation_mode: IsolationMode = IsolationMode.FENCE
    lease_revoked: bool = False
    traffic_drained: bool = False
    remaining_leases: int = 0
    duration_ms: float = 0.0
    success: bool = False
    recovery_trace_id: str = ""


@dataclass
class JournalReplayState:  # LAW-8 RULE-2
    """State of a journal replay operation during DR restore."""

    replay_id: str = ""
    recovery_point_id: str = ""
    from_offset: int = 0
    to_offset: int = 0
    current_offset: int = 0
    entries_replayed: int = 0
    consistency_ok: bool = False
    gaps_detected: int = 0
    duration_ms: float = 0.0
    recovery_trace_id: str = ""


@dataclass
class CompatibilityMatrix:  # LAW-3 RULE-1
    """Compatibility matrix for migration and update decisions."""

    source_version: str = ""
    target_version: str = ""
    schema_compatible: bool = True
    api_compatible: bool = True
    data_format_compatible: bool = True
    protocol_compatible: bool = True
    rollback_compatible: bool = True
    issues: List[str] = field(default_factory=list)
    recovery_trace_id: str = ""


@dataclass
class DryRunResult:  # LAW-3 RULE-1
    """Result of a migration dry-run simulation."""

    dry_run_id: str = ""
    source_backend: str = ""
    target_backend: str = ""
    passed: bool = False
    compatibility_ok: bool = True
    issues_found: List[str] = field(default_factory=list)
    estimated_duration_ms: float = 0.0
    data_volume_bytes: int = 0
    source_snapshot_hash: str = ""
    recovery_trace_id: str = ""
