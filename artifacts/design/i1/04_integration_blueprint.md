# Phase I1 — Production Infrastructure Integration Blueprint

## 1. Architecture Overview

The Production Infrastructure (I1) sits between the G5 Multi-Agent Swarm
and the F2 Control Plane, with the Distributed Queue acting as the
asynchronous buffer. All infrastructure events flow to F4 Observability.

```
G5.SwarmCoordinator ──> I1.DistributedQueue ──> I1.KubernetesDeployer ──> F2.ControlPlane
                              │                          │                       │
                              │                          │                       │
                              v                          v                       v
                         I1.HAOrchestrator          I1.ObjectStorage        F4.Observability
                         (Leader Election,          (Artifact Store,        (TraceCollector,
                          Fencing, Failover)         Integrity Verify)       AlertRouter)
```

**Key principle:** All production operations are asynchronous, idempotent,
and fully observable. The Queue decouples G5 task dispatch from K8s
deployment execution. The HA Orchestrator guarantees cluster stability.

---

## 2. Data Flow: G5 → Queue → K8s → F2 → F4

### Flow 1: Task Execution (G5 → I1.Queue → Worker Pods)

```
G5.SwarmCoordinator
    │
    │  broadcast_task({
    │    "action": "execute_dag",
    │    "dag_id": "dag_001",
    │    "mission_trace_id": "msn_abc"
    │  })
    ▼
I1.DistributedQueue.enqueue(task, topic="runtime.execution", priority=2)
    │
    │  ┌── Queue ───────────────────────────────┐
    │  │  msg_id: "msg_001"                     │
    │  │  topic: "runtime.execution"            │
    │  │  payload_hash: "abc123..."             │
    │  │  priority: HIGH                        │
    │  └────────────────────────────────────────┘
    │
    ├── Worker Pod dequeues message
    │       └── IDistributedQueue.dequeue(worker_group="workers", batch_size=1)
    │
    ├── Worker processes → acknowledges
    │       └── IDistributedQueue.acknowledge("msg_001", "workers")
    │
    └── F4.Observability
            ├── TraceCollector: {infra_trace_id, "queue.enqueue", msg_id}
            ├── TelemetryAggregator: {queue_depth, processing_rate}
            └── AlertRouter: [if queue_depth > threshold] → "QUEUE_OVERFLOW"
```

### Flow 2: Runtime Deployment (I1.K8s → F2.ControlPlane → F4)

```
I1.KubernetesDeployer.deploy_runtime(manifest, infra_trace_id)
    │
    │  ┌── F2.ControlPlane ──────────────────────┐
    │  │  ReconciliationLoop: monitor pod status │
    │  │  HealthSupervisor: health check probes  │
    │  │  Autoscaler: scale based on metrics     │
    │  └──────────────────────────────────────────┘
    │
    ├── Rollout strategy applied (rolling/canary/blue_green)
    │       └── Deterministic Rollout Guard verified
    │
    ├── I1.ObjectStorage.store_artifact(manifest_uri, manifest_bytes)
    │       └── checksum_sha256 stored for integrity
    │
    └── F4.Observability
            ├── TraceCollector: {infra_trace_id, "deploy", deployment_id}
            ├── TelemetryAggregator: {worker_count, cpu_usage, memory_usage}
            └── AlertRouter: [if deploy fails] → "DEPLOYMENT_FAILED"
```

### Flow 3: HA Failover (I1.HA → I1.Queue → F4)

```
I1.HAOrchestrator.monitor_fencing(cluster_id, leader_id, lease_timeout, infra_trace_id)
    │
    │  Lease expired? ──yes──> I1.HAOrchestrator.trigger_failover()
    │                                   │
    │                                   ├── I1.Queue.enqueue(
    │                                   │     task={action: "failover", leader_id},
    │                                   │     topic="runtime.failover",
    │                                   │     priority=MessagePriority.CRITICAL)
    │                                   │
    │                                   ├── F2.ControlPlane → drain failed node
    │                                   │
    │                                   └── F4.Observability
    │                                           ├── AlertRouter: "LEADER_FAILURE"
    │                                           └── TraceCollector: failover span
    │
    └── Leader alive? ──yes──> Continue monitoring (heartbeat OK)
```

---

## 3. Correlation ID Propagation (LAW 5)

Every infrastructure operation carries an **infra_trace_id** that flows
across all layers, ensuring full back-traceability.

### ID Hierarchy

```
mission_trace_id (G5)
    └── infra_trace_id (I1) — one per deployment/queue operation
            ├── deployment_id — one per K8s deploy
            ├── msg_id — one per Queue message
            ├── term — one per leader election term
            ├── snapshot_hash — one per state sync
            └── checksum_sha256 — one per stored artifact
```

### Propagation Matrix

| Layer | ID Carried | Format | Reference |
|-------|-----------|--------|-----------|
| G5 SwarmCoordinator | mission_trace_id | `msn_<hex>` | `SwarmContext.mission_trace_id` |
| I1 DistributedQueue | infra_trace_id | `infra_<hex>` | `QueueMessage.infra_trace_id` |
| I1 K8s Deployer | infra_trace_id | `infra_<hex>` | `DeploymentManifest.infra_trace_id` |
| I1 HA Orchestrator | infra_trace_id | `infra_<hex>` | `HAQuorumResult.infra_trace_id` |
| I1 ObjectStorage | infra_trace_id | `infra_<hex>` | `StorageRef.infra_trace_id` |
| F2 ControlPlane | infra_trace_id | `infra_<hex>` | Reconciliation loop |
| F4 TraceCollector | infra_trace_id | `infra_<hex>` | Span ID |

### Generation Rule

```python
def generate_infra_trace_id(mission_trace_id: str, operation_type: str) -> str:
    raw = f"{mission_trace_id}:i1:{operation_type}:{time.time_ns()}"
    return f"infra_{hashlib.sha256(raw.encode()).hexdigest()[:24]}"
```

---

## 4. Event Hooks for Drift & Failure Reporting

### NodeFailure Hook
**Triggered when:** A cluster node is unreachable or lease expires.

```yaml
hook: node_failure
payload:
  infra_trace_id: "infra_abc123"
  cluster_id: "cluster_prod"
  failed_node_id: "node_05"
  last_heartbeat_ns: 1716384000000000000
  lease_timeout_sec: 30.0
  quorum_status: "degraded"
targets:
  - I1.HAOrchestrator.trigger_failover()
  - I1.Queue.enqueue(topic="runtime.failover", priority=CRITICAL)
  - F4.AlertRouter.alert({severity: "critical", type: "NODE_FAILURE"})
```

### QueueOverflow Hook
**Triggered when:** Queue depth exceeds critical threshold.

```yaml
hook: queue_overflow
payload:
  infra_trace_id: "infra_def456"
  topic: "runtime.execution"
  queue_depth: 15000
  threshold: 10000
  oldest_msg_age_sec: 300.0
targets:
  - I1.KubernetesDeployer.scale_workers(target=current*2)
  - F4.AlertRouter.alert({severity: "warning", type: "QUEUE_OVERFLOW"})
  - F4.TelemetryAggregator.report({queue_depth, processing_lag})
```

### LeaderElectionCompleted Hook
**Triggered when:** A new leader is elected after failover.

```yaml
hook: leader_election_completed
payload:
  infra_trace_id: "infra_ghi789"
  cluster_id: "cluster_prod"
  new_leader_id: "node_03"
  term: 7
  quorum_votes: 3
  total_nodes: 5
  election_duration_ms: 2450.0
targets:
  - F4.AlertRouter.alert({severity: "info", type: "LEADER_ELECTED"})
  - F4.TraceCollector.record_span({type: "leader_election", duration_ms: 2450.0})
  - I1.DistributedQueue.enqueue(topic="runtime.health", priority=HIGH)
```

### ArtifactChecksumMismatch Hook
**Triggered when:** Stored artifact checksum does not match expected.

```yaml
hook: artifact_checksum_mismatch
payload:
  infra_trace_id: "infra_jkl012"
  uri: "s3://emo-artifacts/runtime/v1.2.3/manifest.json"
  expected_checksum: "abc123..."
  actual_checksum: "def456..."
  size_bytes: 4096
targets:
  - F4.AlertRouter.alert({severity: "high", type: "CHECKSUM_MISMATCH"})
  - I1.ObjectStorage.lifecycle_cleanup(bucket, prefix, max_age)
  - I1.KubernetesDeployer.rollout_rollback(target_version="previous")
```

---

## 5. Acceptance Criteria

### Latency Budgets

| Operation | Budget | Action on Exceed |
|-----------|--------|-----------------|
| Queue enqueue | 200ms | Retry once, then fail |
| Queue dequeue | 200ms | Return empty batch |
| Message acknowledge | 100ms | Log warning |
| K8s deploy (manifest apply) | 5s | Timeout, trigger rollback |
| Scale workers (per pod) | 30s | Log warning, retry |
| Leader election | 5s | Timeout, trigger re-election |
| State snapshot sync | 10s | Timeout, retry once |
| Artifact store (1MB) | 2s | Retry once, then fail |
| Artifact retrieve (1MB) | 2s | Return from cache if available |
| Integrity verify | 1s | Stream checksum, no timeout |
| Failover (total) | 30s | Escalate to operator |

### Idempotency Guarantees

| Operation | Idempotent? | Mechanism |
|-----------|-------------|-----------|
| `deploy_runtime(manifest)` | ✅ | Same manifest → same cluster state hash |
| `scale_workers(target=5)` | ✅ | Declarative — converges to target |
| `rollout_rollback(version)` | ✅ | Deterministic state reversal |
| `enqueue(task)` | ❌ | Each call creates unique msg_id |
| `acknowledge(msg_id)` | ✅ | Idempotent — second ack is no-op |
| `store_artifact(uri, payload)` | ✅ | Write-once, same payload → same checksum |
| `elect_leader(candidates)` | ✅ | Same candidates + term → same leader |

### Determinism Thresholds

| Aspect | Threshold | Enforcement |
|--------|-----------|-------------|
| Manifest hash deviation | 0% (strict) | Must match exactly |
| Target state hash | 0% (strict) | Must match exactly |
| Snapshot checksum | 0% (strict) | Must match exactly |
| Rollout behaviour | Deterministic | Same manifest → same strategy |
| Leader election result | Deterministic | Same votes → same leader |

### Rollback on Failure

| Failure Mode | Rollback Action | Queue Action |
|-------------|----------------|--------------|
| Deployment health check fails | Rollback to previous manifest | Enqueue `runtime.deployment.revert` |
| Canary error rate spike | Abort canary, route 100% to stable | Enqueue `runtime.deployment.abort` |
| Snapshot checksum mismatch | Block recovery, retry from source | Enqueue `runtime.recovery.retry` |
| Leader election timeout | Trigger re-election with backoff | Enqueue `runtime.failover.retry` |
| Queue overflow | Scale workers, throttle producers | Enqueue `runtime.scaling.urgent` |
| Artifact corruption | Re-store from build pipeline | Enqueue `runtime.storage.rebuild` |

---

## 6. Compliance Mapping Summary

| Component | LAW/RULE | Evidence |
|-----------|----------|----------|
| IKubernetesDeployer | LAW 1, 5, 11; RULE 3, 4 | §2 Flow 2, §5 Latency budgets |
| IDistributedQueue | LAW 1, 5, 11; RULE 2, 5 | §2 Flow 1, QueueMessage model |
| IHAOrchestrator | LAW 1, 5, 11, 20, 21, 22; RULE 3, 4, 5 | §2 Flow 3, HA SM, S1–S5 |
| IObjectStorage | LAW 1, 5, 11; RULE 1, 2 | §2 Flow 2, StorageRef model |
| HA State Machine | LAW 20, 21, 22; RULE 3, 5 | §3 HA SM, Guards S1–S5 |
| F2 Control Plane integration | LAW 5 | §2 Flow 2, ReconciliationLoop |
| F4 Observability hooks | LAW 5 | §4 Event Hooks, Correlation IDs |
| G5 Swarm integration | LAW 1, 5 | §2 Flow 1, mission_trace_id → infra_trace_id |
