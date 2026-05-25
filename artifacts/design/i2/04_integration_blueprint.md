# Phase I2 — Data Infrastructure Integration Blueprint

## 1. Architecture Overview

The Data Infrastructure (I2) sits between the I1 Production Infrastructure
and the F2 Control Plane / F4 Observability layers. PostgreSQL provides
durable state, the Distributed Log provides append-only event streaming,
and Analytics provides real-time monitoring.

```
I1.KubernetesDeployer ──> I2.PostgreSQLManager ──> F2.ControlPlane
       │                        │                        │
       │                        │                        │
       v                        v                        v
 I1.ObjectStorage ──> I2.DistributedLog ──> I2.RuntimeAnalytics
 (Artifacts)          (Append-only log)     (Throughput, Anomalies)
                              │
                              v
                         F4.Observability
                         (TraceCollector,
                          AlertRouter,
                          TelemetryAggregator)
```

**Key principle:** All data operations are transactional, idempotent, and
fully observable. The Distributed Log decouples I1 infrastructure events
from F4 analytics. The PostgreSQL Manager enforces ACID guarantees with
quorum-based replication.

---

## 2. Data Flow: I1 → I2 → F2 → F4

### Flow 1: Persistent State (I1.K8s → I2.PostgreSQL → F2.ControlPlane)

```
I1.KubernetesDeployer.deploy_runtime(manifest, infra_trace_id)
    │
    │  Persist deployment state
    ▼
I2.PostgreSQLManager.execute_tx([
    {"sql": "INSERT INTO deployments (...) VALUES (...)",
     "params": [deployment_id, runtime_version, infra_trace_id]}
], isolation_level="READ_COMMITTED", data_trace_id=infra_trace_id)
    │
    │  ┌── ACID Guards ──────────────────────────────┐
    │  │  G1: connection_acquired ✅                  │
    │  │  G2: isolation_level ✅                      │
    │  │  G3: partition_key ✅                        │
    │  └──────────────────────────────────────────────┘
    │
    ├── I2.DistributedLog.append_entry(
    │     stream="db.changes",
    │     payload={action: "deploy", deployment_id, infra_trace_id},
    │     data_trace_id=infra_trace_id)
    │
    ├── F2.ControlPlane.ReconciliationLoop
    │       └── reads deployment state from PostgreSQL
    │
    └── F4.Observability
            ├── TraceCollector: {data_trace_id, "db.insert", table, rows}
            └── AlertRouter: [if tx fails] → "TX_FAILED"
```

### Flow 2: Log Replication & Analytics (I2.Log → I2.Analytics → F4)

```
I2.DistributedLog.append_entry(stream="runtime.execution",
    payload={dag_id, action, duration_ms}, data_trace_id)
    │
    ├── I2.DistributedLog.sync_replicas(stream, [node2, node3],
    │     data_trace_id)
    │       └── G4: quorum_ack validation
    │
    ├── I2.RuntimeAnalytics.compute_throughput(
    │     window_id, metrics=[...], data_trace_id)
    │       └── Returns: operations_per_sec, p99_latency_ms, cost_estimate
    │
    ├── I2.RuntimeAnalytics.detect_anomalies(
    │     window_id, metrics, baselines, data_trace_id)
    │       └── Returns: anomaly_count, critical_count
    │
    └── F4.Observability
            ├── TelemetryAggregator: {throughput, latency, cost}
            ├── AlertRouter: [if anomaly detected] → "ANOMALY_DETECTED"
            └── TraceCollector: log span for analytics window
```

### Flow 3: Data Migration (SQLite → I2.PostgreSQL → I2.Log)

```
I2.DataMigrator.extract_legacy_sqlite(sqlite_path, tables, data_trace_id)
    │
    │  snapshot_hash computed (RULE 1)
    ▼
I2.DataMigrator.transform_schema(sqlite_schema, target_schema,
    mapping_rules, data_trace_id)
    │
    │  mapping_hash computed, DAG integrity verified (LAW 14)
    ▼
I2.DataMigrator.load_postgres(transformed_data, conn_config,
    batch_size, data_trace_id)
    │
    │  ┌── Migration Guard ─────────────────────────────────┐
    │  │  snapshot_hash matches? ✅                          │
    │  │  mapping_hash deterministic? ✅                     │
    │  │  row_count matches expected? ✅                     │
    │  └─────────────────────────────────────────────────────┘
    │
    ├── I2.DistributedLog.append_entry(
    │     stream="schema.migrations",
    │     payload={migration_id, tables, rows, data_trace_id})
    │
    ├── F2.ControlPlane
    │       └── updates schema registry from migration
    │
    └── I2.PostgreSQLManager.verify_integrity(
          target_table, expected_hash, data_trace_id)
            └── integrity_ok: true/false
```

---

## 3. Correlation ID Propagation (LAW 5)

Every data operation carries a **data_trace_id** that flows across all
layers, ensuring full back-traceability from infrastructure event through
database transaction to analytics dashboard.

### ID Hierarchy

```
mission_trace_id (G5)
    └── infra_trace_id (I1) — one per deployment/queue operation
            └── data_trace_id (I2) — one per DB/log/analytics operation
                    ├── tx_id — one per PostgreSQL transaction
                    ├── entry_id — one per Log entry
                    ├── window_id — one per Analytics window
                    ├── migration_id — one per Migration
                    └── partition_name — target partition
```

### Propagation Matrix

| Layer | ID Carried | Format | Reference |
|-------|-----------|--------|-----------|
| G5 SwarmCoordinator | mission_trace_id | `msn_<hex>` | `SwarmContext.mission_trace_id` |
| I1 KubernetesDeployer | infra_trace_id | `infra_<hex>` | `DeploymentManifest.infra_trace_id` |
| I2 PostgreSQLManager | data_trace_id | `data_<hex>` | `StorageConfig.data_trace_id` |
| I2 DistributedLog | data_trace_id | `data_<hex>` | `LogEntry.data_trace_id` |
| I2 RuntimeAnalytics | data_trace_id | `data_<hex>` | `AnalyticsWindow.data_trace_id` |
| I2 DataMigrator | data_trace_id | `data_<hex>` | `MigrationManifest.data_trace_id` |
| F2 ControlPlane | data_trace_id | `data_<hex>` | Reconciliation loop |
| F4 TraceCollector | data_trace_id | `data_<hex>` | Span ID |

### Generation Rule

```python
def generate_data_trace_id(infra_trace_id: str, operation_type: str) -> str:
    raw = f"{infra_trace_id}:i2:{operation_type}:{time.time_ns()}"
    return f"data_{hashlib.sha256(raw.encode()).hexdigest()[:24]}"
```

---

## 4. Event Hooks for Drift & Failure Reporting

### SchemaDrift Hook
**Triggered when:** Table schema does not match expected migration version.

```yaml
hook: schema_drift
payload:
  data_trace_id: "data_abc123"
  table_name: "deployments"
  expected_version: 7
  actual_version: 5
  drift_columns: ["runtime_version", "worker_count"]
targets:
  - I2.PostgreSQLManager.migrate_schema(migration_id, sql, data_trace_id)
  - F4.AlertRouter.alert({severity: "high", type: "SCHEMA_DRIFT"})
  - I2.DistributedLog.append_entry(stream="audit.trail", payload={...})
```

### LogReplicationLag Hook
**Triggered when:** Replica lag exceeds critical threshold.

```yaml
hook: log_replication_lag
payload:
  data_trace_id: "data_def456"
  stream: "runtime.execution"
  node: "node_05"
  lag_ms: 15000
  threshold_ms: 10000
targets:
  - I2.DistributedLog.sync_replicas(stream, [node_05], data_trace_id)
  - F4.AlertRouter.alert({severity: "warning", type: "REPLICATION_LAG"})
  - F4.TelemetryAggregator.report({replication_lag_ms: 15000})
```

### PartitionOverflow Hook
**Triggered when:** Any partition exceeds storage threshold.

```yaml
hook: partition_overflow
payload:
  data_trace_id: "data_ghi789"
  table_name: "deployments"
  partition_name: "deployments_p2026_05"
  size_bytes: 10737418240  # 10GB
  threshold_bytes: 8589934592  # 8GB
targets:
  - I2.PostgreSQLManager.partition_table(table, key, "range", data_trace_id)
  - F4.AlertRouter.alert({severity: "medium", type: "PARTITION_OVERFLOW"})
```

### MigrationFailure Hook
**Triggered when:** Data migration fails at any stage.

```yaml
hook: migration_failure
payload:
  data_trace_id: "data_jkl012"
  migration_id: "mig_007"
  stage: "loading"
  error: "constraint violation on table deployments"
  rows_loaded: 15000
  rows_expected: 15234
targets:
  - I2.DataMigrator.verify_migration(source_hash, table, count, data_trace_id)
  - F4.AlertRouter.alert({severity: "critical", type: "MIGRATION_FAILURE"})
  - I2.DistributedLog.append_entry(stream="schema.migrations",
      payload={migration_id, status: "failed", error})
```

---

## 5. Acceptance Criteria

### Latency Budgets

| Operation | Budget | Action on Exceed |
|-----------|--------|-----------------|
| PostgreSQL connection acquire | 500ms | Queue and retry with backoff |
| Schema migration (10 tables) | 30s | Timeout, mark as FAILED |
| Partition table (1M rows) | 60s | Timeout, alert partition_overflow |
| Execute tx (simple) | 200ms | Retry once, then rollback |
| Execute tx (complex) | 5s | Timeout, trigger rollback |
| Verify integrity (1M rows) | 10s | Stream checksum, no timeout |
| Log append | 50ms | Retry once, then fail |
| Log read range (100 entries) | 100ms | Return partial results |
| Log compaction (1GB) | 30s | Timeout, retry in next window |
| Replica sync (1000 entries) | 5s | Log warning, continue async |
| Throughput computation (1hr window) | 10s | Return partial metrics |
| Anomaly detection (1000 metrics) | 5s | Skip window, alert |
| Dashboard publish | 2s | Cache stale data |

### Idempotency Guarantees

| Operation | Idempotent? | Mechanism |
|-----------|-------------|-----------|
| `migrate_schema(migration_id, ...)` | ✅ | Same migration_id → skip if applied |
| `partition_table(table, key, ...)` | ✅ | Same params → same partitions |
| `execute_tx(queries, ...)` | ❌ | Each call creates unique tx_id |
| `append_entry(stream, payload, ...)` | ❌ | Each call creates unique entry_id |
| `compact_segments(stream, ...)` | ✅ | Idempotent — second call is no-op |
| `sync_replicas(stream, nodes)` | ✅ | Convergent — syncs to latest offset |
| `compute_throughput(window, metrics)` | ✅ | Same metrics → same result |
| `detect_anomalies(window, metrics, baselines)` | ✅ | Same inputs → same anomalies |
| `extract_legacy_sqlite(path, tables)` | ✅ | Same db → same snapshot_hash |
| `load_postgres(data, config)` | ❌ | Duplicate rows prevented by unique keys |

### ACID Compliance Thresholds

| Aspect | Threshold | Enforcement |
|--------|-----------|-------------|
| Isolation level requirement | Must be explicitly set | G2 guard blocks if missing |
| Quorum majority | votes > total / 2 | G4 guard blocks if insufficient |
| Partition key | Must be non-null and valid | G3 guard blocks if invalid |
| data_trace_id | Must be non-empty | G1, G7 guards block if missing |
| Integrity checksum | 0% deviation | DGM blocks on checksum mismatch |
| Deadlock retries | Max 3 | G6 guard blocks after 3 |
| Replica timeout | 5s | G8 guard triggers rollback |

### Rollback on Failure

| Failure Mode | Rollback Action | Log Action |
|-------------|----------------|------------|
| Transaction query fails | Rollback to savepoint | Append `db.changes` with status rolled_back |
| Constraint violation | Rollback, report violation | Append `audit.trail` with constraint_details |
| Replica ack timeout | Rollback if fallback_to_rollback | Append `runtime.execution` with replication_failure |
| Deadlock detected | Retry with backoff (max 3) | Append `runtime.execution` with deadlock_event |
| Migration checksum mismatch | Abort migration, preserve source | Append `schema.migrations` with checksum_failure |
| Partition overflow | Create new partition, rebalance | Append `db.changes` with partition_created |
| Analytics timeout | Skip window, report timeout | Append `analytics.metrics` with window_skipped |

---

## 6. Compliance Mapping Summary

| Component | LAW/RULE | Evidence |
|-----------|----------|----------|
| IPostgreSQLManager | LAW 5, 11, 14; RULE 1, 2, 3 | §2 Flow 1, ACID Guards G1–G8 |
| IDistributedLog | LAW 5, 11, 21; RULE 2, 4, 5 | §2 Flow 2, LogEntry model, ReplicaSync |
| IRuntimeAnalytics | LAW 5, 15, 16; RULE 1, 2, 3 | §2 Flow 2, AnalyticsWindow, AnomalyRecord |
| IDataMigrator | LAW 5, 11, 14; RULE 1, 2, 5 | §2 Flow 3, MigrationManifest, DGM |
| ACID State Machine | LAW 14, 20, 21; RULE 3, 4, 5 | §3 Transitions A1–A8, Guards G1–G8 |
| I1 K8s integration | LAW 5 | §2 Flow 1, infra_trace_id → data_trace_id |
| F2 Control Plane integration | LAW 5 | §2 Flow 1, ReconciliationLoop reads PG |
| F4 Observability hooks | LAW 5 | §4 Event Hooks, Correlation IDs |
