"""Phase I1 — Production Infrastructure Protocols.  # LAW-1 LAW-5 LAW-11 LAW-20 LAW-21 LAW-22 RULE-1 RULE-2 RULE-3 RULE-4 RULE-5

Formal typing.Protocols for Kubernetes Deployer, Distributed Queue,
HA Orchestrator, and Object Storage runtimes. Every interface conforms
to Interface Authority (LAW 1), enforces observability (LAW 5), and
guarantees stateless/immutable design (LAW 11, RULE 2).

Ref: Canon LAW 1 (Interface Authority)
Ref: Canon LAW 5 (Observability Mandatory)
Ref: Canon LAW 11 (No Global State)
Ref: Canon LAW 20 (Failure Detection), LAW 21 (Failure Propagation)
Ref: Canon LAW 22 (Service Isolation)
Ref: Canon RULE 1 (Determinism), RULE 2 (No Uncontrolled IO)
Ref: Canon RULE 3 (Safety Guards), RULE 4 (Isolation), RULE 5 (Recovery)
Ref: ROADMAP Phase I1 — Production Infrastructure
Ref: DEVELOPER.md §15.9, §15.13
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class IKubernetesDeployer(Protocol):  # LAW-1 LAW-5 LAW-11 RULE-3 RULE-4
    """Kubernetes deployment orchestrator — stateless and idempotent.

    Every deployment is driven by a declarative manifest. The deployer
    never mutates global state (LAW 11) and reports all lifecycle events
    to F4 Observability (LAW 5).
    """

    def deploy_runtime(  # LAW-1 RULE-3
        self,
        manifest: Dict[str, Any],
        infra_trace_id: str,
    ) -> Dict[str, Any]:
        """Deploy a Runtime release from a declarative manifest.

        Args:
            manifest:       DeploymentManifest as dict (runtime_version,
                            worker_pods, resource_limits, health_checks,
                            configmap_refs).
            infra_trace_id: Correlation ID for observability (LAW 5).

        Returns:
            deployment_id:  Unique deployment identifier.
            status:         One of "deploying", "deployed", "failed".
            worker_count:   Number of worker pods requested.
            cluster_state_hash: Deterministic hash of target cluster state.
            events:         List of lifecycle events emitted during deploy.

        RULE 3: Pre-deployment capability check enforced.
        LAW 11: No global mutable state — every deploy is fresh.
        """

    def scale_workers(  # LAW-5 RULE-4
        self,
        deployment_id: str,
        target: int,
        infra_trace_id: str,
    ) -> Dict[str, Any]:
        """Scale the worker pod count for an active deployment.

        Args:
            deployment_id:  Target deployment.
            target:         Desired number of worker replicas.
            infra_trace_id: Correlation ID for observability.

        Returns:
            previous_count: Worker count before scaling.
            current_count:  Worker count after scaling.
            scaling_ok:     True if all pods reached ready state.
            events:         Scaling lifecycle events.

        LAW 5: All scaling events reported to F4 TelemetryAggregator.
        RULE 4: Workers are isolated — scaling does not affect other deployments.
        """

    def rollout_rollback(  # RULE-3 RULE-5
        self,
        deployment_id: str,
        target_version: str,
        infra_trace_id: str,
    ) -> Dict[str, Any]:
        """Rollback a deployment to a previous version.

        Args:
            deployment_id:  Target deployment.
            target_version: Version to rollback to (e.g. "v1.2.3").
            infra_trace_id: Correlation ID for observability.

        Returns:
            rollback_ok:       True if rollback completed.
            previous_version:  Version before rollback.
            current_version:   Version after rollback.
            events:            Rollback lifecycle events.

        RULE 3: Rollback guarded by health check verification.
        RULE 5: Failed rollback retries independently.
        """

    def capture_events(  # LAW-5
        self,
        deployment_id: str,
        infra_trace_id: str,
    ) -> List[Dict[str, Any]]:
        """Capture all deployment-related Kubernetes events.

        Args:
            deployment_id:  Target deployment.
            infra_trace_id: Correlation ID for observability.

        Returns:
            List of event dicts: {timestamp, type, reason, message, involved_object}.
        """


@runtime_checkable
class IDistributedQueue(Protocol):  # LAW-1 LAW-5 LAW-11 RULE-2 RULE-5
    """Distributed task queue — message routing, priority, DLQ.

    All queue state is ephemeral or backed by durable storage.
    No global in-memory state (LAW 11). Every message carries observability
    metadata (LAW 5).
    """

    def enqueue(  # LAW-11 RULE-2
        self,
        task: Dict[str, Any],
        topic: str,
        priority: int = 0,
        infra_trace_id: str = "",
    ) -> Dict[str, Any]:
        """Enqueue a task message into a topic.

        Args:
            task:           Task payload as dict.
            topic:          Queue topic (e.g. "runtime.execution", "runtime.scaling").
            priority:       Message priority (0=low, 1=medium, 2=high, 3=critical).
            infra_trace_id: Correlation ID for observability.

        Returns:
            msg_id:         Unique message identifier.
            topic:          Topic the message was enqueued to.
            enqueued_at_ns: Epoch nanosecond timestamp.
            payload_hash:   SHA-256 hash of task payload (RULE 1).

        LAW 11: Queue is a service boundary — no shared state.
        RULE 2: Payload is validated before enqueue.
        """

    def dequeue(  # LAW-5
        self,
        worker_group: str,
        topics: Optional[List[str]] = None,
        batch_size: int = 1,
        infra_trace_id: str = "",
    ) -> List[Dict[str, Any]]:
        """Dequeue messages for a worker group.

        Args:
            worker_group:   Logical worker group identifier.
            topics:         Optional topic filter. None = all subscribed topics.
            batch_size:     Max messages to dequeue in one call.
            infra_trace_id: Correlation ID for observability.

        Returns:
            List of message dicts: {msg_id, topic, payload, payload_hash,
            priority, enqueued_at_ns, delivery_count}.
        """

    def acknowledge(  # RULE-5
        self,
        msg_id: str,
        worker_group: str,
        infra_trace_id: str = "",
    ) -> bool:
        """Acknowledge a message as successfully processed.

        Args:
            msg_id:         Message ID to acknowledge.
            worker_group:   Acknowledging worker group.
            infra_trace_id: Correlation ID.

        Returns:
            True if acknowledged, False if message not found.
        """

    def requeue_on_nack(  # RULE-5
        self,
        msg_id: str,
        worker_group: str,
        reason: str = "",
        delay_sec: float = 0.0,
        infra_trace_id: str = "",
    ) -> Dict[str, Any]:
        """Re-queue a negatively acknowledged message.

        Args:
            msg_id:         Message ID to requeue.
            worker_group:   Nacking worker group.
            reason:         Nack reason (e.g. "timeout", "processing_error").
            delay_sec:      Delay before message is visible again.
            infra_trace_id: Correlation ID.

        Returns:
            requeue_ok:     True if requeued.
            retry_count:    Current retry count for this message.
            dlq_routed:     True if moved to dead-letter queue.
        """


@runtime_checkable
class IHAOrchestrator(Protocol):  # LAW-1 LAW-5 LAW-11 LAW-20 LAW-21 LAW-22 RULE-3 RULE-4 RULE-5
    """High-Availability orchestrator — leader election, fencing, failover.

    Every HA decision is deterministic, uses quorum-based consensus,
    and never stores global mutable state (LAW 11).
    """

    def elect_leader(  # LAW-11 LAW-20 RULE-3
        self,
        cluster_id: str,
        candidates: List[Dict[str, Any]],
        infra_trace_id: str,
    ) -> Dict[str, Any]:
        """Elect a leader from candidate nodes using quorum consensus.

        Args:
            cluster_id:     Cluster identifier.
            candidates:     List of candidate node dicts: {node_id, role,
                            last_heartbeat_ns, lease_holder, version}.
            infra_trace_id: Correlation ID.

        Returns:
            leader_id:      Elected leader node ID.
            term:           Election term number.
            quorum_votes:   Number of votes received.
            total_nodes:    Total nodes in cluster.
            elected_at_ns:  Election timestamp.

        LAW 11: No global state — election is ephemeral, scoped to term.
        LAW 20: Quorum-based failure detection.
        RULE 3: Election requires quorum > total_nodes / 2.
        """

    def monitor_fencing(  # LAW-20 LAW-22 RULE-4
        self,
        cluster_id: str,
        leader_id: str,
        lease_timeout_sec: float,
        infra_trace_id: str,
    ) -> Dict[str, Any]:
        """Monitor leader health and fence if lease expires.

        Args:
            cluster_id:        Cluster identifier.
            leader_id:         Current leader node ID.
            lease_timeout_sec: Lease timeout in seconds.
            infra_trace_id:    Correlation ID.

        Returns:
            leader_alive:   True if leader heartbeat is valid.
            lease_expired:  True if lease has expired.
            fenced:         True if leader was fenced.
            remaining_lease_sec: Remaining lease time.
        """

    def trigger_failover(  # LAW-21 LAW-22 RULE-5
        self,
        cluster_id: str,
        failed_leader_id: str,
        candidates: List[Dict[str, Any]],
        infra_trace_id: str,
    ) -> Dict[str, Any]:
        """Trigger failover from a failed leader to a new leader.

        Args:
            cluster_id:        Cluster identifier.
            failed_leader_id:  ID of the failed leader.
            candidates:        List of candidate nodes.
            infra_trace_id:    Correlation ID.

        Returns:
            new_leader_id:     Newly elected leader.
            failover_ok:       True if failover succeeded.
            recovery_actions:  List of recovery steps taken.
            downtime_ms:       Measured downtime.

        LAW 21: Failure propagation is contained — no cascading.
        RULE 5: Recovery retries independently.
        """

    def sync_state_snapshot(  # LAW-5 RULE-1
        self,
        cluster_id: str,
        source_node_id: str,
        target_node_id: str,
        infra_trace_id: str,
    ) -> Dict[str, Any]:
        """Synchronise a state snapshot from source to target node.

        Args:
            cluster_id:        Cluster identifier.
            source_node_id:    Source node for snapshot.
            target_node_id:    Target node to receive snapshot.
            infra_trace_id:    Correlation ID.

        Returns:
            snapshot_ok:        True if sync succeeded.
            snapshot_size_bytes: Size of transferred snapshot.
            snapshot_hash:      SHA-256 hash (RULE 1).
            synced_at_ns:       Timestamp.
        """


@runtime_checkable
class IObjectStorage(Protocol):  # LAW-1 LAW-5 LAW-11 RULE-1 RULE-2
    """Immutable object storage — artifact persistence with integrity verification.

    All stored objects are immutable (write-once) with content-addressable
    checksums. No global mutable state (LAW 11).
    """

    def store_artifact(  # LAW-11 RULE-1 RULE-2
        self,
        uri: str,
        payload: bytes,
        content_type: str,
        infra_trace_id: str = "",
    ) -> Dict[str, Any]:
        """Store an artifact at the given URI.

        Args:
            uri:             Storage URI (e.g. "s3://bucket/path/key").
            payload:         Raw bytes to store.
            content_type:    MIME type of the payload.
            infra_trace_id:  Correlation ID.

        Returns:
            stored:          True if stored successfully.
            checksum_sha256: SHA-256 checksum of stored payload.
            size_bytes:      Payload size in bytes.
            stored_at_ns:    Timestamp.

        RULE 1: Same payload → same checksum (deterministic).
        RULE 2: Input validated before storage.
        """

    def retrieve_artifact(  # LAW-5 RULE-1
        self,
        uri: str,
        expected_checksum: str = "",
        infra_trace_id: str = "",
    ) -> Dict[str, Any]:
        """Retrieve an artifact from storage.

        Args:
            uri:               Storage URI.
            expected_checksum: Optional SHA-256 checksum for verification.
            infra_trace_id:    Correlation ID.

        Returns:
            payload:           Retrieved bytes.
            content_type:      MIME type.
            checksum_sha256:   Actual SHA-256 checksum.
            size_bytes:        Payload size.
            integrity_ok:      True if checksum matches (if provided).

        RULE 1: Integrity verification via checksum.
        """

    def lifecycle_cleanup(  # LAW-5
        self,
        bucket: str,
        prefix: str,
        max_age_sec: float,
        infra_trace_id: str = "",
    ) -> Dict[str, Any]:
        """Clean up expired artifacts from storage.

        Args:
            bucket:           Storage bucket/container name.
            prefix:           Key prefix filter.
            max_age_sec:      Max age in seconds before deletion.
            infra_trace_id:   Correlation ID.

        Returns:
            cleaned:        True if cleanup completed.
            objects_removed: Count of removed objects.
            bytes_reclaimed: Storage bytes reclaimed.
        """

    def verify_integrity(  # RULE-1
        self,
        uri: str,
        expected_checksum: str,
        infra_trace_id: str = "",
    ) -> Dict[str, Any]:
        """Verify stored artifact integrity against expected checksum.

        Args:
            uri:               Storage URI.
            expected_checksum: Expected SHA-256 checksum.
            infra_trace_id:    Correlation ID.

        Returns:
            integrity_ok:   True if checksum matches.
            actual_checksum: Actual SHA-256 checksum.
            size_bytes:      Payload size.
        """
