# Phase I1 — HA & Failover State Machine

## State Overview

The High-Availability Orchestrator defines a **5-state lifecycle machine**
for every node in a Runtime cluster. Each transition is gated by
**Split-Brain Guards** that enforce Canon LAW 20 (Failure Detection),
LAW 21 (Failure Propagation), LAW 22 (Service Isolation), and RULE 3
(Safety Guards).

### States

| State | Description | LAW/RULE |
|-------|-------------|----------|
| `LEADER` | Node is the active cluster leader | LAW 20, LAW 22 |
| `FOLLOWER` | Node is a replica, replicating from leader | LAW 11, RULE 4 |
| `CANDIDATE` | Node is running for election | LAW 20 |
| `ISOLATED` | Node is partitioned from quorum | LAW 22, RULE 4 |
| `RECOVERING` | Node is syncing state after disruption | RULE 5 |

---

## Transition Map

```
                        ┌──────────────────────────────────────────────┐
                        │                                              │
                        v                                              │
   ┌─────────┐  H1   ┌──────────┐  H2   ┌────────────┐  H4   ┌──────┐ │
   │ FOLLOWER│──────>│ CANDIDATE│──────>│   LEADER   │──────>│FOLLOWER│ │
   └─────────┘       └──────────┘       └────────────┘       └──────┘ │
        │                                    │                 │       │
        │H9                                 H3,H5              │       │
        v                                    v                 │       │
   ┌─────────┐                          ┌──────────┐           │       │
   │ ISOLATED│<─────────────────────────│ RECOVERING│           │       │
   └─────────┘       H7,H8              └──────────┘           │       │
        │                                                        │       │
        │H6                                                      │       │
        v                                                        │       │
   ┌─────────┐                                                    │       │
   │ CANDIDATE│────────────────────────────────────────────────────┘       │
   └─────────┘                                                            │
          │                                                                │
          └────────────────────────────────────────────────────────────────┘
```

### Transition Table

| # | From | To | Guard | Conditions | LAW/RULE |
|---|------|----|-------|------------|----------|
| H1 | FOLLOWER | CANDIDATE | `guard_lease_expired` | lease_timeout_expired AND leader heartbeat missing > timeout_sec | LAW 20 |
| H2 | CANDIDATE | LEADER | `guard_quorum_election` | quorum_votes > total_nodes / 2 AND term > current_term | LAW 20, RULE 3 |
| H3 | LEADER | RECOVERING | `guard_health_degraded` | node health degraded AND can self-heal | LAW 5 |
| H4 | LEADER | FOLLOWER | `guard_peaceful_stepdown` | voluntary resignation OR new_leader_elected with higher term | LAW 11 |
| H5 | LEADER | ISOLATED | `guard_network_partition` | quorum_lost AND lease_remaining = 0 | LAW 22, RULE 4 |
| H6 | ISOLATED | CANDIDATE | `guard_rejoin_cluster` | partition_resolved AND state_snapshot_synced | RULE 5 |
| H7 | RECOVERING | FOLLOWER | `guard_snapshot_verified` | snapshot_hash matches source AND all_deltas_applied | RULE 1 |
| H8 | RECOVERING | ISOLATED | `guard_recovery_timeout` | recovery_duration > max_recovery_sec | LAW 20 |
| H9 | FOLLOWER | ISOLATED | `guard_follower_isolation` | leader_lease_valid BUT node cannot reach quorum | LAW 22 |

---

## Split-Brain Guards (S1–S5)

### S1 — Quorum Election Guard (`guard_quorum_election`)
**Prevents:** Two leaders elected concurrently.

| Condition | Pass | Fail |
|-----------|------|------|
| quorum_votes > total_nodes / 2 | ✅ | ❌ Block — insufficient quorum |
| election_term > last_known_term | ✅ | ❌ Block — stale term |
| no_other_leader_advertised_in_term | ✅ | ❌ Block — split brain detected |
| **LAW:** LAW 20, RULE 3 | | |

### S2 — Lease Expiry Guard (`guard_lease_expired`)
**Prevents:** Premature leader election before lease truly expires.

| Condition | Pass | Fail |
|-----------|------|------|
| leader_heartbeat_age > lease_timeout_sec | ✅ | ❌ Block — leader still alive |
| >= (total_nodes / 2) + 1 nodes report leader missing | ✅ | ❌ Block — insufficient confirmation |
| lease_holder metadata matches known leader | ❌ (should differ) | ✅ Block — wrong lease holder |
| **LAW:** LAW 20 (Failure Detection) | | |

### S3 — Snapshot Verification Guard (`guard_snapshot_verified`)
**Prevents:** Recovering with corrupted or stale state.

| Condition | Pass | Fail |
|-----------|------|------|
| snapshot_hash matches source node hash | ✅ | ❌ Block — checksum mismatch |
| snapshot_term >= last_committed_term | ✅ | ❌ Block — stale snapshot |
| delta_log_applied_up_to >= source_commit_index | ✅ | ❌ Block — missing deltas |
| **LAW:** RULE 1 (Determinism), RULE 5 (Recovery) | | |

### S4 — Network Partition Guard (`guard_network_partition`)
**Prevents:** Leader operating without quorum.

| Condition | Pass | Fail |
|-----------|------|------|
| quorum_lost_interval > max_partition_sec | ✅ | ❌ Still within tolerance |
| leader_can_reach >= quorum_minimum nodes | ❌ | ✅ Block — still has quorum |
| lease_remaining == 0 | ✅ | ❌ Lease still valid |
| **LAW:** LAW 22 (Service Isolation), RULE 4 (Isolation) | | |

### S5 — Follower Isolation Guard (`guard_follower_isolation`)
**Prevents:** Follower operating while partitioned from leader.

| Condition | Pass | Fail |
|-----------|------|------|
| follower_cannot_reach_leader AND cannot_reach_quorum | ✅ | ❌ Can still reach leader or quorum |
| leader_lease_valid (leader alive) | ✅ | ❌ Leader also isolated → trigger election |
| follower_has_outstanding_uncommitted_log | ❌ (no uncommitted entries) | ✅ Block — data loss risk |
| **LAW:** LAW 22 (Service Isolation), LAW 11 (No Global State) | | |

---

## Deterministic Rollout Guard — Design

The Deployer guarantees that **the same manifest + cluster_state produces
the same rollout behaviour every time**. This prevents Non-Deterministic
Rollout Drift.

### Formula

```
manifest_hash = H(runtime_version || worker_pods || resource_limits ||
                  health_checks || configmap_refs || namespace)

target_state_hash = H(manifest_hash || cluster_state_hash || current_version)

rollout_decision = deterministic_select(manifest_hash, target_state_hash, strategy)
```

Where `H()` is SHA-256 and `||` is sorted-key canonical JSON concatenation.

### Rollout Decision Table

| Strategy | Condition | Action |
|----------|-----------|--------|
| `rolling_update` | always | Incremental pod replacement (maxSurge=1, maxUnavailable=0) |
| `blue_green` | canary_percent == 0 | Full new stack, switch traffic after health check |
| `canary` | canary_percent > 0 | Route canary_percent% traffic to new version |
| `rollback` | deployment failed | Reverse to previous manifest_hash |

### Deviation Tolerance

| Metric | Threshold | Action |
|--------|-----------|--------|
| Pod readiness deviation | 0% (strict) | Abort rollout, trigger rollback |
| Health check failure rate | ≥1 failure in 3 consecutive checks | Mark pod unhealthy, drain |
| Canary error rate increase | ≥5% above baseline | Abort canary, rollback |
| Snapshot checksum mismatch | 0% (strict) | Block recovery, alert |
| Election term gap | >1 term | Force full re-election |

### Integration with IKubernetesDeployer.deploy_runtime

```python
def _compute_manifest_hash(manifest: DeploymentManifest) -> str:
    raw = json.dumps({
        "runtime_version": manifest.runtime_version,
        "worker_pods": manifest.worker_pods,
        "resource_limits": manifest.resource_limits,
        "health_checks": manifest.health_checks,
        "configmap_refs": sorted(manifest.configmap_refs),
        "namespace": manifest.namespace,
    }, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:32]
```

---

## HA Lifecycle Compliance

| Concern | Guard | Enforcement |
|---------|-------|-------------|
| No leader without quorum > 50% | S1 | Block election |
| No premature failover | S2 | Verify lease truly expired |
| No corrupted state sync | S3 | Checksum verification |
| No leader operating isolated | S4 | Step down, trigger election |
| No follower operating partitioned | S5 | Isolate node |
| Deterministic rollout | Rollout Guard | Same manifest → same behaviour |
