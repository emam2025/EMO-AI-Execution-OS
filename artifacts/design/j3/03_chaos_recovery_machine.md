# Phase J3 — Chaos & Recovery State Machine

## Overview

Formal state machine governing chaos injection, degradation monitoring,
auto-recovery verification, and load testing lifecycle. Enforces 3 Recovery
Guards (G-C1–G-C3) and 1 Deterministic Load Guard (G-D1).

Ref: ROADMAP 🔟 FINAL DELIVERY STAGE
Ref: DEVELOPER.md §15.13 (Chaos Engineering), §16 (Production Readiness)
Ref: Canon LAW 3, 5, 8, 11, 20-22, RULE 1-5
Ref: artifacts/design/j3/protocols/01_readiness_protocols.py
Ref: artifacts/design/j3/models/02_chaos_and_load_models.py

---

## 1. Chaos Injection & Recovery State Machine

```
                           ┌──────────────────────────────────────┐
                           │         BASELINE CAPTURED            │
                           │  (pre-fault health snapshot taken)   │
                           └──────────────┬───────────────────────┘
                                          │
                                          ▼
                           ┌──────────────────────────────────────┐
                     ┌────>│          FAULT INJECTED               │
                     │     │  service: IChaosInjector              │
                     │     │  guard:   G-C1 (pre-fault health)     │
                     │     └──────────────┬───────────────────────┘
                     │                    │
                     │                    ▼
                     │     ┌──────────────────────────────────────┐
                     │     │       MONITOR DEGRADATION            │
                     │     │  (wait for fault to manifest)        │
                     │     │  guard:   G-C2 (degradation budget)  │
                     │     └──────────────┬───────────────────────┘
                     │                    │
                     │          ┌─────────┴──────────┐
                     │          ▼                    ▼
                     │  ┌──────────────────┐  ┌──────────────────┐
                     │  │  AUTO-RECOVERY   │  │   ESCALATED      │
                     │  │  (restore base-  │  │  (degradation >  │
                     │  │   line triggered)│  │   max threshold) │
                     │  │  guard: G-C3     │  │  → manual interv │
                     │  └──────┬───────────┘  └────────┬─────────┘
                     │         │                        │
                     │         ▼                        │
                     │  ┌──────────────────┐            │
                     │  │  VERIFY INTEGRITY│            │
                     │  │  (check data,    │            │
                     │  │   verify rollback)            │
                     │  │  guard: data_in- │            │
                     │  │  tegrity_verified│            │
                     │  │  AND p99 < thr   │            │
                     │  └──────┬───────────┘            │
                     │         │                        │
                     │  ┌──────┴──────┐                 │
                     │  ▼             ▼                 │
                     │  ┌────────┐ ┌────────┐          │
                     │  │COMPLET-│ │ROLLED  │          │
                     │  │ED      │ │BACK    │          │
                     │  │(pass)  │ │(fail)  │          │
                     │  └────────┘ └───┬────┘          │
                     │                 │               │
                     └─────────────────┼───────────────┘
                                       │
                                       ▼
                                ┌──────────────────┐
                                │  BASELINE        │
                                │  CAPTURED        │
                                │  (next scenario) │
                                └──────────────────┘
```

### Chaos State Transitions Table

| ID | From | To | Trigger | Guard |
|----|------|----|---------|-------|
| C-T1 | BASELINE_CAPTURED | FAULT_INJECTED | IChaosInjector.inject_*() called | G-C1 |
| C-T2 | FAULT_INJECTED | MONITOR_DEGRADATION | Fault confirmed active | — |
| C-T3 | MONITOR_DEGRADATION | AUTO_RECOVERY | Degradation within budget | G-C2 |
| C-T4 | MONITOR_DEGRADATION | ESCALATED | Degradation exceeds max threshold | G-C2 |
| C-T5 | AUTO_RECOVERY | VERIFY_INTEGRITY | IChaosInjector.restore_baseline() completes | G-C3 |
| C-T6 | AUTO_RECOVERY | ROLLED_BACK | Recovery fails RULE 3 guards | G-C3 |
| C-T7 | ESCALATED | ROLLED_BACK | Manual intervention escalates to rollback | — |
| C-T8 | VERIFY_INTEGRITY | COMPLETED | data_integrity_verified AND p99 < threshold | RULE 3 |
| C-T9 | VERIFY_INTEGRITY | ROLLED_BACK | data_integrity_verified == False OR p99 >= threshold | RULE 3 |
| C-T10 | ROLLED_BACK | BASELINE_CAPTURED | Rollback complete, ready for next scenario | — |
| C-T11 | COMPLETED | BASELINE_CAPTURED | Pass, ready for next scenario | — |

---

## 2. Load Testing State Machine

```
                ┌──────────┐
                │   IDLE   │
                └────┬─────┘
                     │
                     ▼
             ┌──────────────┐
             │  GENERATING  │
             │ (concurrent  │
             │  DAG submit) │
             └──────┬───────┘
                    │
                    ▼
             ┌──────────────┐
             │  PRESSURE    │
             │  APPLIED     │
             │ (resource    │
             │  pressure)   │
             └──────┬───────┘
                    │
                    ▼
             ┌──────────────┐
             │  MEASURING   │
             │ (p99/p999    │
             │  latency)    │
             └──────┬───────┘
                    │
                    ▼
             ┌──────────────┐
             │ OSCILLATION  │
             │   CHECK      │
             │ (detect osc) │
             └──────┬───────┘
                    │
                    ▼
             ┌──────────────┐
             │  COMPLETED   │
             └──────────────┘
```

### Load State Transitions Table

| ID | From | To | Trigger | Guard |
|----|------|----|---------|-------|
| L-T1 | IDLE | GENERATING | ILoadOrchestrator.generate_concurrent_dags() | G-D1 |
| L-T2 | GENERATING | PRESSURE_APPLIED | All DAGs submitted, apply_resource_pressure() | G-D1 |
| L-T3 | PRESSURE_APPLIED | MEASURING | Pressure stabilized, measure_p99_latency() | — |
| L-T4 | MEASURING | OSCILLATION_CHECK | Latency samples collected, detect_oscillation() | — |
| L-T5 | OSCILLATION_CHECK | COMPLETED | Oscillation check complete | — |

---

## 3. Recovery Guards Matrix (G-C1 through G-C3)

### G-C1: Pre-Fault Health Guard

**Condition:**
```
injection_allowed = (
    target_service.health_score >= PRE_FAULT_HEALTH_MIN  # e.g. 0.8
    AND target_service.error_rate_pct < MAX_ERROR_RATE_BEFORE_INJECTION  # e.g. 5.0
    AND NOT target_service.is_already_degraded
    AND readiness_trace_id is not None  # LAW 8
    AND scenario.expected_recovery_sec > 0  # LAW 8 — NON-NEGOTIABLE
)
```

**If violated:** Injection is blocked. Event published to `readiness.chaos.injection_blocked`.

**Canon ref:** LAW 8, 20; RULE 3

### G-C2: Degradation Budget Guard

**Condition:**
```
auto_recovery_allowed = (
    degradation_metric < MAX_DEGRADATION_THRESHOLD  # e.g. error_rate < 30%
    AND recovery_time_remaining >= scenario.expected_recovery_sec * 0.5
    AND NOT cascade_failure_detected  # LAW 22
    AND severity_propagation_contained  # LAW 21
)
```

**If degradation_metric >= MAX_DEGRADATION_THRESHOLD:** → `ESCALATED` state. Manual intervention required.

**If cascade_failure_detected:** → Immediate `ESCALATED`, cascading failure prevention (LAW 22).

**Canon ref:** LAW 21, 22; RULE 3

### G-C3: Recovery Verification Guard

**Condition:**
```
recovery_verified = (
    restore_baseline.completed == True
    AND data_sync_lag < 500ms  # DATA INTEGRITY CHECK
    AND lease_transferred == True  # For failover scenarios
    AND audit_hash_match == True  # G-A1 style deterministic verification
    AND p99_ms < P99_THRESHOLD  # e.g. p99 < 200ms
    AND NOT oscillation_detected
    AND verify_rollback_safety.rollback_safe == True  # RULE 5
)
```

**If violated:** → `ROLLED_BACK` state. Full rollback executed. Event published to `readiness.chaos.recovery_failed`.

**Canon ref:** LAW 5, 8, 22; RULE 3, 5

---

## 4. Deterministic Load Guard (G-D1)

### Purpose

Prevents Non-Deterministic Test Drift — same LoadProfile + ClusterState combination MUST produce the identical load curve. This guarantees that load test results are reproducible across runs and environments.

### Deterministic Load Hash Formula

```
G-D1_load_hash = SHA-256(
    profile_id
    + ":" + concurrent_users
    + ":" + dags_per_second
    + ":" + resource_multiplier
    + ":" + ramp_up_curve
    + ":" + cluster_state_hash
)
```

Where `cluster_state_hash` = SHA-256 of (available_workers + cpu_capacity + memory_available + active_connections).

Result: 32-character hex string.

### How the Orchestrator Ensures the Same Load Curve

1. **LoadProfile + ClusterState → Deterministic Seed**: The G-D1 hash is used as the random seed for DAG topology generation. Same profile + same cluster state → identical DAG topology sequence.

2. **Ramp-Up Curve is Parameterized, Not Sampled**: The LoadShape (LINEAR_RAMP, STEP_FUNCTION, SPIKE, etc.) defines exact injection timestamps. No random jitter is introduced — the curve is fully deterministic from the hash seed.

3. **Idempotent DAG Generation**: `generate_concurrent_dags(count=100)` with the same profile_hash will produce the exact same 100 DAGs in the same order. Determinism is verified by comparing profile_hash before and after generation.

4. **Rejection of Non-Determinism**:

| Scenario | G-D1 Response |
|----------|---------------|
| Same LoadProfile + ClusterState | Always same load curve |
| Different LoadProfile | Different curve |
| Different ClusterState | Different curve (accounts for scale) |
| Profile hash mismatch after generation | Test flagged as non-deterministic |

### Canon ref

- **RULE 1:** Determinism — same LoadProfile + ClusterState, same load curve.
- **LAW 5:** Stability validation is deterministic and reproducible.

---

## 5. Load Curve Determinism Table (G-D1)

| Parameter | Type | Determinism Guarantee |
|-----------|------|----------------------|
| `concurrent_users` | int | Exact count submitted |
| `dags_per_second` | float | Exact injection rate maintained |
| `resource_multiplier` | float | Exact multiplier applied |
| `ramp_up_curve` | LoadShape | Exact curve shape (no jitter) |
| `cluster_state_hash` | str | Captured at start of test |
| **G-D1_hash** | str | SHA-256 of all above → seed |

---

## 6. Certification Gate State Machine

```
                ┌──────────┐
                │   IDLE   │
                └────┬─────┘
                     │
                     ▼
             ┌──────────────┐
             │  BASELINE    │
             │  LOADING     │
             │ load_canon_  │
             │ baseline()   │
             └──────┬───────┘
                    │
                    ▼
             ┌──────────────┐
             │  VALIDATING  │
             │ run_valida-  │
             │ tion_suite() │
             └──────┬───────┘
                    │
                    ▼
             ┌──────────────┐
             │  SCORING     │
             │ compute_final│
             │ _score()     │
             └──────┬───────┘
                    │
         ┌──────────┼──────────┐
         ▼          ▼          ▼
   ┌─────────┐ ┌─────────┐ ┌──────────┐
   │CERTIFIED│ │CERTIFIED│ │NOT CERT- │
   │ (A/B)   │ │  (C)    │ │IFIED (F) │
   └────┬────┘ └────┬────┘ └────┬─────┘
        │           │           │
        ▼           ▼           ▼
   ┌─────────┐ ┌─────────┐ ┌──────────┐
   │ FROZEN  │ │ FLAGGED │ │ BLOCKED  │
   │ (snap-  │ │ (review │ │ (certifi-│
   │ shot)   │ │  needed)│ │ cation   │
   └─────────┘ └─────────┘ │  denied) │
                            └──────────┘
```

### Certification Transitions

| ID | From | To | Trigger | Condition |
|----|------|----|---------|-----------|
| G-T1 | IDLE | BASELINE_LOADING | ICertificationGate.load_canon_baseline() | baseline_path valid |
| G-T2 | BASELINE_LOADING | VALIDATING | Baseline loaded, suite ready | Baseline validated (RULE 2) |
| G-T3 | VALIDATING | SCORING | run_validation_suite() complete | All checks executed |
| G-T4 | SCORING | CERTIFIED_A_B | compute_final_score() grade A/B | score >= 0.85 AND G-C3 passed |
| G-T5 | SCORING | CERTIFIED_C | compute_final_score() grade C | score >= 0.70 AND < 0.85 |
| G-T6 | SCORING | NOT_CERTIFIED | compute_final_score() grade F | score < 0.70 OR G-C3 failed |
| G-T7 | CERTIFIED_A_B | FROZEN | freeze_production_snapshot() | Snapshot stored |
| G-T8 | CERTIFIED_C | FLAGGED | Review required | Quality warning issued |
| G-T9 | NOT_CERTIFIED | BLOCKED | Certification denied | Blocked by list populated |

---

## 7. Stop Conditions Reference

| Condition | Guard | Violation Response |
|-----------|-------|--------------------|
| `expected_recovery_sec` missing in ChaosScenario | G-C1 | → STOP-REPORT (LAW 8) |
| `readiness_trace_id` missing in any model | G-C1/G-C3 | → STOP-REPORT (LAW 8) |
| Certify without `data_integrity_verified` | G-C3 | → STOP-REPORT (RULE 3 + LAW 20-22) |
| Certify without `p99 < threshold` | G-C3 | → STOP-REPORT (RULE 3 + LAW 5) |
| Non-deterministic load curve detected | G-D1 | → Test flagged, must re-run |
| Cross-scenario state leakage (LAW 11) | G-C1 | → Instance isolation required |
