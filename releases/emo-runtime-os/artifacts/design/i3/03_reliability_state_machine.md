# Phase I3 — Production Reliability State Machine

## 1. Core Reliability State Machine (Failover + Disaster Recovery)

The Production Reliability State Machine defines a **8-state lifecycle** for
failover orchestration and disaster recovery. Each transition is gated by
**Safety Guards** that enforce Canon LAW 8 (Recoverability), LAW 20 (Failure
Detection), LAW 21 (Failure Propagation), LAW 22 (Service Isolation), and
RULE 3 (Safety Guards).

This machine extends I1's HA State Machine (5 states, 9 transitions, S1-S5
Split-Brain Guards) with higher-level failover orchestration, DR recovery
points, and journal replay. It integrates with I2's ACID State Machine for
data-layer consistency during failover.

### States

| State | Description | LAW/RULE |
|-------|-------------|----------|
| `HEALTHY` | Normal operation — all nodes reachable, quorum healthy | LAW 20 |
| `FAILURE_DETECTED` | Anomaly or heartbeat loss detected on a node | LAW 20, LAW 8 |
| `QUORUM_CHECK` | Verifying quorum integrity before escalation | LAW 20, RULE 3 |
| `ISOLATE_NODE` | Isolating failed node via fencing | LAW 22, RULE 4 |
| `PROMOTE_REPLICA` | Promoting standby replica to active | LAW 8, RULE 3 |
| `SYNC_STATE` | Synchronizing state after promotion | RULE 1, RULE 5 |
| `RECOVERY_POINT` | Creating a checksum-verified recovery point | LAW 8, RULE 1 |
| `RESTORE_REPLAY` | Restoring from backup + replaying journal | LAW 8, RULE 2 |

---

### Transition Map

```
                     R1 (guard_health_degraded)
    ┌─────────────────────────────────────────────────────┐
    │                                                     │
    ▼                                                     │
┌──────────┐  R1   ┌──────────────────┐  R2   ┌───────────┐
│  HEALTHY │──────>│ FAILURE_DETECTED │──────>│QUORUM_CHECK│
└──────────┘       └──────────────────┘       └───────────┘
     ▲                      │                       │
     │R12                  R12                      │
     │                      │R2 (guard_false_alarm) │R3 (guard_quorum_valid)
     │                      v                       v
     │                 ┌──────────┐           ┌────────────────┐
     │                 │  HEALTHY │           │ PROMOTE_REPLICA│
     │                 │ (resume) │           └────────────────┘
     │                 └──────────┘                  │
     │                                               │R4 (guard_promote_safe)
     │                                               v
     │                                          ┌──────────────┐
     │                                          │ ISOLATE_NODE │
     │                                          └──────────────┘
     │                                               │
     │                                              R5 (guard_replica_promoted)
     │                                               v
     │                                          ┌───────────┐
     │                                          │ SYNC_STATE│
     │                                          └───────────┘
     │                                          │         │
     │                              R6 (guard_sync_ok)   R7 (guard_sync_failed)
     │                              │                     │
     │                              v                     v
     │                          ┌──────────┐        ┌──────────┐
     │                          │  HEALTHY │        │ FALLBACK │
     │                          │ (recovered)       └──────────┘
     │                          └──────────┘              │
     │                                               R8 (guard_fallback_dr)
     │                                                     │
     │                                                     v
     │                                                ┌──────────────┐
     │                                                │RESTORE_REPLAY│
     │                                                └──────────────┘
     │                                                     │
     │                                              R11 (guard_restore_ok)
     │                                                     │
     └───────────────────── R11 ──────────────────────────┘

DR Path (from HEALTHY):

┌──────────┐  R9   ┌────────────────┐  R10   ┌──────────┐
│  HEALTHY │──────>│ RECOVERY_POINT │──────>│  HEALTHY │
│ (normal) │       │  (create)      │       │ (backed up)
└──────────┘       └────────────────┘       └──────────┘
```

### Transition Table

| # | From | To | Guard | Conditions | LAW/RULE |
|---|------|----|-------|------------|----------|
| R1 | HEALTHY | FAILURE_DETECTED | `guard_health_degraded` | heartbeat_loss_sec > threshold AND quorum_status != "healthy" OR anomaly_severity >= HIGH | LAW 20, RULE 3 |
| R2 | FAILURE_DETECTED | QUORUM_CHECK | `guard_quorum_integrity` | failure_confirmed_by >= 2 nodes AND suspicion != "false_alarm" | LAW 20, RULE 3 |
| R2a | FAILURE_DETECTED | HEALTHY | `guard_false_alarm` | failure_not_confirmed OR self_healed within window | LAW 8 |
| R3 | QUORUM_CHECK | PROMOTE_REPLICA | `guard_quorum_valid` | quorum_votes > total_nodes / 2 AND standby_available AND data_sync_lag < threshold | LAW 20, RULE 3 |
| R3a | QUORUM_CHECK | ISOLATE_NODE | `guard_quorum_lost` | quorum_votes <= total_nodes / 2 AND leader_must_step_down | LAW 22, RULE 4 |
| R4 | ISOLATE_NODE | PROMOTE_REPLICA | `guard_promote_safe` | node_isolated AND lease_revoked AND traffic_drained AND checksum_match | LAW 22, RULE 3 |
| R5 | PROMOTE_REPLICA | SYNC_STATE | `guard_replica_promoted` | promotion_succeeded AND new_leader_elected AND quorum_reestablished | LAW 8, RULE 5 |
| R6 | SYNC_STATE | HEALTHY | `guard_sync_verified` | state_hash_matches AND all_deltas_applied AND journal_offset_caught_up | RULE 1, RULE 5 |
| R7 | SYNC_STATE | FALLBACK | `guard_sync_failed` | sync_timeout OR checksum_mismatch OR delta_gap_exceeds_max | LAW 8, RULE 5 |
| R8 | FALLBACK | RESTORE_REPLAY | `guard_fallback_to_dr` | fallback_initiated AND recovery_point_available AND backup_exists | LAW 8, RULE 5 |
| R9 | HEALTHY | RECOVERY_POINT | `guard_recovery_point_due` | scheduled_interval_elapsed OR manual_trigger OR pre_upgrade | LAW 8 |
| R10 | RECOVERY_POINT | HEALTHY | `guard_backup_verified` | checksum_match AND journal_offset_recorded AND size_within_limits | RULE 1 |
| R11 | RESTORE_REPLAY | HEALTHY | `guard_restore_verified` | restore_checksum_match AND replay_complete AND consistency_ok AND data_trace_chain_intact | LAW 8, RULE 2 |
| R12 | FAILURE_DETECTED | HEALTHY | `guard_false_alarm` | investigation_concluded AND no_action_needed | LAW 8 |

---

## 2. Rolling Update Sub-Machine

The Rolling Update sub-machine manages zero-downtime deployments using
canary, blue-green, and progressive strategies. It extends I1's
Deterministic Rollout Guard with explicit state transitions.

### States

| State | Description | LAW/RULE |
|-------|-------------|----------|
| `PREPARE_CANARY` | Canary preparation with compatibility validation | LAW 3, RULE 1 |
| `ROLL_FORWARD` | Progressive rollout or blue-green switch | LAW 3, RULE 4 |
| `HEALTH_MONITOR` | Post-rollout health verification | LAW 20, RULE 3 |
| `ROLL_BACK` | Rollback on health failure or error spike | LAW 8, RULE 5 |

### Transition Map

```
┌───────────────┐  U1   ┌────────────────┐  U2   ┌────────────────┐
│ PREPARE_CANARY│──────>│  ROLL_FORWARD  │──────>│ HEALTH_MONITOR │
└───────────────┘       └────────────────┘       └────────────────┘
       │                        │                         │
       │U5                     U3                        │U4
       v                        v                         │
┌────────────────┐        ┌──────────┐                    │
│  ROLL_BACK     │<───────│ROLL_BACK │<────────────────────┘
└────────────────┘   U3   └──────────┘
       │
       │U6
       v
┌────────────────┐
│ PREPARE_CANARY │  (retry with new version)
└────────────────┘
```

### Transition Table

| # | From | To | Guard | Conditions | LAW/RULE |
|---|------|----|-------|------------|----------|
| U1 | PREPARE_CANARY | ROLL_FORWARD | `guard_canary_ready` | compatibility_ok AND canary_percent_set AND health_endpoint_configured AND manifest_hash_computed | LAW 3, RULE 1 |
| U2 | ROLL_FORWARD | HEALTH_MONITOR | `guard_rollout_progressed` | target_pods_ready >= desired AND health_probes_passing AND error_rate < baseline | LAW 20 |
| U3 | ROLL_FORWARD | ROLL_BACK | `guard_rollback_required` | health_check_failure OR error_rate >= rollback_threshold (5%) OR latency > 1.5x baseline OR compatibility_issue | LAW 8, RULE 5 |
| U4 | HEALTH_MONITOR | ROLL_BACK | `guard_health_degraded_post` | deferred_error_detected OR gradual_latency_increase > threshold OR anomaly_detected | LAW 20, RULE 3 |
| U5 | PREPARE_CANARY | ROLL_BACK | `guard_preparation_failed` | compatibility_mismatch OR manifest_hash_mismatch OR insufficient_cluster_capacity | RULE 3 |
| U6 | ROLL_BACK | PREPARE_CANARY | `guard_rollback_complete` | previous_version_restored AND data_preserved AND health_checks_pass | LAW 8, RULE 5 |

---

## 3. Runtime Migration Sub-Machine

The Migration sub-machine manages seamless backend migration with dry-run
validation, state snapshot, switch-over, and post-migration verification.

### States

| State | Description | LAW/RULE |
|-------|-------------|----------|
| `DRY_RUN` | Migration simulation with compatibility checks | LAW 3, RULE 1 |
| `SNAPSHOT_STATE` | Capturing pre-migration deterministic snapshot | LAW 8, RULE 2 |
| `SWITCH_OVER` | Switching traffic to target backend | LAW 8, RULE 4 |
| `POST_MIGRATION_VERIFY` | Verifying migrated data integrity | LAW 8, RULE 1 |

### Transition Map

```
┌──────────┐  M1   ┌────────────────┐  M2   ┌──────────────┐
│ DRY_RUN  │──────>│ SNAPSHOT_STATE │──────>│ SWITCH_OVER  │
└──────────┘       └────────────────┘       └──────────────┘
     │                      │                      │
     │M6                   M5                     M3
     v                      v                      v
┌──────────┐          ┌──────────┐          ┌──────────────┐
│ ABORT    │          │ ABORT    │          │ ROLL_BACK    │
└──────────┘          └──────────┘          └──────────────┘
                                                      │
                                                      │M4
                                                      v
                                               ┌────────────────────┐
                                               │POST_MIGRATION_VERIFY│
                                               └────────────────────┘
                                                      │
                                                      │M7
                                                      v
                                               ┌──────────┐
                                               │ COMPLETE │
                                               └──────────┘
```

### Transition Table

| # | From | To | Guard | Conditions | LAW/RULE |
|---|------|----|-------|------------|----------|
| M1 | DRY_RUN | SNAPSHOT_STATE | `guard_dry_run_passed` | dry_run_passed AND compatibility_ok AND issues_found empty AND data_volume < capacity | LAW 3, RULE 1 |
| M2 | SNAPSHOT_STATE | SWITCH_OVER | `guard_snapshot_verified` | snapshot_hash_computed AND journal_offset_recorded AND source_integrity_ok AND checksum_match | LAW 8, RULE 2 |
| M3 | SWITCH_OVER | POST_MIGRATION_VERIFY | `guard_switch_complete` | traffic_routed >= threshold AND rollback_path_exists AND target_backend_healthy | LAW 8, RULE 4 |
| M4 | SWITCH_OVER | ROLL_BACK | `guard_switch_failed` | traffic_routing_failed OR target_unhealthy OR data_inconsistency_detected | LAW 8, RULE 5 |
| M5 | SNAPSHOT_STATE | ABORT | `guard_snapshot_failed` | source_unreachable OR checksum_mismatch OR journal_inconsistent | RULE 2 |
| M6 | DRY_RUN | ABORT | `guard_dry_run_failed` | compatibility_issues_found OR data_format_incompatible OR protocol_mismatch | LAW 3 |
| M7 | POST_MIGRATION_VERIFY | COMPLETE | `guard_migration_verified` | source_hash_match AND checksum_match AND row_count_match AND integrity_pct == 100 | RULE 1 |

---

## 4. Safety Guards

### G-R1 — Health Degraded Guard (`guard_health_degraded`)
**Prevents:** Failing to detect a real failure.

| Condition | Pass | Fail |
|-----------|------|------|
| heartbeat_loss_sec > heartbeat_timeout | ✅ Failure confirmed | ❌ Heartbeat within threshold |
| quorum_status in ("degraded", "lost") | ✅ Escalate | ❌ Quorum still healthy |
| anomaly_severity >= HIGH | ✅ Failure detected | ❌ Anomaly below threshold |
| **LAW:** LAW 20 (Failure Detection), RULE 3 (Safety Guards) | | |

### G-R2 — Quorum Integrity Guard (`guard_quorum_integrity`)
**Prevents:** Escalating a false alarm without quorum confirmation.

| Condition | Pass | Fail |
|-----------|------|------|
| failure_confirmed_by >= 2 independent nodes | ✅ Confirmed | ❌ Insufficient confirmation |
| consensus_check passed within cluster | ✅ Proceed | ❌ No consensus — potential partition |
| **LAW:** LAW 20 (Failure Detection), LAW 21 (Failure Propagation) | | |

### G-R3 — Promote Safe Guard (`guard_promote_safe`)
**Prevents:** Promoting a replica without quorum or with excessive sync lag.

| Condition | Pass | Fail |
|-----------|------|------|
| quorum_votes > total_nodes / 2 | ✅ Quorum valid | ❌ Insufficient quorum |
| data_sync_lag_ms < max_sync_lag_threshold (500ms) | ✅ Sync within budget | ❌ Sync lag exceeds threshold |
| standby_checksum matches primary snapshot | ✅ State consistent | ❌ Checksum mismatch |
| lease_revoked_on_failed_node | ✅ Fencing confirmed | ❌ Lease still active on failed node |
| **LAW:** LAW 8 (Recoverability), RULE 3 (Safety Guards) | | |

### G-R4 — Quorum Lost Guard (`guard_quorum_lost`)
**Prevents:** Allowing a leader to operate without quorum.

| Condition | Pass | Fail |
|-----------|------|------|
| quorum_votes <= total_nodes / 2 | ✅ Quorum lost — must step down | ❌ Still has quorum |
| leader_lease_remaining == 0 | ✅ Lease expired, safe to isolate | ❌ Lease still valid — wait |
| **LAW:** LAW 22 (Service Isolation), RULE 4 (Isolation) | | |

### G-R5 — Fencing Complete Guard (`guard_promote_safe` in isolate path)
**Prevents:** Promoting before isolation has completed.

| Condition | Pass | Fail |
|-----------|------|------|
| node_isolated AND isolation_mode confirmed | ✅ Node fenced | ❌ Isolation not confirmed |
| lease_revoked AND no_remaining_leases_for_node | ✅ Lease released | ❌ Lease still active |
| traffic_drained AND no_active_connections | ✅ Traffic stopped | ❌ Connections still active |
| **LAW:** LAW 22 (Service Isolation), RULE 4 (Isolation) | | |

### G-R6 — Sync Verified Guard (`guard_sync_verified`)
**Prevents:** Declaring recovery complete before state is fully synced.

| Condition | Pass | Fail |
|-----------|------|------|
| state_hash matches source (pre-failover) | ✅ State consistent | ❌ State mismatch |
| all_deltas_applied up to last_committed_offset | ✅ No missing deltas | ❌ Delta gap found |
| journal_offset_caught_up >= source_offset | ✅ Journal complete | ❌ Journal behind |
| **LAW:** RULE 1 (Determinism), RULE 5 (Recovery) | | |

### G-R7 — Backup Verified Guard (`guard_backup_verified`)
**Prevents:** Declaring a recovery point valid without checksum verification.

| Condition | Pass | Fail |
|-----------|------|------|
| combined_checksum == SHA-256(state_hash | ❌ Block — checksum mismatch |journal_offset) |
| journal_offset_recorded >= last_committed | ✅ Offset valid | ❌ Offset behind committed |
| size_bytes within_storage_limits | ✅ Size OK | ❌ Storage budget exceeded |
| **LAW:** LAW 8 (Recoverability), RULE 1 (Determinism) | | |

### G-R8 — Restore Verified Guard (`guard_restore_verified`)
**Prevents:** Declaring DR complete before data integrity is confirmed.

| Condition | Pass | Fail |
|-----------|------|------|
| restore_checksum == expected_checksum | ✅ Data intact | ❌ Checksum mismatch |
| replay_complete AND consistency_ok | ✅ Journal complete | ❌ Journal inconsistent |
| data_trace_chain_intact (I2 correlation preserved) | ✅ Traceability OK | ❌ Trace chain broken |
| **LAW:** LAW 8 (Recoverability), RULE 2 (No Uncontrolled IO) | | |

### G-U1 — Canary Ready Guard (`guard_canary_ready`)
**Prevents:** Starting a canary without full preparation.

| Condition | Pass | Fail |
|-----------|------|------|
| compatibility_matrix all fields OK | ✅ Compatible | ❌ Compatibility issue found |
| canary_percent set (0 < pct <= 100) | ✅ Percent set | ❌ Percent not configured |
| health_endpoint_configured AND reachable | ✅ Health check ready | ❌ Health endpoint not ready |
| manifest_hash computed (RULE 1) | ✅ Hash computed | ❌ Hash mismatch |
| **LAW:** LAW 3 (Deterministic Execution), RULE 1 (Determinism) | | |

### G-U2 — Rollback Required Guard (`guard_rollback_required`)
**Prevents:** Continuing a rollout that has failed.

| Condition | Pass | Fail |
|-----------|------|------|
| health_check_failure_count >= 1 | ✅ Rollback triggered | ❌ No failures |
| error_rate >= rollback_threshold (5%) | ✅ Error spike | ❌ Error rate normal |
| avg_latency > 1.5x baseline_latency | ✅ Latency degraded | ❌ Latency within bounds |
| **LAW:** LAW 8 (Recoverability), RULE 5 (Recovery) | | |

### G-M1 — Dry Run Passed Guard (`guard_dry_run_passed`)
**Prevents:** Starting migration without successful dry-run.

| Condition | Pass | Fail |
|-----------|------|------|
| dry_run_passed == true | ✅ Dry run OK | ❌ Dry run failed |
| compatibility_ok across all dimensions | ✅ Compatible | ❌ Incompatible |
| issues_found empty | ✅ No issues | ❌ Issues found |
| data_volume_bytes < target_capacity_bytes | ✅ Capacity OK | ❌ Insufficient capacity |
| **LAW:** LAW 3 (Deterministic Execution), RULE 1 (Determinism) | | |

### G-M2 — Snapshot Verified Guard (`guard_snapshot_verified`)
**Prevents:** Switching over with an unverified snapshot.

| Condition | Pass | Fail |
|-----------|------|------|
| snapshot_hash computed AND matches expected | ✅ Hash valid | ❌ Hash mismatch |
| journal_offset_recorded >= last_committed_tx | ✅ Offset valid | ❌ Offset behind |
| source_integrity_ok (no corruption detected) | ✅ Source healthy | ❌ Source corruption |
| **LAW:** LAW 8 (Recoverability), RULE 2 (No Uncontrolled IO) | | |

---

## 5. Deterministic Rollout Guard

The Rollout Guard guarantees that **the same UpdateStrategy + ClusterHealth
produces the same rollout behaviour every time**, preventing Non-Deterministic
Update Drift (LAW 3, RULE 1).

### Formula

```
strategy_hash = H(target_version || strategy || cluster_health_hash ||
                  canary_percent || compatibility_matrix || rollback_threshold)

manifest_hash    = H(runtime_version || worker_pods || resource_limits ||
                     health_checks || configmap_refs || namespace)

cluster_health_hash = H(healthy_nodes || degraded_nodes || cpu_avg || memory_avg ||
                        error_rate || avg_latency)

rollout_decision = deterministic_select(strategy_hash, manifest_hash,
                                        cluster_health_hash, strategy)
```

Where `H()` is SHA-256 and `||` is sorted-key canonical JSON concatenation.

### Rollout Decision Table

| Strategy | Condition | Action |
|----------|-----------|--------|
| `canary` | canary_percent > 0 AND compatibility_ok | Route canary_percent% traffic to new version, monitor health |
| `blue_green` | canary_percent == 0 AND health_check_window > 0 | Deploy full new stack, switch traffic after health checks pass |
| `progressive` | strategy == "progressive" AND cluster_health == healthy | Incremental replacement in stages (10%, 25%, 50%, 100%) |
| `rolling_update` | default for healthy clusters | Incremental pod replacement (maxSurge=1, maxUnavailable=0) |
| `rollback` | cluster_health.degraded_nodes > 0 OR error_rate > threshold | Reverse to previous manifest_hash |

### Deviation Tolerance

| Metric | Threshold | Action |
|--------|-----------|--------|
| Pod readiness deviation | 0% (strict) | Abort rollout, trigger rollback (G-U2) |
| Health check failure rate | >= 1 failure in 3 consecutive checks | Mark pod unhealthy, drain |
| Canary error rate increase | >= 5% above baseline | Abort canary, rollback |
| Progressive stage failure | Stage not 100% ready within timeout | Hold stage, investigate |
| Rollout manifest hash mismatch | 0% (strict) | Block deployment, alert |
| Cluster health degraded | degraded_nodes > total_nodes * 10% | Block rollout, wait for recovery |

### Integration with IRollingUpdateManager.roll_forward

```python
def _compute_rollout_decision(
    target_version: str,
    strategy: str,
    cluster_health: Dict[str, Any],
) -> str:
    strategy_data = {
        "target_version": target_version,
        "strategy": strategy,
        "cluster_health": {k: v for k, v in sorted(cluster_health.items())},
    }
    strategy_hash = hashlib.sha256(
        json.dumps(strategy_data, sort_keys=True).encode()
    ).hexdigest()[:32]

    # Deterministic selection from strategy + cluster_health
    if strategy == "canary":
        return RolloutDecision.PROCEED_CANARY.value
    elif strategy == "blue_green":
        return RolloutDecision.PROCEED_BLUE_GREEN.value
    elif cluster_health.get("degraded_nodes", 0) > 0:
        return RolloutDecision.ABORT_HEALTH_DEGRADED.value
    else:
        return RolloutDecision.PROCEED_ROLLING.value
```

---

## 6. Compliance Mapping

| Concern | Guard | Enforcement |
|---------|-------|-------------|
| No promotion without quorum > 50% | G-R3 (guard_promote_safe) | Block promotion |
| No promotion with sync lag > 500ms | G-R3 (data_sync_lag) | Block promotion |
| No premature failover | G-R1 (guard_health_degraded) | Verify heartbeat truly lost |
| No false alarm escalation | G-R2 (guard_quorum_integrity) | Require >= 2 node confirmation |
| No recovery without checksum | G-R7 (guard_backup_verified) | Block if checksum mismatch |
| No DR without journal replay | G-R8 (guard_restore_verified) | Block if replay incomplete |
| No canary without compatibility check | G-U1 (guard_canary_ready) | Block if compatibility fails |
| No rollout without health rollback | G-U2 (guard_rollback_required) | Auto-rollback on error spike |
| No migration without dry-run | G-M1 (guard_dry_run_passed) | Block if dry-run failed |
| Non-deterministic rollout | Deterministic Rollout Guard | Same inputs -> same decision |
| Recoverability of all state transitions | LAW 8 | Every path ends in HEALTHY or FALLBACK with recovery |
