# Phase J3 — Integration Blueprint: J3 / I1 / I2 / J2 / F4

## Overview

Defines the data flow, correlation strategy, event hooks, and acceptance
criteria for integrating the J3 Production Readiness Layer with existing
I1 K8s Infrastructure, I2 PostgreSQL Storage, J2 Enterprise Tenant Router,
and F4 Observability.

Ref: ROADMAP 🔟 FINAL DELIVERY STAGE
Ref: DEVELOPER.md §15.13 (Chaos Engineering), §16 (Production Readiness)
Ref: Canon LAW 3, 5, 8, 11, 20-22, RULE 1-5
Ref: artifacts/design/j3/protocols/01_readiness_protocols.py
Ref: artifacts/design/j3/models/02_chaos_and_load_models.py
Ref: artifacts/design/j3/03_chaos_recovery_machine.md

---

## 1. Data Flow Diagram

```
┌──────────────┐
│              │
│  J3.Chaos   │───── IChaosInjector ────► I1.K8s (worker kill,
│  Injector   │                             network partition,
│              │                             resource pressure)
└──────┬───────┘
       │
       │ ILoadOrchestrator
       ▼
┌──────────────┐
│  J3.Load    │───── generate_concurrent_dags() ────► F1 Runtime API
│  Orchestrator│      apply_resource_pressure() ────► I1.K8s (CPU/Mem/IO)
│              │      measure_p99_latency()    ────► F1 Execution Metrics
└──────┬───────┘
       │
       │ StabilityMetric
       ▼
┌──────────────┐
│  J3.Stability│───── evaluate_throughput_stability()
│  Validator   │      check_data_integrity_post_chaos() ────► I2.PostgreSQL
│              │      verify_rollback_safety()      ────► I1.K8s (state compare)
│              │      publish_readiness_report()    ────► F4.Observability
└──────┬───────┘
       │
       │ ReadinessReport
       ▼
┌──────────────┐
│  J3.Cert     │───── load_canon_baseline()        ────► I1.ObjectStorage
│  Gate        │      run_validation_suite()        ────► All J3 components
│              │      compute_final_score()
│              │      freeze_production_snapshot()  ────► I1.ObjectStorage
└──────┬───────┘
       │
       ▼
┌──────────────────────────────────────────────────────┐
│                  J2.TenantRouter                      │
│  (scope verification for multi-tenant chaos targets)  │
│  Guard: J2 G-L1 enforced before cross-tenant chaos   │
└──────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────┐
│              F4 Observability (Events Bus)            │
│  ChaosInjectFailed | RecoveryTimeout                 │
│  LoadOscillationDetected | CertificationBlocked      │
│  ProductionSnapshotFrozen                            │
└──────────────────────────────────────────────────────┘
```

### Flow Sequence

```
J3.ChaosInjector → I1.K8s            (inject fault)
         ↓
J3.LoadOrchestrator → F1 Runtime    (generate concurrent load)
         ↓
J3.LoadOrchestrator → I1.K8s        (apply resource pressure)
         ↓
J3.StabilityValidator → I2.PostgreSQL (check data integrity post-chaos)
         ↓
J3.StabilityValidator → F4           (publish readiness event)
         ↓
J3.CertificationGate → I1.ObjectStorage (freeze production snapshot)
         ↓
        F4 Observability collects all events + metrics
```

---

## 2. Correlation ID Strategy: readiness_trace_id

### Hierarchy

The `readiness_trace_id` flows through all layers, with each component
extending the trace chain:

```
J3.Initiator (CLI/API trigger)
  │
  ├── readiness_trace_id = "rdns_" + SHA-256(session + ts + scenario_id)[:28]
  │
  ▼
J3.IChaosInjector
  │
  ├── Extends: chaos_trace = readiness_trace_id + ":chaos:" + injection_id
  │
  ▼
J3.ILoadOrchestrator
  │
  ├── Extends: load_trace = readiness_trace_id + ":load:" + profile_id
  │
  ▼
J3.IStabilityValidator
  │
  ├── Extends: stability_trace = readiness_trace_id + ":stability:" + metric_id
  │
  ▼
J3.ICertificationGate
  │
  ├── Extends: cert_trace = readiness_trace_id + ":cert:" + report_id
  │
  ▼
I1 ObjectStorage / I2 PostgreSQL
  │
  ├── readiness_trace_id stored in all artifact metadata
  │
  ▼
F4 Observability
  │
  └── Full trace chain stored; any segment is back-traceable to root
```

### Propagation Rules (P-R1–P-R6)

| ID | Rule | Enforced By |
|----|------|-------------|
| P-R1 | Every J3 protocol method MUST accept `readiness_trace_id: str` as parameter | Protocol signature |
| P-R2 | Every J3 method return MUST include `trace_id` in its result dict | Protocol return spec |
| P-R3 | When calling another J3 component, forward the full `readiness_trace_id` chain | Integration code |
| P-R4 | When calling I1, I2, or F4, include `readiness_trace_id` in payload metadata | Integration code |
| P-R5 | readiness_trace_id MUST be non-empty (min 8 chars) — validated at entry point | RULE 2 |
| P-R6 | readiness_trace_id MUST be logged in every chaos execution log entry | IChaosInjector |

---

## 3. Event Hooks (H1–H10)

### Published Event Topics

| ID | Topic | Publisher | Payload | Trigger |
|----|-------|-----------|---------|---------|
| H1 | `readiness.chaos.injected` | IChaosInjector | injection_id, target_service, fault_type, duration_sec, expected_recovery_sec, trace_id | On inject_*() success |
| H2 | `readiness.chaos.injection_blocked` | IChaosInjector | target_service, blocked_by, pre_health_score, trace_id | G-C1 violation |
| H3 | `readiness.chaos.recovery_started` | IChaosInjector | injection_id, recovery_strategy, trace_id | restore_baseline() called |
| H4 | `readiness.chaos.recovery_failed` | IChaosInjector | injection_id, violated_guards, data_sync_lag, p99_ms, trace_id | G-C3 violation → ROLLED_BACK |
| H5 | `readiness.chaos.escalated` | IChaosInjector | injection_id, degradation_metric, cascade_detected, trace_id | G-C2 violation → ESCALATED |
| H6 | `readiness.load.started` | ILoadOrchestrator | profile_id, concurrent_users, dags_per_second, duration_sec, trace_id | On generate_concurrent_dags() |
| H7 | `readiness.load.oscillation_detected` | ILoadOrchestrator | oscillation_score, peak_count, metric_timeseries_sample, trace_id | detect_oscillation() flagged |
| H8 | `readiness.stability.report_published` | IStabilityValidator | report_id, chaos_pass, load_pass, integrity_pass, final_score, grade, trace_id | publish_readiness_report() |
| H9 | `readiness.certification.blocked` | ICertificationGate | report_id, blocked_by, final_score, grade, trace_id | compute_final_score() grade F |
| H10 | `readiness.certification.snapshot_frozen` | ICertificationGate | snapshot_id, storage_ref, grade, included_artifacts, trace_id | freeze_production_snapshot() completed |

### Event Bus Integration

All hooks publish to F4 event bus. The event format follows `ExecutionEvent`
from `core.models.events`:

```python
ExecutionEvent(
    event_id=f"rdns_{int(time.time() * 1000000)}",
    event_type="STATE_TRANSITION",
    timestamp=time.time(),
    source="J3ProductionReadiness",
    payload={
        "action": "ChaosInjected",
        "topic": "readiness.chaos.injected",
        "injection_id": "...",
        "readiness_trace_id": "...",
        # additional context
    },
)
```

---

## 4. I1 Infrastructure Integration (K8s Worker / Network / Storage)

### I1 Services Consumed

| Service | Purpose | J3 Protocol Using It |
|---------|---------|---------------------|
| I1.K8s Worker Manager | Kill workers, inject pod failures, monitor health | IChaosInjector |
| I1.K8s Network Policy | Inject network partitions, connection drops | IChaosInjector |
| I1.ObjectStorage | Store readiness reports, production snapshots, baseline configs | IStabilityValidator, ICertificationGate |
| I1.Metrics Collector | Collect CPU/memory/IO pressure metrics | ILoadOrchestrator |

### Chaos Injection Data Flow

```
J3.IChaosInjector.inject_network_partition()
  → 1. Capture baseline health snapshot (pre-fault)
  → 2. Apply I1.K8s NetworkPolicy to isolate target service
  → 3. Monitor degradation via I1.MetricsCollector
  → 4. Auto-recover: remove I1.K8s NetworkPolicy
  → 5. Verify: compare post-recovery metrics to baseline

J3.IChaosInjector.kill_worker()
  → 1. Capture baseline pod state (replicas, ready count)
  → 2. Scale down / delete pod via I1.K8s Worker Manager
  → 3. Monitor auto-scaling recovery
  → 4. Verify: replica count restored, ready count matches baseline
```

### Baseline Storage

| Artifact | Storage Path Pattern | I1 Service |
|----------|---------------------|------------|
| Pre-fault health snapshot | `chaos/{scenario_id}/baseline_{timestamp}.json` | ObjectStorage |
| Post-recovery health snapshot | `chaos/{scenario_id}/post_recovery_{timestamp}.json` | ObjectStorage |
| Readiness report | `readiness/reports/{report_id}.json` | ObjectStorage |
| Production snapshot | `readiness/snapshots/{snapshot_id}/` | ObjectStorage |
| Canon baseline config | `readiness/baseline/canon_config_{version}.json` | ObjectStorage |

---

## 5. I2 PostgreSQL Integration (Data Integrity Checks)

### I2 Services Consumed

| Service | Purpose | J3 Protocol Using It |
|---------|---------|---------------------|
| I2.PostgreSQL Connection Pool | Query tables for integrity checks after chaos | IStabilityValidator |
| I2.PostgreSQL Replication Monitor | Verify replication lag < 500ms post-failover | IStabilityValidator |
| I2.PostgreSQL Checksum Utility | Compute table checksums for data integrity | IStabilityValidator |

### Data Integrity Check Flow

```
J3.IStabilityValidator.check_data_integrity_post_chaos()
  → 1. For target_service == 'postgres':
  →    a. Query row count for critical tables
  →    b. Compute SHA-256 checksum of table contents
  →    c. Compare against pre-fault checksum (stored in I1)
  →    d. Check replication lag (replay_lag < 500ms)
  →    e. Verify constraint integrity (no orphaned rows)
  → 2. For target_service == 'redis':
  →    a. Verify key count matches pre-fault baseline
  →    b. Verify TTL integrity (no unexpected expirations)
  → 3. Return integrity_verified + detailed check results
```

---

## 6. J2 Enterprise Integration (Multi-Tenant Chaos Boundaries)

### J2 Services Consumed

| J2 Service | Purpose | Integration Point |
|------------|---------|-------------------|
| J2.TenantRouter.validate_tenant_scope | Verify chaos target is within tenant boundary | IChaosInjector before injection |
| J2.IComplianceAuditor.collect_audit_trail | Log chaos operations per tenant | IChaosInjector post-injection |

### Multi-Tenant Chaos Rules

1. **Chaos injection is ALWAYS scoped to a single tenant's boundary.**
   - Before any chaos injection, `J2.TenantRouter.validate_tenant_scope()` is called to verify the target service is within the tenant's isolation boundary.
   - Cross-tenant chaos injection is BLOCKED by J2 G-L1 (shared_resource_flag + scope_verified).
   - If the target service is shared across tenants, `scope_verified` must be True AND the target isolation policy must not be STRICT.

2. **readiness_trace_id chains to enterprise_trace_id.**
   - When chaos involves a J2 tenant, the readiness_trace_id is appended to the enterprise_trace_id:
     `enterprise_trace_id + ":rdns:" + readiness_trace_id`
   - This preserves the J2 → J3 audit trail.

3. **J3 Compliance Audit uses J2 Auditor.**
   - All chaos operations within a tenant boundary are logged via `J2.IComplianceAuditor.collect_audit_trail()`.
   - The audit entry carries both `enterprise_trace_id` (tenant-scoped) and `readiness_trace_id` (chaos-scoped).

---

## 7. F4 Observability Integration

### Metrics

| Metric Name | Type | Source | Labels |
|-------------|------|--------|--------|
| `readiness.chaos.injections_total` | Counter | IChaosInjector | target_service, fault_type, severity |
| `readiness.chaos.injection_blocked_total` | Counter | IChaosInjector | target_service, blocked_by |
| `readiness.chaos.recovery_time_ms` | Histogram | IChaosInjector | target_service, fault_type |
| `readiness.chaos.recovery_slo_met` | Gauge | IChaosInjector | target_service (1=met, 0=missed) |
| `readiness.chaos.escalations_total` | Counter | IChaosInjector | target_service, reason |
| `readiness.load.concurrent_dags` | Gauge | ILoadOrchestrator | profile_id |
| `readiness.load.p99_ms` | Gauge | ILoadOrchestrator | profile_id |
| `readiness.load.p999_ms` | Gauge | ILoadOrchestrator | profile_id |
| `readiness.load.throughput_ops_sec` | Gauge | ILoadOrchestrator | profile_id |
| `readiness.load.error_rate_pct` | Gauge | ILoadOrchestrator | profile_id |
| `readiness.load.oscillation_score` | Gauge | ILoadOrchestrator | profile_id |
| `readiness.stability.integrity_check_total` | Counter | IStabilityValidator | target_service, result |
| `readiness.stability.reports_total` | Counter | IStabilityValidator | grade |
| `readiness.certification.score` | Gauge | ICertificationGate | grade |
| `readiness.certification.blocked_total` | Counter | ICertificationGate | blocked_by |
| `readiness.certification.snapshot_frozen_total` | Counter | ICertificationGate | grade |

### Alerts

| Condition | Severity | Alert Name |
|-----------|----------|------------|
| Recovery time > expected_recovery_sec | critical | `ReadinessRecoverySLOMissed` |
| Chaos injection block rate > 2 in 5min | warning | `ReadinessHighInjectionBlockRate` |
| Escalation > 1 in 10min | critical | `ReadinessChaosEscalation` |
| Load oscillation score > 0.3 | warning | `ReadinessLoadOscillationDetected` |
| P99 latency > 200ms during load | warning | `ReadinessHighP99Latency` |
| Data integrity check failed post-chaos | critical | `ReadinessDataIntegrityFailure` |
| Certification blocked (grade F) | critical | `ReadinessCertificationBlocked` |

---

## 8. Acceptance Criteria

### Latency Budgets

| Operation | Budget | Measured At |
|-----------|--------|-------------|
| Inject fault (any type) | ≤ 100ms | IChaosInjector |
| Restore baseline | ≤ 200ms | IChaosInjector |
| Generate 100 concurrent DAGs | ≤ 2s | ILoadOrchestrator |
| Apply resource pressure | ≤ 500ms | ILoadOrchestrator |
| Measure p99 latency (1000 samples) | ≤ 1s | ILoadOrchestrator |
| Detect oscillation (1000-point series) | ≤ 200ms | ILoadOrchestrator |
| Evaluate throughput stability | ≤ 100ms | IStabilityValidator |
| Check data integrity (10 tables) | ≤ 500ms | IStabilityValidator |
| Verify rollback safety | ≤ 200ms | IStabilityValidator |
| Compute final certification score | ≤ 100ms | ICertificationGate |
| Freeze production snapshot | ≤ 1s | ICertificationGate |

### Idempotency Guarantees

| Operation | Idempotency Key | Behavior on Retry |
|-----------|----------------|-------------------|
| inject_network_partition | (scenario_id, target_service, trace_id) | No-op if same injection active |
| kill_worker | (scenario_id, worker_id, trace_id) | No-op if worker already killed |
| simulate_db_failover | (scenario_id, db_instance, trace_id) | No-op if failover already active |
| restore_baseline | (injection_id, trace_id) | No-op if already restored |
| generate_concurrent_dags | (profile_hash, trace_id) | Same DAG IDs returned |
| apply_resource_pressure | (pressure_type, trace_id) | Same pressure level if already applied |
| measure_p99_latency | (sample_size, trace_id) | Fresh measurement always taken |
| publish_readiness_report | (report_hash, trace_id) | No-op if report already published |
| freeze_production_snapshot | (cert_result_hash, trace_id) | No-op if snapshot already frozen |

### Determinism Thresholds

| Check | Threshold | Guard |
|-------|-----------|-------|
| Load curve reproducibility (same profile + cluster) | 100% exact DAG topology | G-D1 |
| Chaos scenario hash reproducibility | 100% match | G-D1 (scenario_hash) |
| Readiness report hash reproducibility | 100% match | RULE 1 |
| Recovery time variance | ± 5% across identical scenarios | LAW 8 |
| Integrity check reproducibility | 100% same checksum for same data | RULE 1 |
| Certification score variance | ± 0.0 (deterministic) | LAW 5 |

### Zero-Data-Loss Under Chaos

| Scenario | Data Loss Guarantee | Validation |
|----------|---------------------|------------|
| Network partition (service isolated) | Zero data loss — transactions queued | Check queue depth matches pre-fault |
| Worker killed abruptly | Zero data loss — committed transactions preserved | Verify committed transaction count |
| DB failover promoted replica | Zero data loss — WAL replay complete | Verify replication lag < 500ms |
| Resource exhaustion (memory pressure) | Zero data loss — OOM-killed workers drain first | Verify drain queue processed before kill |
| Connection drop during load test | Zero data loss — client retry with idempotency keys | Verify all retried operations deduplicated |

### Rollback on Failure

| Failure Point | Rollback Action | RULE |
|---------------|-----------------|------|
| Fault injection fails mid-operation | Remove partial fault state from I1 K8s | RULE 5 |
| Recovery exceeds expected_recovery_sec | Trigger manual escalation path | RULE 5 |
| Data integrity check fails post-chaos | Restore from pre-fault snapshot (I1 ObjectStorage) | RULE 5 |
| Certification scoring fails | Discard partial report, no freeze executed | RULE 5 |
| Production snapshot freeze fails | Revert to previous snapshot version | RULE 5 |

---

## 9. CompositionRoot Wiring Specification

The J3 components will be wired in CompositionRoot (during Phase J3
implementation) following the same pattern as J1/J2:

```python
# (Design-only sketch — not production code)

# Constructor params:
#   chaos_injector: Any = None,
#   load_orchestrator: Any = None,
#   stability_validator: Any = None,
#   certification_gate: Any = None,
#   strict_readiness_mode: bool = False,

# Properties:

# @property
# def chaos_injector(self) -> Any:
#     ...

# @property
# def load_orchestrator(self) -> Any:
#     ...

# @property
# def stability_validator(self) -> Any:
#     ...

# @property
# def certification_gate(self) -> Any:
#     ...

# Builder methods:
#   _build_chaos_injector() -> ChaosInjector
#   _build_load_orchestrator() -> LoadOrchestrator
#   _build_stability_validator() -> StabilityValidator
#   _build_certification_gate() -> CertificationGate
```

Total J3 components: 4 protocols × 1 implementation = 4 production modules
+ 1 state machine module + 1 `__init__.py` = 6 files in `core/readiness/`.
