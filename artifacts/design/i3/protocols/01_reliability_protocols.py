"""Phase I3 — Production Reliability Protocols.  # LAW-3 LAW-8 LAW-11 LAW-20 LAW-21 LAW-22 RULE-1 RULE-2 RULE-3 RULE-4 RULE-5

Formal typing.Protocols for Failover Orchestration, Disaster Recovery,
Rolling Update Management, and Runtime Migration. Every interface enforces
recoverability (LAW 8), determinism (RULE 1), safety guards (RULE 3), and
service isolation (RULE 4).

Ref: Canon LAW 3 (Deterministic Execution)
Ref: Canon LAW 8 (Recoverability — all state transitions MUST be recoverable)
Ref: Canon LAW 11 (No Global State)
Ref: Canon LAW 20 (Failure Detection), LAW 21 (Failure Propagation)
Ref: Canon LAW 22 (Service Isolation)
Ref: Canon RULE 1 (Determinism), RULE 2 (No Uncontrolled IO)
Ref: Canon RULE 3 (Safety Guards), RULE 4 (Isolation), RULE 5 (Recovery)
Ref: ROADMAP Phase I3 — Production Reliability
Ref: DEVELOPER.md §15.13 (AI-Native Runtime Features), §15.15a (D8 Failure Propagation)
Ref: I1 HA State Machine (03_ha_failover_machine.md)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class IFailoverOrchestrator(Protocol):  # LAW-8 LAW-20 LAW-21 LAW-22 RULE-3 RULE-4
    """Failover orchestration — detects failure, verifies quorum, promotes replica.

    Extends I1 HAOrchestrator with production failover orchestration,
    node isolation via fencing, replica promotion, and quorum verification.
    Every operation carries recovery_trace_id for full back-traceability (LAW 8).

    Ref: I1 HAOrchestrator protocol, I1 S1–S5 Split-Brain Guards
    """

    def trigger_failover(  # LAW-8 LAW-20 RULE-3
        self,
        cluster_id: str,
        failed_node_id: str,
        quorum_status: str,
        recovery_trace_id: str,
    ) -> Dict[str, Any]:
        """Initiate failover after detecting a node failure.

        Args:
            cluster_id:        Cluster identifier.
            failed_node_id:    Identifier of the unreachable/degraded node.
            quorum_status:     Current quorum health: "healthy", "degraded", "lost".
            recovery_trace_id: Correlation ID for observability (LAW 8).

        Returns:
            failover_initiated: True if failover sequence started.
            target_standby:     Selected standby node for promotion.
            current_quorum:     Quorum count at failover time.
            lease_expiry:       Lease expiry timestamp for fencing.
            data_sync_lag_ms:   Data sync lag between primary and standby.
            isolation_action:   Fencing action taken: "drain", "isolate", "terminate".
            duration_ms:        Failover initiation time.

        LAW 8: Failover must guarantee recoverability of all committed state.
        LAW 20: Failure must be confirmed via quorum before escalation.
        RULE 3: Failover blocked if quorum_status == "lost" (guard_promote_safe).
        """

    def isolate_node(  # LAW-22 RULE-4
        self,
        cluster_id: str,
        node_id: str,
        isolation_mode: str,
        recovery_trace_id: str,
    ) -> Dict[str, Any]:
        """Isolate a node from the cluster via fencing.

        Args:
            cluster_id:        Cluster identifier.
            node_id:           Node to isolate.
            isolation_mode:    "drain" (graceful), "fence" (network cut), "terminate".
            recovery_trace_id: Correlation ID.

        Returns:
            isolated:          True if node successfully isolated.
            isolation_mode:    Mode used.
            lease_revoked:     True if lease was revoked.
            remaining_leases:  Leases still held by other nodes.
            traffic_drained:   True if all traffic was drained.
            duration_ms:       Isolation duration.

        LAW 22: Isolation must not cascade to healthy nodes.
        RULE 4: Fencing is strictly scoped to the isolated node.
        """

    def promote_replica(  # LAW-8 RULE-3
        self,
        cluster_id: str,
        standby_node_id: str,
        quorum_votes: int,
        data_sync_lag_ms: float,
        recovery_trace_id: str,
    ) -> Dict[str, Any]:
        """Promote a standby replica to active leader.

        Args:
            cluster_id:        Cluster identifier.
            standby_node_id:   Standby node to promote.
            quorum_votes:      Confirmed quorum votes for this promotion.
            data_sync_lag_ms:  Maximum data sync lag between primary and standby.
            recovery_trace_id: Correlation ID.

        Returns:
            promoted:            True if promotion succeeded.
            new_leader_id:       Identifier of the promoted leader.
            promotion_term:      Election term after promotion.
            quorum_confirmed:    True if quorum validated.
            sync_lag_at_promotion: Data sync lag at promotion time.
            duration_ms:         Promotion duration.

        LAW 8: Promotion must not lose committed transactions.
        RULE 3: Blocked if quorum_votes <= total_nodes / 2 OR data_sync_lag_ms > threshold.
        """

    def verify_quorum(  # LAW-20 LAW-21 RULE-3
        self,
        cluster_id: str,
        nodes: List[str],
        expected_quorum: int,
        recovery_trace_id: str,
    ) -> Dict[str, Any]:
        """Verify cluster quorum integrity.

        Args:
            cluster_id:        Cluster identifier.
            nodes:             List of node identifiers in the cluster.
            expected_quorum:   Minimum votes required for quorum.
            recovery_trace_id: Correlation ID.

        Returns:
            quorum_healthy:       True if quorum >= expected_quorum.
            votes_received:       Actual votes received.
            total_nodes:          Total nodes in cluster.
            unreachable_nodes:    Nodes that did not respond.
            partition_detected:   True if network partition suspected.
            election_term:        Current election term.

        LAW 20: Quorum failure must be detected and reported.
        LAW 21: Unreachable nodes must not cause cascading failure.
        RULE 3: Verify before any promote or isolate decision.
        """


@runtime_checkable
class IDisasterRecovery(Protocol):  # LAW-8 LAW-11 RULE-1 RULE-2 RULE-5
    """Disaster recovery — recovery points, restore with checksum, journal replay.

    Guarantees that every recovery point is checksum-verified and every
    restore is fully deterministic. The system can always reconstruct its
    state from the last verified recovery point + journal replay (LAW 8).

    Ref: I2 ACID State Machine, I2 Deterministic Migration Guard
    """

    def capture_recovery_point(  # LAW-8 RULE-1
        self,
        state_snapshot: Dict[str, Any],
        journal_offset: int,
        isolation_context: Dict[str, str],
        recovery_trace_id: str,
    ) -> Dict[str, Any]:
        """Capture a checksum-verified recovery point.

        Args:
            state_snapshot:    Full state snapshot dict (sorted keys for determinism).
            journal_offset:    Journal offset at snapshot time.
            isolation_context: Context dict: {node_id, cluster_id, term}.
            recovery_trace_id: Correlation ID.

        Returns:
            recovery_point_id:  Unique recovery point identifier.
            state_hash:         SHA-256 hash of state snapshot (RULE 1).
            journal_offset:     Confirmed journal offset.
            timestamp_ns:       Capture timestamp.
            checksum:           Combined checksum of state + journal offset.
            size_bytes:         Total size of captured data.

        LAW 8: Every recovery point must be independently verifiable.
        RULE 1: Same state_snapshot + journal_offset -> same state_hash.
        """

    def restore_from_backup(  # LAW-8 RULE-5
        self,
        recovery_point_id: str,
        target_location: str,
        expected_checksum: str,
        recovery_trace_id: str,
    ) -> Dict[str, Any]:
        """Restore state from a verified recovery point.

        Args:
            recovery_point_id:  Identifier of the recovery point to restore from.
            target_location:    Target storage location for restored data.
            expected_checksum:  Expected SHA-256 checksum for verification.
            recovery_trace_id:  Correlation ID.

        Returns:
            restored:            True if restore completed.
            recovery_point_id:   Recovery point used.
            actual_checksum:     SHA-256 checksum of restored data.
            checksum_match:      True if expected == actual.
            rows_restored:       Number of data rows/entries restored.
            duration_ms:         Restore duration.

        LAW 8: Restore must fail if checksum does not match.
        RULE 5: Restore is isolated — does not affect live traffic until verified.
        """

    def validate_checksum(  # LAW-8 RULE-1
        self,
        data: Dict[str, Any],
        expected_checksum: str,
        recovery_trace_id: str,
    ) -> Dict[str, Any]:
        """Validate data integrity against an expected checksum.

        Args:
            data:               Data dict to validate.
            expected_checksum:  Expected SHA-256 checksum.
            recovery_trace_id:  Correlation ID.

        Returns:
            valid:              True if checksum matches.
            actual_checksum:    Computed SHA-256 checksum.
            data_size:          Size of data in bytes.
            data_hash_algorithm: Algorithm used ("sha256").

        RULE 1: Same data -> same checksum (deterministic validation).
        """

    def replay_journal(  # LAW-8 RULE-2
        self,
        journal_source: str,
        from_offset: int,
        to_offset: int,
        recovery_trace_id: str,
    ) -> Dict[str, Any]:
        """Replay journal entries from last recovery point to current offset.

        Args:
            journal_source:    Source of journal entries (e.g. "i2.distributed_log").
            from_offset:       Starting offset (last confirmed recovery point).
            to_offset:         Ending offset (target state).
            recovery_trace_id: Correlation ID.

        Returns:
            replayed:          True if replay completed.
            entries_replayed:  Number of journal entries replayed.
            from_offset:       Starting offset.
            to_offset:         Confirmed end offset after replay.
            consistency_ok:    True if no gaps or ordering violations detected.
            duration_ms:       Replay duration.

        LAW 8: Journal replay must exactly reconstruct state to given offset.
        RULE 2: Replay reads journal only — no uncontrolled IO.
        """


@runtime_checkable
class IRollingUpdateManager(Protocol):  # LAW-3 LAW-11 RULE-1 RULE-3 RULE-4
    """Rolling update management — canary, progressive, blue-green, rollback.

    Ensures zero-downtime updates with deterministic rollout behaviour.
    Same UpdateStrategy + ClusterHealth -> same rollout plan (RULE 1).
    Every update operation carries recovery_trace_id for observability.

    Ref: I1 Deterministic Rollout Guard (03_ha_failover_machine.md §Rollout Guard)
    """

    def prepare_canary(  # LAW-3 RULE-1
        self,
        target_version: str,
        canary_percent: float,
        compatibility_matrix: Dict[str, Any],
        recovery_trace_id: str,
    ) -> Dict[str, Any]:
        """Prepare a canary deployment for the target version.

        Args:
            target_version:       Deployment version string (semver).
            canary_percent:       Percentage of traffic to route to canary (0.0–100.0).
            compatibility_matrix: Dict of compatibility checks:
                                  {version, schema_version, api_version, protocol_version}.
            recovery_trace_id:    Correlation ID.

        Returns:
            canary_ready:         True if canary prepared.
            target_version:       Version being canaried.
            canary_percent:       Configured traffic percentage.
            health_check_endpoint: Health check endpoint for canary.
            expected_checksum:    SHA-256 of deployment manifest (RULE 1).
            duration_ms:          Preparation duration.

        RULE 1: Same target_version + compatibility_matrix -> same canary manifest.
        LAW 3: Canary must not affect deterministic execution of running workflows.
        """

    def roll_forward(  # LAW-3 RULE-4
        self,
        target_version: str,
        strategy: str,
        cluster_health: Dict[str, Any],
        recovery_trace_id: str,
    ) -> Dict[str, Any]:
        """Roll forward a deployment using the specified strategy.

        Args:
            target_version:    Deployment version string.
            strategy:          "rolling_update", "blue_green", "progressive".
            cluster_health:    Current cluster health metrics:
                               {healthy_nodes, degraded_nodes, cpu_avg, memory_avg}.
            recovery_trace_id: Correlation ID.

        Returns:
            rollout_started:     True if rollout initiated.
            strategy:            Strategy used.
            target_version:      Version being rolled out.
            max_surge:           Max number of extra pods during rollout.
            max_unavailable:     Max number of unavailable pods.
            health_check_window: Health check window seconds.
            duration_ms:         Rollout initiation duration.

        LAW 3: Same target_version + strategy + cluster_health -> same rollout plan.
        RULE 4: Rollout is scoped per service — no cross-service disruption.
        """

    def roll_back(  # LAW-8 RULE-5
        self,
        current_version: str,
        previous_version: str,
        rollback_reason: str,
        recovery_trace_id: str,
    ) -> Dict[str, Any]:
        """Roll back a deployment to a previous version.

        Args:
            current_version:   Current (failed) deployment version.
            previous_version:  Target rollback version.
            rollback_reason:   Reason for rollback: "health_check_failure",
                               "error_rate_spike", "compatibility_issue", "manual".
            recovery_trace_id: Correlation ID.

        Returns:
            rollback_initiated: True if rollback sequence started.
            target_version:     Version being rolled back to.
            health_check_window: Health check window for rollback.
            manifest_hash_previous: SHA-256 hash of previous manifest.
            duration_ms:        Rollback initiation duration.

        LAW 8: Rollback must restore the exact previous version state.
        RULE 5: Rollback must preserve data — no destructive rollback.
        """

    def monitor_health(  # LAW-20 RULE-3
        self,
        deployment_id: str,
        health_checks: List[Dict[str, Any]],
        recovery_trace_id: str,
    ) -> Dict[str, Any]:
        """Monitor deployment health during and after rollout.

        Args:
            deployment_id:    Deployment identifier.
            health_checks:    List of health check configs:
                              {check_type, endpoint, expected_status, timeout_sec}.
            recovery_trace_id: Correlation ID.

        Returns:
            healthy:           True if all health checks pass.
            deployment_id:     Deployment identifier.
            checks_passed:     Number of checks passed.
            checks_failed:     Number of checks failed.
            failed_checks:     List of failed check details.
            error_rate:        Current error rate (0.0–1.0).
            avg_latency_ms:    Average latency during monitoring.

        LAW 20: Failure detection during rollout must trigger immediate action.
        RULE 3: Health check thresholds are enforced as safety guards.
        """


@runtime_checkable
class IRuntimeMigrator(Protocol):  # LAW-3 LAW-8 LAW-11 RULE-1 RULE-2 RULE-4
    """Runtime backend migration — dry-run, snapshot, switch-over, verify.

    Enables seamless migration of Runtime between backends (e.g. SQLite -> PG,
    single-node -> cluster) with zero data loss and full deterministic
    verification. Same source + mapping -> same migration outcome.

    Ref: I2 DataMigrator protocol, I2 Deterministic Migration Guard
    Ref: I1 HAOrchestrator (leader migration during cluster reconfiguration)
    """

    def dry_run_migration(  # LAW-3 RULE-1
        self,
        source_backend: str,
        target_backend: str,
        compatibility_matrix: Dict[str, Any],
        recovery_trace_id: str,
    ) -> Dict[str, Any]:
        """Dry-run a migration simulation with compatibility checks.

        Args:
            source_backend:       Source backend identifier (e.g. "sqlite", "single_node").
            target_backend:       Target backend identifier (e.g. "postgresql", "cluster").
            compatibility_matrix: Dict of compatibility checks:
                                  {schema_version, api_version, data_format, protocol}.
            recovery_trace_id:    Correlation ID.

        Returns:
            dry_run_passed:       True if dry-run completed without issues.
            compatibility_ok:     True if all compatibility checks passed.
            source_backend:       Source backend identifier.
            target_backend:       Target backend identifier.
            issues_found:         List of compatibility issues detected.
            estimated_duration_ms: Estimated migration duration.
            data_volume_bytes:    Estimated data volume to migrate.

        LAW 3: Dry-run must be deterministic — same inputs -> same issues.
        RULE 1: Same source + target + compatibility_matrix -> same dry-run result.
        """

    def snapshot_state(  # LAW-8 RULE-2
        self,
        source_backend: str,
        tables_or_collections: List[str],
        recovery_trace_id: str,
    ) -> Dict[str, Any]:
        """Capture a deterministic snapshot of the source backend state.

        Args:
            source_backend:       Source backend identifier.
            tables_or_collections: List of tables/collections to snapshot.
            recovery_trace_id:    Correlation ID.

        Returns:
            snapshot_id:          Unique snapshot identifier.
            snapshot_hash:        SHA-256 hash of snapshot data (RULE 1).
            tables_snapshot:      Number of tables/collections snapshotted.
            total_rows:           Total rows/records in snapshot.
            journal_offset:       Journal offset at snapshot time.
            size_bytes:           Total snapshot size.
            duration_ms:          Snapshot duration.

        LAW 8: Snapshot is the foundation for recoverable migration.
        RULE 2: Snapshot is read-only — no mutation of source.
        """

    def switch_over(  # LAW-8 RULE-4
        self,
        target_backend: str,
        snapshot_hash: str,
        switch_strategy: str,
        recovery_trace_id: str,
    ) -> Dict[str, Any]:
        """Switch traffic from source to target backend.

        Args:
            target_backend:    Target backend identifier.
            snapshot_hash:     SHA-256 hash of the snapshot being switched from.
            switch_strategy:   "atomic" (cut-over), "gradual" (percentage-based),
                               "shadow" (dual-write before cut).
            recovery_trace_id: Correlation ID.

        Returns:
            switch_completed:    True if switch-over completed.
            target_backend:      Target backend identifier.
            switch_strategy:     Strategy used.
            traffic_routed:      Percentage of traffic on new backend.
            rollback_available:  True if rollback path exists.
            data_consistency_ok: True if data consistency verified.
            duration_ms:         Switch-over duration.

        LAW 8: Switch-over must have a rollback path until verified.
        RULE 4: Switch-over is scoped per service — no cross-service impact.
        """

    def verify_post_migration(  # LAW-8 RULE-1
        self,
        source_snapshot_hash: str,
        target_backend: str,
        expected_checksum: str,
        recovery_trace_id: str,
    ) -> Dict[str, Any]:
        """Verify migration integrity post switch-over.

        Args:
            source_snapshot_hash: SHA-256 hash of the pre-migration snapshot.
            target_backend:       Target backend identifier.
            expected_checksum:    Expected checksum of migrated data.
            recovery_trace_id:    Correlation ID.

        Returns:
            verified:             True if all checks pass.
            source_hash_match:    True if target data matches source snapshot hash.
            checksum_match:       True if actual checksum matches expected.
            row_count_match:      True if row counts match.
            integrity_pct:        Percentage of records verified.
            duration_ms:          Verification duration.

        RULE 1: Same data -> same hash -> deterministic verification.
        """
