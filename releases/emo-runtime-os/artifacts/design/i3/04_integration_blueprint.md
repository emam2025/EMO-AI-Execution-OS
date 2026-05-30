# Phase I3 — Production Reliability Integration Blueprint

## 1. Architecture Overview

The Production Reliability layer (I3) sits across I1 Production Infrastructure,
I2 Data Infrastructure, and F2 Control Plane, providing failover orchestration,
disaster recovery, rolling updates, and runtime migration. The recovery_trace_id
flows through every layer to guarantee full back-traceability (LAW 8).

```
                         ┌──────────────────────────────────────────────────┐
                         │               F2.ControlPlane                   │
                         │  ┌──────────────────────────────────────────┐   │
                         │  │ ReconciliationLoop HealthSupervisor       │   │
                         │  │ DeploymentRegistry ConfigStore           │   │
                         │  └──────────────────────────────────────────┘   │
                         └──────────────────────────────────────────────────┘
                                        │
         ┌──────────────────────────────┼──────────────────────────────┐
         │                              │                              │
         v                              v                              v
┌──────────────────┐          ┌──────────────────┐          ┌──────────────────┐
│ I3.Failover      │          │ I3.DR            │          │ I3.RollingUpdate │
│ Orchestrator     │◄────────►│ Recovery         │◄────────►│ Manager          │
│                  │          │ Manager          │          │                  │
│ trigger_failover │          │ capture_recovery │          │ prepare_canary   │
│ isolate_node     │          │ point            │          │ roll_forward     │
│ promote_replica  │          │ restore_from_    │          │ roll_back        │
│ verify_quorum    │          │ backup           │          │ monitor_health   │
└──────────────────┘          └──────────────────┘          └──────────────────┘
         │                              │                              │
         │                              │                              │
         v                              v                              v
┌─────────────────────────────────────────────────────────────────────────────┐
│                              I1.Infrastructure                              │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐               │
│  │ K8s Deployer   │  │ HAOrchestrator │  │ ObjectStorage  │               │
│  │ Queue          │  │ State Machine  │  │ Trace Correl.  │               │
│  └────────────────┘  └────────────────┘  └────────────────┘               │
└─────────────────────────────────────────────────────────────────────────────┘
         │                              │                              │
         v                              v                              v
┌─────────────────────────────────────────────────────────────────────────────┐
│                              I2.Data Infrastructure                         │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐               │
│  │ PostgreSQL     │  │ DistributedLog │  │ RuntimeAnalytics│               │
│  │ Manager (ACID) │  │ (Journal)      │  │ (DR Metrics)   │               │
│  └────────────────┘  └────────────────┘  └────────────────┘               │
└─────────────────────────────────────────────────────────────────────────────┘
         │                              │                              │
         v                              v                              v
┌─────────────────────────────────────────────────────────────────────────────┐
│                           F4.Observability                                  │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐               │
│  │ TraceCollector │  │ AlertRouter    │  │ TelemetryAgg.  │               │
│  └────────────────┘  └────────────────┘  └────────────────┘               │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Key principle:** All reliability operations are driven by the recovery_trace_id,
checksum-verified, and rollback-safe. The I3 layer orchestrates I1 and I2
components without duplicating their logic.

---

## 2. Data Flow: I3 → I1 → I2 → F2 → F4

### Flow 1: Failover Orchestration (I3.Failover → I1.HA → I2.PostgreSQL → F2)

```
I3.IFailoverOrchestrator.verify_quorum(cluster_id, nodes, expected_quorum,
                                       recovery_trace_id)
    │
    │  ┌── Safety Guard G-R2 ──────────────────────────────┐
    │  │  failure_confirmed_by >= 2 independent nodes ✓     │
    │  └────────────────────────────────────────────────────┘
    ▼
I3.IFailoverOrchestrator.isolate_node(cluster_id, failed_node_id,
                                      isolation_mode="fence", recovery_trace_id)
    │
    │  ┌── Safety Guard G-R5 ──────────────────────────────┐
    │  │  node_isolated + lease_revoked + traffic_drained ✓ │
    │  └────────────────────────────────────────────────────┘
    │
    ├── I1.HAOrchestrator.trigger_failover()
    │       └── I1 Queue.enqueue(topic="runtime.failover", priority=CRITICAL)
    │
    ├── I1.KubernetesDeployer.scale_workers(target=drain_failed_node)
    │
    ├── I2.PostgreSQLManager.execute_tx(
    │     queries=[{"sql": "UPDATE cluster_nodes SET status='isolated' ..."}],
    │     isolation_level="REPEATABLE_READ",
    │     data_trace_id=recovery_trace_id)
    │
    └── F4.Observability
            ├── AlertRouter: {severity: "critical", type: "NODE_ISOLATED"}
            └── TraceCollector: {recovery_trace_id, "i3.failover.isolate"}
```

### Flow 2: Replica Promotion (I3.Failover → I1.HA → F2)

```
I3.IFailoverOrchestrator.promote_replica(cluster_id, standby_node_id,
    quorum_votes=3, data_sync_lag_ms=120.0, recovery_trace_id)
    │
    │  ┌── Safety Guard G-R3 ──────────────────────────────────┐
    │  │  quorum_votes > total/2 (3 > 2.5) ✓                   │
    │  │  data_sync_lag < 500ms (120ms) ✓                      │
    │  │  standby_checksum matches primary ✓                   │
    │  │  lease_revoked_on_failed_node ✓                       │
    │  └────────────────────────────────────────────────────────┘
    │
    ├── I1.HAOrchestrator.elect_leader(candidates=[standby_node],
    │     infra_trace_id=recovery_trace_id)
    │       └── S1 Quorum Election Guard + H1->H2 transition
    │
    ├── I2.DistributedLog.append_entry(
    │     stream="runtime.execution",
    │     payload={action: "promote_replica", node: standby_node_id,
    │              term: new_term, recovery_trace_id},
    │     data_trace_id=recovery_trace_id)
    │
    ├── I2.RuntimeAnalytics.compute_throughput(window_id, metrics,
    │     data_trace_id=recovery_trace_id)
    │
    └── F4.Observability
            ├── AlertRouter: {severity: "info", type: "LEADER_PROMOTED"}
            └── TraceCollector: {recovery_trace_id, "i3.failover.promote"}
```

### Flow 3: Recovery Point Capture (I3.DR → I2.PostgreSQL → I2.Log → F4)

```
I3.IDisasterRecovery.capture_recovery_point(state_snapshot, journal_offset,
    isolation_context, recovery_trace_id)
    │
    │  state_hash = SHA-256(sorted_key_json(state_snapshot))
    │  combined_checksum = SHA-256(state_hash || journal_offset)
    │
    ├── I2.PostgreSQLManager.execute_tx(
    │     queries=[{"sql": "INSERT INTO recovery_points (...) VALUES (...)"}],
    │     isolation_level="SERIALIZABLE",
    │     data_trace_id=recovery_trace_id)
    │
    ├── I2.DistributedLog.append_entry(
    │     stream="audit.trail",
    │     payload={action: "recovery_point", point_id, state_hash,
    │              journal_offset, checksum, recovery_trace_id},
    │     data_trace_id=recovery_trace_id)
    │
    └── F4.Observability
            ├── TelemetryAggregator: {recovery_point_size, duration_ms}
            └── TraceCollector: {recovery_trace_id, "i3.dr.recovery_point"}
```

### Flow 4: DR Restore + Journal Replay (I3.DR → I2.Log → I2.PostgreSQL → F2 → F4)

```
I3.IDisasterRecovery.restore_from_backup(recovery_point_id, target_location,
    expected_checksum, recovery_trace_id)
    │
    │  ┌── Safety Guard G-R7 ────────────────────────────────┐
    │  │  combined_checksum matches ✓                         │
    │  │  journal_offset >= last_committed ✓                  │
    │  └──────────────────────────────────────────────────────┘
    │
    ├── I2.PostgreSQLManager.execute_tx(
    │     queries=[{sql: "RESTORE FROM recovery_point"}],
    │     isolation_level="SERIALIZABLE",
    │     data_trace_id=recovery_trace_id)
    │
    ├── I3.IDisasterRecovery.replay_journal(
    │     journal_source="i2.distributed_log",
    │     from_offset=recovery_point.journal_offset,
    │     to_offset=last_known_offset,
    │     recovery_trace_id)
    │       └── I2.DistributedLog.read_range(stream, from_offset, to_offset)
    │
    ├── I3.IDisasterRecovery.validate_checksum(
    │     data=restored_state,
    │     expected_checksum=recovery_point.combined_checksum,
    │     recovery_trace_id)
    │
    ├── F2.ControlPlane
    │       └── ReconciliationLoop verifies restored state
    │
    └── F4.Observability
            ├── AlertRouter: {severity: "info", type: "RESTORE_COMPLETED"}
            └── TraceCollector: {recovery_trace_id, "i3.dr.restore"}
```

### Flow 5: Rolling Update (I3.RollingUpdate → I1.K8s → F2 → F4)

```
I3.IRollingUpdateManager.prepare_canary(target_version="v2.0.0",
    canary_percent=10.0, compatibility_matrix={...}, recovery_trace_id)
    │
    │  ┌── Safety Guard G-U1 ────────────────────────────────┐
    │  │  compatibility_ok ✓  health_endpoint_configured ✓   │
    │  │  manifest_hash computed ✓                           │
    │  └──────────────────────────────────────────────────────┘
    │
    ├── I1.KubernetesDeployer.deploy_runtime(manifest=
    │     DeploymentManifest(runtime_version="v2.0.0", ...),
    │     infra_trace_id=recovery_trace_id)
    │       └── Deterministic Rollout Guard applied
    │
    ├── I3.IRollingUpdateManager.roll_forward(
    │     target_version="v2.0.0", strategy="canary",
    │     cluster_health={healthy: 5, degraded: 0}, recovery_trace_id)
    │
    ├── I3.IRollingUpdateManager.monitor_health(
    │     deployment_id, health_checks, recovery_trace_id)
    │
    ├── [on failure] I3.IRollingUpdateManager.roll_back(
    │     current="v2.0.0", previous="v1.0.0",
    │     reason="health_check_failure", recovery_trace_id)
    │
    └── F4.Observability
            ├── AlertRouter: {severity: "warning", type: "ROLLOUT_[PROGRESS/ROLLBACK]"}
            └── TraceCollector: {recovery_trace_id, "i3.update.rollout"}
```

### Flow 6: Runtime Migration (I3.Migrator → I1.K8s → I2 → F2 → F4)

```
I3.IRuntimeMigrator.dry_run_migration(source_backend="sqlite",
    target_backend="postgresql", compatibility_matrix={...}, recovery_trace_id)
    │
    │  ┌── Safety Guard G-M1 ────────────────────────────────┐
    │  │  dry_run_passed ✓  compatibility_ok ✓  issues empty ✓│
    │  └──────────────────────────────────────────────────────┘
    │
    ├── I3.IRuntimeMigrator.snapshot_state(
    │     source_backend="sqlite", tables=["executions", "state"],
    │     recovery_trace_id)
    │       └── snapshot_hash = SHA-256(sorted JSON of all rows)
    │
    ├── I3.IRuntimeMigrator.switch_over(
    │     target_backend="postgresql", snapshot_hash, strategy="shadow",
    │     recovery_trace_id)
    │       └── I2.DataMigrator.load_postgres(...)
    │
    ├── I3.IRuntimeMigrator.verify_post_migration(
    │     source_snapshot_hash, target_backend="postgresql",
    │     expected_checksum, recovery_trace_id)
    │       └── integrity_pct == 100% required
    │
    └── F4.Observability
            ├── AlertRouter: {severity: "info", type: "MIGRATION_[VERIFIED/FAILED]"}
            └── TraceCollector: {recovery_trace_id, "i3.migration"}
```

---

## 3. Correlation ID Propagation (LAW 5, LAW 8)

Every reliability operation carries a **recovery_trace_id** that flows across
all layers, ensuring full back-traceability from failover event through DR
restore to post-migration verification.

### ID Hierarchy

```
mission_trace_id (G5)
    └── infra_trace_id (I1) — one per deployment/queue operation
            └── data_trace_id (I2) — one per DB/log/analytics operation
                    └── recovery_trace_id (I3) — one per failover/DR/update/migration
                            ├── failover_id — one per failover sequence
                            ├── recovery_point_id — one per DR recovery point
                            ├── deployment_id — one per rolling update
                            └── migration_id — one per runtime migration
```

### Propagation Matrix

| Layer | ID Carried | Format | Reference |
|-------|-----------|--------|-----------|
| G5 SwarmCoordinator | mission_trace_id | `msn_<hex>` | `SwarmContext.mission_trace_id` |
| I1 Infrastructure | infra_trace_id | `infra_<hex>` | `QueueMessage.infra_trace_id` |
| I2 Data Infrastructure | data_trace_id | `data_<hex>` | `StorageConfig.data_trace_id` |
| I3 FailoverOrchestrator | recovery_trace_id | `rec_<hex>` | `FailoverPlan.recovery_trace_id` |
| I3 DisasterRecovery | recovery_trace_id | `rec_<hex>` | `RecoveryPoint.recovery_trace_id` |
| I3 RollingUpdateManager | recovery_trace_id | `rec_<hex>` | `UpdateStrategy.recovery_trace_id` |
| I3 RuntimeMigrator | recovery_trace_id | `rec_<hex>` | `MigrationManifest.recovery_trace_id` |
| F2 ControlPlane | recovery_trace_id | `rec_<hex>` | Reconciliation loop |
| F4 TraceCollector | recovery_trace_id | `rec_<hex>` | Span ID |

### Generation Rule

```python
def generate_recovery_trace_id(
    data_trace_id: str,
    operation_type: str,
) -> str:
    raw = f"{data_trace_id}:i3:{operation_type}:{time.time_ns()}"
    return f"rec_{hashlib.sha256(raw.encode()).hexdigest()[:24]}"
```

### Correlation Chain Example

```
msn_a1b2c3 (G5 mission_trace_id)
  └── infra_d4e5f6 (I1 infra_trace_id — from deployment)
        └── data_g7h8i9 (I2 data_trace_id — from PostgreSQL tx)
              └── rec_j0k1l2 (I3 recovery_trace_id — from failover)
                    ├── failover_id: "fail_001"
                    ├── recovery_point_id: "rp_abc"
                    ├── deployment_id: "dep_v2.0.0"
                    └── migration_id: "mig_sqlite_to_pg"
```

---

## 4. Event Hooks for Failover, DR, Update & Migration Reporting

### FailoverTriggered Hook
**Triggered when:** I3 FailoverOrchestrator initiates a failover sequence.

```yaml
hook: failover_triggered
payload:
  recovery_trace_id: "rec_j0k1l2"
  cluster_id: "cluster_prod"
  failed_node_id: "node_05"
  target_standby: "node_03"
  quorum_votes: 3
  total_nodes: 5
  data_sync_lag_ms: 120.0
  isolation_mode: "fence"
targets:
  - I1.HAOrchestrator.trigger_failover(cluster_id, node_05, ...)
  - I1.Queue.enqueue(topic="runtime.failover", priority=CRITICAL)
  - F4.AlertRouter.alert({severity: "critical", type: "FAILOVER_TRIGGERED"})
  - I2.DistributedLog.append_entry(stream="audit.trail", payload={...})
```

### RecoveryPointCreated Hook
**Triggered when:** A new DR recovery point is captured and verified.

```yaml
hook: recovery_point_created
payload:
  recovery_trace_id: "rec_m3n4o5"
  recovery_point_id: "rp_20260523_001"
  state_hash: "a1b2c3d4..."
  journal_offset: 1048576
  combined_checksum: "e5f6g7h8..."
  size_bytes: 5368709120
  timestamp_ns: 1716384000000000000
targets:
  - I2.PostgreSQLManager.execute_tx({sql: "INSERT INTO recovery_points ..."})
  - F4.AlertRouter.alert({severity: "info", type: "RECOVERY_POINT_CREATED"})
  - I2.DistributedLog.append_entry(stream="audit.trail", payload={...})
```

### UpdateRolledBack Hook
**Triggered when:** A rolling update or canary is rolled back.

```yaml
hook: update_rolled_back
payload:
  recovery_trace_id: "rec_p6q7r8"
  deployment_id: "dep_042"
  current_version: "v2.0.0"
  previous_version: "v1.0.0"
  rollback_reason: "health_check_failure"
  error_rate: 0.12
  latency_increase_pct: 75.0
  duration_ms: 45000.0
targets:
  - I1.KubernetesDeployer.rollout_rollback(target_version="v1.0.0")
  - F4.AlertRouter.alert({severity: "warning", type: "UPDATE_ROLLED_BACK"})
  - I2.DistributedLog.append_entry(stream="runtime.execution", payload={...})
```

### MigrationCompleted Hook
**Triggered when:** A runtime migration completes successfully.

```yaml
hook: migration_completed
payload:
  recovery_trace_id: "rec_s9t0u1"
  migration_id: "mig_023"
  source_backend: "sqlite"
  target_backend: "postgresql"
  snapshot_hash: "v2w3x4y5..."
  integrity_pct: 100.0
  duration_ms: 120000.0
  data_volume_bytes: 2147483648
targets:
  - F2.ControlPlane.update_schema_registry({backend: "postgresql"})
  - F4.AlertRouter.alert({severity: "info", type: "MIGRATION_COMPLETED"})
  - I2.DistributedLog.append_entry(stream="schema.migrations", payload={...})
```

### SplitBrainDetected Hook
**Triggered when:** Network partition or split-brain is suspected.

```yaml
hook: split_brain_detected
payload:
  recovery_trace_id: "rec_v2w3x4"
  cluster_id: "cluster_prod"
  conflicting_leaders: ["node_03", "node_07"]
  partition_nodes: ["node_03", "node_04", "node_05"]
  isolated_nodes: ["node_07", "node_08"]
  quorum_status: "lost"
targets:
  - I3.IFailoverOrchestrator.isolate_node(cluster_id, node_07, "fence", ...)
  - F4.AlertRouter.alert({severity: "critical", type: "SPLIT_BRAIN_DETECTED"})
  - I1.HAOrchestrator.trigger_failover(...)
  - I2.DistributedLog.append_entry(stream="audit.trail", payload={...})
```

### DRRestoreStarted Hook
**Triggered when:** A DR restore process begins.

```yaml
hook: dr_restore_started
payload:
  recovery_trace_id: "rec_a1b2c3"
  recovery_point_id: "rp_20260523_001"
  target_location: "postgresql://prod-restore/db"
  expected_checksum: "d4e5f6g7..."
  journal_replay_from: 1048576
  journal_replay_to: 2097152
targets:
  - I2.PostgreSQLManager.execute_tx({sql: "BEGIN RESTORE ..."})
  - F4.AlertRouter.alert({severity: "warning", type: "DR_RESTORE_STARTED"})
```

---

## 5. Acceptance Criteria

### Latency Budgets

| Operation | Budget | Action on Exceed |
|-----------|--------|-----------------|
| Failover trigger (verify_quorum + isolate) | 5s | Escalate to operator |
| Node isolation via fencing | 2s | Retry with stronger isolation |
| Replica promotion | 3s | Timeout, re-election with backoff |
| State sync after promotion | 10s | Fallback to DR restore |
| Recovery point capture (1GB state) | 30s | Split into smaller snapshots |
| Restore from backup (10GB) | 120s | Stream restore, no timeout |
| Journal replay (1M entries) | 60s | Parallel replay with offset sharding |
| Checksum validation (10GB) | 30s | Stream hashing |
| Canary preparation | 10s | Abort, report compatibility timeout |
| Roll forward (per 10 pods) | 30s | Abort, trigger rollback |
| Roll back (per 10 pods) | 30s | Escalate if rollback fails |
| Health monitor check | 500ms | Degrade health status |
| Migration dry-run | 60s | Report timeout, suggest capacity review |
| Migration switch-over | 5s | Abort switch, preserve source |
| Post-migration verify (1M rows) | 30s | Stream verification |

### Idempotency Guarantees

| Operation | Idempotent? | Mechanism |
|-----------|-------------|-----------|
| `trigger_failover(cluster_id, failed_node)` | ❌ | Each call creates unique failover_id |
| `isolate_node(node_id, mode)` | ✅ | Same node + mode -> same fence state |
| `promote_replica(standby_id, ...)` | ❌ | Each call creates unique promotion term |
| `verify_quorum(cluster_id, nodes)` | ✅ | Same nodes -> same quorum result |
| `capture_recovery_point(state, offset)` | ✅ | Same state + offset -> same state_hash |
| `restore_from_backup(point_id)` | ✅ | Same point_id -> same restored state |
| `validate_checksum(data, checksum)` | ✅ | Same data -> same checksum result |
| `replay_journal(source, from, to)` | ✅ | Same offsets -> same replay state |
| `prepare_canary(version, pct, matrix)` | ✅ | Same inputs -> same manifest_hash |
| `roll_forward(version, strategy, health)` | ✅ | Same inputs -> same rollout decision |
| `roll_back(current, previous, reason)` | ✅ | Same versions -> same manifest hash |
| `monitor_health(deployment_id)` | ✅ | Same idempotent health check |
| `dry_run_migration(source, target, matrix)` | ✅ | Same inputs -> same dry-run result |
| `snapshot_state(source, tables)` | ✅ | Same source -> same snapshot_hash |
| `switch_over(target, snapshot_hash, strategy)` | ❌ | Single-use switch-over |
| `verify_post_migration(source_hash, ...)` | ✅ | Same data -> same verification result |

### Zero-Data-Loss Thresholds

| Aspect | Threshold | Enforcement |
|--------|-----------|-------------|
| Data sync lag for promotion | < 500ms | G-R3 blocks if exceeded |
| Recovery point checksum deviation | 0% (strict) | G-R7 blocks if mismatch |
| Restore checksum deviation | 0% (strict) | G-R8 blocks if mismatch |
| Journal replay consistency | 100% (no gaps) | G-R8 requires consistency_ok |
| Migration integrity | 100% | G-M1, G-M2 require full match |
| Canary error rate increase | < 5% above baseline | G-U2 triggers rollback at 5% |
| Rollback data preservation | Full | RULE 5 — no destructive rollback |

### Rollback on Failure

| Failure Mode | Rollback Action | Log Action |
|-------------|----------------|------------|
| Quorum check fails (>50% nodes unreachable) | Block promotion, preserve leader | Append `runtime.failover` with quorum_failure |
| Node isolation fails | Retry with stronger isolation mode | Append `runtime.failover` with isolation_retry |
| Replica sync lag > 500ms | Block promotion, wait for sync | Append `runtime.failover` with sync_lag_exceeded |
| State sync after promotion fails | Fallback to DR restore from recovery point | Append `runtime.failover` with sync_failed |
| Recovery point checksum mismatch | Discard point, re-capture | Append `audit.trail` with checksum_failure |
| Restore checksum mismatch | Abort restore, alert operator | Append `audit.trail` with restore_checksum_failure |
| Journal replay inconsistency | Abort replay, escalate | Append `audit.trail` with replay_inconsistent |
| Canary health check fails | Rollback to previous version | Append `runtime.execution` with canary_rollback |
| Error rate spike during rollout | Abort rollout, full rollback | Append `runtime.execution` with error_spike_rollback |
| Migration compatibility fails | Block migration, preserve source | Append `schema.migrations` with compatibility_failure |
| Migration switch-over fails | Rollback to source backend | Append `schema.migrations` with switch_failed |
| Post-migration verification fails | Rollback, preserve source data | Append `schema.migrations` with verification_failure |

---

## 6. Compliance Mapping Summary

| Component | LAW/RULE | Evidence |
|-----------|----------|----------|
| IFailoverOrchestrator | LAW 8, 20, 21, 22; RULE 3, 4 | §2 Flow 1-2, G-R1-G-R6 |
| IDisasterRecovery | LAW 8, 11; RULE 1, 2, 5 | §2 Flow 3-4, G-R7-G-R8 |
| IRollingUpdateManager | LAW 3, 8, 20; RULE 1, 3, 5 | §2 Flow 5, G-U1-G-U2, Rollout Guard |
| IRuntimeMigrator | LAW 3, 8, 11; RULE 1, 2, 4 | §2 Flow 6, G-M1-G-M2 |
| I1 HAOrchestrator integration | LAW 20, 21, 22; RULE 3, 4 | §2 Flow 1-2, S1-S5 guards extended |
| I2 Data integration | LAW 5, 8, 14; RULE 1, 2 | §2 Flow 3-4, data_trace_id -> recovery_trace_id |
| F2 Control Plane integration | LAW 5 | §2 Flow 1-6, ReconciliationLoop |
| F4 Observability hooks | LAW 5, 8 | §4 Event Hooks, Correlation IDs |
| recovery_trace_id propagation | LAW 5, LAW 8 | §3 Correlation ID Hierarchy |
| Deterministic Rollout Guard | LAW 3, RULE 1 | §5 Rollout Decision Table |
