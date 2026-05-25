# Phase F2 — Scaling Decision State Machine & Worker Draining Lifecycle

## 1. Scaling Decision State Machine

### States

| State | Description | Terminal |
|-------|-------------|----------|
| `METRIC_COLLECTED` | Load metrics gathered from cluster | No |
| `THRESHOLD_EVAL` | Evaluation against target_utilization ± hysteresis | No |
| `SCALE_UP` | Increase worker count by scale_step | No |
| `SCALE_DOWN` | Decrease worker count by scale_step | No |
| `HOLD` | Within hysteresis band — no action | No |
| `COOLDOWN` | Waiting for cooldown_sec before next action | No |
| `DRAIN` | Graceful worker draining in progress | No |
| `TERMINATE` | Final worker removal | Yes |

### Transition Map

```
                    ┌──────────────────────────────────────────────┐
                    │                                              │
                    ▼                                              │
    METRIC_COLLECTED ──→ THRESHOLD_EVAL                            │
                              │                                     │
                    ┌─────────┼──────────┬──────────┐              │
                    ▼         ▼          ▼          ▼              │
                SCALE_UP  SCALE_DOWN  HOLD      DRAIN              │
                    │         │          │          │              │
                    │         │          │          ▼              │
                    │         │          │      TERMINATE          │
                    │         │          │          │              │
                    └─────────┴──────────┴──────────┘              │
                              │                                    │
                              ▼                                    │
                          COOLDOWN ────────────────────────────────┘
```

### Transition Guards

| From | To | Guard Condition |
|------|----|-----------------|
| `METRIC_COLLECTED` | `THRESHOLD_EVAL` | At least one LoadMetric field > 0 |
| `THRESHOLD_EVAL` | `SCALE_UP` | utilization > target_utilization + hysteresis_pct AND last_scaled > cooldown_sec ago AND 2 consecutive UP evaluations |
| `THRESHOLD_EVAL` | `SCALE_DOWN` | utilization < target_utilization - hysteresis_pct AND last_scaled > cooldown_sec ago AND 2 consecutive DOWN evaluations |
| `THRESHOLD_EVAL` | `HOLD` | utilization within [target - hysteresis, target + hysteresis] OR cooldown active |
| `THRESHOLD_EVAL` | `DRAIN` | utilization < target_utilization - hysteresis_pct AND surplus >= 2 consecutive cycles |
| `SCALE_UP` | `COOLDOWN` | Always (post-action cooldown) |
| `SCALE_DOWN` | `COOLDOWN` | Always (post-action cooldown) |
| `DRAIN` | `TERMINATE` | All leases released AND no pending tasks |
| `TERMINATE` | `COOLDOWN` | Always (post-action cooldown) |
| `HOLD` | `COOLDOWN` | Only if state change from previous cycle (transition to HOLD resets consecutive counter) |
| `COOLDOWN` | `METRIC_COLLECTED` | cooldown_timer >= policy.cooldown_sec |

### 2. Hysteresis Guards (Oscillation Prevention)

Oscillation prevention is mandatory per §15.9.4. The following guards
MUST be implemented to prevent rapid flapping:

#### Guard 1: Consecutive Cycle Requirement
```
scale_up_allowed = (
    utilization >= target + hysteresis
    AND previous_n_signals[-2:] == [UP, UP]
    AND cooldown_expired
)
scale_down_allowed = (
    utilization <= target - hysteresis
    AND previous_n_signals[-2:] == [DOWN, DOWN]
    AND cooldown_expired
)
```

#### Guard 2: Hysteresis Dead-Band
```
if target - hysteresis <= utilization <= target + hysteresis:
    signal = HOLD
    consecutive_scale_up_counter = 0
    consecutive_scale_down_counter = 0
```

#### Guard 3: Cooldown Window
```
cooldown_expired = (time.time() - last_scaling_action_timestamp) >= policy.cooldown_sec
```

#### Guard 4: Scale Step Limiting
```
actual_delta = min(
    abs(target_count - current_count),
    policy.scale_step,
)
```
Prevents adding/removing more than `scale_step` workers in a single action.

### 3. Worker Draining Lifecycle

The draining lifecycle follows §15.9.3 with these immutable phases:

```
MARK_DRAINING ──→ STOP_NEW_LEASES ──→ AWAIT_COMPLETION ──→ RELEASE_LEASES ──→ TERMINATE
```

#### Phase Details

| Phase | Action | Guard | Expected Duration |
|-------|--------|-------|-------------------|
| `MARK_DRAINING` | Set WorkerState to DRAINING, log reason | WorkerState must be HEALTHY or DEGRADED | Immediate |
| `STOP_NEW_LEASES` | Remove worker from scheduler pool, reject new lease assignments | DRAINING state confirmed | Immediate |
| `AWAIT_COMPLETION` | Wait for active leases to complete or timeout | At least one lease may be active; timeout after `max_drain_wait_sec` | Configurable (default 300s) |
| `RELEASE_LEASES` | Force-release any remaining leases, emit `worker.drain.completed` event | All leases either completed or timed out | Immediate |
| `TERMINATE` | Set WorkerState to TERMINATED, release resources, emit `worker.terminated` event | LEASES_RELEASED phase complete | Immediate |

#### Draining Guards

1. **Cannot drain if already TERMINATED**: Worker state must be HEALTHY or DEGRADED.
2. **Cannot stop draining once started**: Draining is irreversible (RULE 2 exception — RULE 2 guarantees system-level reversibility via new worker provisioning, not individual drain reversal).
3. **Timeout safeguard**: If AWAIT_COMPLETION exceeds `max_drain_wait_sec`, force-release remaining leases and proceed to TERMINATE.
4. **RELEASE_LEASES before TERMINATE**: Required by §15.9.3 — terminating a worker with active leases violates LAW 3 (Lease integrity).

### 4. Scaling Decision Algorithm (Pseudocode)

```
Input:  snapshot (ClusterSnapshot), policy (ScalingPolicy), history (List[ScalingSignalRecord])
Output: signal (ScalingSignal)

1. utilization = max(snapshot.load.cpu_pct, snapshot.load.mem_pct) / 100.0
2. last_action = latest_scaling_timestamp(history)
3. last_two_signals = latest_n_signals(history, 2)

4. if not cooldown_expired(last_action, policy.cooldown_sec):
5.     return HOLD

6. if utilization > policy.target_utilization + policy.hysteresis_pct:
7.     if last_two_signals == [UP, UP]:
8.         return UP
9.     return HOLD   # need 2 consecutive UP evaluations

10. if utilization < policy.target_utilization - policy.hysteresis_pct:
11.    if last_two_signals == [DOWN, DOWN]:
12.        return DOWN
13.    if worker_surplus >= 2:
14.        return DRAIN
15.    return HOLD   # need 2 consecutive DOWN evaluations

16. return HOLD   # within hysteresis band
```

### 5. Compliance Matrix

| Rule | Implementation Point | Verification |
|------|--------------------|--------------|
| §15.9.4 Cooldown | Guard 3 — cooldown_expired check | cooldown_sec >= 60 |
| §15.9.4 Hysteresis | Guard 1, 2 — dead-band + consecutive cycles | hysteresis_pct >= 0.05 |
| §15.9.4 Oscillation-free | All 4 guards combined | No UP→DOWN→UP within cooldown window |
| §15.9.3 Drain lifecycle | Section 3 — 5-phase drain | RELEASE_LEASES before TERMINATE |
| LAW 3 (Lease integrity) | Drain Guard 4 | Force-release before terminate |
