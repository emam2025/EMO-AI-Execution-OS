# Canary Deployment Plan — EXEC-DIRECTIVE-021

## Overview

Canary deployment of v4.7.0-prod-ready on 3 isolated users with strict monitoring,
replay integrity verification, and rollback triggers.

## 3 Canary Users

| User | Repo | Worker Pool | CPU | Memory | Max Concurrent DAGs |
|------|------|-------------|-----|--------|-------------------|
| user-alpha | /tmp/canary/repos/alpha/ | pool-alpha | 1.0 core | 512 MB | 5 |
| user-beta  | /tmp/canary/repos/beta/  | pool-beta  | 2.0 cores | 1024 MB | 10 |
| user-gamma | /tmp/canary/repos/gamma/ | pool-gamma | 0.5 cores | 256 MB | 3 |

## Monitoring

- 10 Metrics collected every 10 seconds (P50/P95/P99, dag_completion_rate, retry_rate,
  replay_determinism_pct, lease_expiry_freq, ownership_conflicts, worker_recovery_time,
  scheduler_fairness_score, memory_growth_per_hour, cache_hit_ratio,
  planner_determinism_drift, feedback_calibration_stability)
- Anomaly checks every 30 seconds
- Metrics published to F4 Observability via `runtime.canary.metrics` topic
- Alerts published to `runtime.canary.alerts` and `runtime.readiness.canary`

## Replay Integrity

- `replay_integrity_check`: original_trace_hash vs replayed_trace_hash
- `checkpoint_validation`: pre/post run state consistency
- `determinism_audit`: run each DAG 3 times, compare output_hash, execution_order, timing

## Rollback Criteria

| Metric | Threshold | Action |
|--------|-----------|--------|
| P99 latency | > 500ms for 5 consecutive minutes | ROLLBACK to v4.6.0 |
| replay_determinism_pct | < 98% | PAUSE + INVESTIGATE |
| memory_growth_per_hour | > 5% sustained | ROLLBACK + LEAK AUDIT |
| lease_conflict_count | > 0 in 1 hour | PAUSE + OWNERSHIP AUDIT |
| scheduler_fairness_score | < 0.7 | PAUSE + SCHEDULER TUNING |
| planner_determinism_drift | > 2% strategy change | PAUSE + PLANNER AUDIT |

## Stop Conditions

Any breach of the above thresholds triggers immediate STOP-REPORT + ROLLBACK.

## Exit Criteria (→ v4.7.1-stable)

| Metric | Threshold |
|--------|-----------|
| P99 latency | ≤ 300ms (95th percentile over 24h) |
| replay_determinism_pct | ≥ 99.5% over 100 replay attempts |
| memory_growth_per_hour | ≤ 1% sustained |
| lease_conflict_count | 0 over 24h |
| scheduler_fairness_score | ≥ 0.9 (variance ≤ 0.1×mean) |
| planner_determinism_drift | ≤ 0.5% strategy change |
| dag_completion_rate | ≥ 99.9% |
| retry_rate | ≤ 2% (non-cascading) |
| user_reported_issues | 0 critical, ≤ 1 minor |
| canary_duration | ≥ 72 hours stable |
