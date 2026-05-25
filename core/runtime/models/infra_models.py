"""Phase I1 — Production Infrastructure Models.  # LAW-1 LAW-5 LAW-11 LAW-20 LAW-21 LAW-22 RULE-1 RULE-2 RULE-3 RULE-4 RULE-5

Shared dataclasses and enums for all I1 components: IKubernetesDeployer,
IDistributedQueue, IHAOrchestrator, and IObjectStorage.

Ref: Canon LAW 1 (Interface Authority), LAW 5 (Observability)
Ref: Canon LAW 11 (No Global State)
Ref: Canon LAW 20 (Failure Detection), LAW 21 (Failure Propagation)
Ref: Canon LAW 22 (Service Isolation)
Ref: Canon RULE 1-5
Ref: artifacts/design/i1/models/02_deployment_and_queue_models.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# ── Enums ────────────────────────────────────────────────────────────────────


class HAState(str, Enum):  # LAW-11 LAW-20
    LEADER = "leader"
    FOLLOWER = "follower"
    CANDIDATE = "candidate"
    ISOLATED = "isolated"
    RECOVERING = "recovering"


class WorkerStatus(str, Enum):  # LAW-5
    PENDING = "pending"
    RUNNING = "running"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    TERMINATED = "terminated"


class QueueTopic(str, Enum):  # LAW-11
    EXECUTION = "runtime.execution"
    SCALING = "runtime.scaling"
    FAILOVER = "runtime.failover"
    DEPLOYMENT = "runtime.deployment"
    HEALTH_CHECK = "runtime.health"
    RECOVERY = "runtime.recovery"


class MessagePriority(int, Enum):  # RULE-5
    LOW = 0
    MEDIUM = 1
    HIGH = 2
    CRITICAL = 3


class DLQStatus(str, Enum):  # RULE-5
    NONE = "none"
    ROUTED = "routed"
    CONSUMED = "consumed"


class LeaderElectionState(str, Enum):  # LAW-20
    IDLE = "idle"
    VOTING = "voting"
    ELECTED = "elected"
    TIMEOUT = "timeout"
    SPLIT_BRAIN = "split_brain"


class ArtifactState(str, Enum):  # RULE-1
    STORED = "stored"
    VERIFIED = "verified"
    CORRUPTED = "corrupted"
    EXPIRED = "expired"
    DELETED = "deleted"


# ── Dataclasses ──────────────────────────────────────────────────────────────


@dataclass
class DeploymentManifest:  # LAW-1 LAW-5 LAW-11 RULE-3 RULE-4
    runtime_version: str = ""
    worker_pods: int = 3
    resource_limits: Dict[str, Dict[str, str]] = field(default_factory=lambda: {
        "worker": {"cpu": "1.0", "memory": "512Mi"},
        "scheduler": {"cpu": "0.5", "memory": "256Mi"},
        "queue_proxy": {"cpu": "0.25", "memory": "128Mi"},
    })
    health_checks: List[Dict[str, Any]] = field(default_factory=lambda: [
        {"path": "/healthz", "port": 8080, "initial_delay_sec": 10, "period_sec": 15},
        {"path": "/readyz", "port": 8080, "initial_delay_sec": 5, "period_sec": 10},
    ])
    configmap_refs: List[str] = field(default_factory=lambda: [
        "emo-runtime-config-v1", "emo-worker-profiles-v1",
    ])
    infra_trace_id: str = ""  # LAW 5
    namespace: str = "emo-production"
    image_pull_policy: str = "Always"
    replicas_by_zone: Dict[str, int] = field(default_factory=lambda: {
        "us-east-1": 2, "eu-west-1": 1,
    })
    rollout_strategy: str = "rolling_update"
    canary_percent: int = 0
    manifest_hash: str = ""  # RULE 1


@dataclass
class QueueMessage:  # LAW-11 LAW-5 RULE-5
    msg_id: str = ""
    topic: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    payload_hash: str = ""  # RULE 1
    priority: MessagePriority = MessagePriority.MEDIUM
    retry_count: int = 0
    max_retries: int = 3
    dlq_status: DLQStatus = DLQStatus.NONE  # RULE 5
    enqueued_at_ns: int = 0
    visible_at_ns: int = 0
    delivery_count: int = 0
    worker_group: str = ""
    infra_trace_id: str = ""  # LAW 5


@dataclass
class NodeSpec:  # LAW-20 LAW-22
    node_id: str = ""
    role: str = "worker"
    zone: str = ""
    version: str = ""
    last_heartbeat_ns: int = 0
    lease_holder: str = ""
    ha_state: HAState = HAState.FOLLOWER
    capabilities: List[str] = field(default_factory=list)
    resource_capacity: Dict[str, str] = field(default_factory=lambda: {
        "cpu": "4.0", "memory": "8Gi", "ephemeral_storage": "50Gi",
    })
    infra_trace_id: str = ""


@dataclass
class HAQuorumResult:  # LAW-20 RULE-3
    quorum_reached: bool = False
    leader_id: str = ""
    term: int = 0
    votes_for: int = 0
    votes_against: int = 0
    total_nodes: int = 0
    election_state: LeaderElectionState = LeaderElectionState.IDLE
    split_brain_detected: bool = False
    split_brain_nodes: List[str] = field(default_factory=list)
    elected_at_ns: int = 0
    infra_trace_id: str = ""


@dataclass
class FailoverPlan:  # LAW-21 RULE-5
    plan_id: str = ""
    cluster_id: str = ""
    failed_leader_id: str = ""
    candidate_nodes: List[str] = field(default_factory=list)
    new_leader_id: str = ""
    failover_steps: List[str] = field(default_factory=list)
    estimated_downtime_ms: float = 0.0
    recovery_actions: List[str] = field(default_factory=list)
    is_automatic: bool = True
    requires_approval: bool = False
    infra_trace_id: str = ""


@dataclass
class StorageRef:  # LAW-11 RULE-1
    bucket: str = ""
    key: str = ""
    content_type: str = "application/octet-stream"
    checksum_sha256: str = ""
    size_bytes: int = 0
    expiry_timestamp: int = 0
    artifact_state: ArtifactState = ArtifactState.STORED
    infra_trace_id: str = ""
    stored_at_ns: int = 0
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass
class ScalingEvent:  # LAW-5
    event_id: str = ""
    deployment_id: str = ""
    previous_count: int = 0
    target_count: int = 0
    current_count: int = 0
    status: str = "in_progress"
    duration_ms: float = 0.0
    infra_trace_id: str = ""
    recorded_at_ns: int = 0


@dataclass
class ClusterHealthReport:  # LAW-5 LAW-20
    cluster_id: str = ""
    total_nodes: int = 0
    healthy_nodes: int = 0
    degraded_nodes: int = 0
    isolated_nodes: int = 0
    leader_id: str = ""
    leader_term: int = 0
    average_heartbeat_lag_ms: float = 0.0
    quorum_health: str = "healthy"
    infra_trace_id: str = ""
    reported_at_ns: int = 0
