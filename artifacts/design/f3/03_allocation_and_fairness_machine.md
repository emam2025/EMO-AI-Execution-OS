# Phase F3 — Resource Allocation & Starvation-Prevention State Machine

## 1. Resource Allocation State Machine

### States

| State | Description | Terminal |
|-------|-------------|----------|
| `REQUEST_RECEIVED` | Resource request submitted | No |
| `QUOTA_CHECK` | Validate against quota policy | No |
| `FAIRNESS_EVAL` | Evaluate fair share and detect starvation | No |
| `RESOURCE_MATCH` | Match request against available offers | No |
| `ASSIGN` | Assign resources and worker | No |
| `QUEUE` | Insufficient resources — enqueue for later | No |
| `PREEMPT` | Preempt lower-priority execution | No |
| `REJECT` | Cannot satisfy request | Yes |

### Transition Map

```
    REQUEST_RECEIVED
           │
           ▼
     QUOTA_CHECK ────[hard limit exceeded]───→ REJECT
           │
           ▼
    FAIRNESS_EVAL ────[starvation detected]───→ [priority boost] ──→ (loop back)
           │
           ▼
    RESOURCE_MATCH
           │
     ┌─────┼──────────┬──────────┐
     ▼     ▼          ▼          ▼
   ASSIGN QUEUE    PREEMPT    REJECT
     │     │          │
     │     └──────────┤
     └────────────────┘
           │
           ▼
       [complete] → release_resources
```

### Transition Guards

| From | To | Guard Condition |
|------|----|-----------------|
| `REQUEST_RECEIVED` | `QUOTA_CHECK` | ResourceRequest has valid execution_id |
| `QUOTA_CHECK` | `FAIRNESS_EVAL` | Quota available (usage < hard_limit) |
| `QUOTA_CHECK` | `REJECT` | usage >= hard_limit OR cooldown active |
| `FAIRNESS_EVAL` | `RESOURCE_MATCH` | Fair share computed, no critical imbalance |
| `FAIRNESS_EVAL` | `FAIRNESS_EVAL` | Starvation detected → apply_priority_boost |
| `RESOURCE_MATCH` | `ASSIGN` | Matching offer found with sufficient resources |
| `RESOURCE_MATCH` | `QUEUE` | No matching offer, but request is preemptible or low priority |
| `RESOURCE_MATCH` | `PREEMPT` | No matching offer, request priority >= HIGH, target found |
| `RESOURCE_MATCH` | `REJECT` | No match, no fallback, request cannot wait (max_wait_sec = 0) |
| `QUEUE` | `RESOURCE_MATCH` | Resources become available (re-evaluated on release) |
| `PREEMPT` | `ASSIGN` | Preemption successful, resources freed |
| `PREEMPT` | `QUEUE` | Preemption attempted but no viable target |

## 2. Preemption Guards

Preemption allows a high-priority request to take resources from a
lower-priority execution. All guards MUST be satisfied:

### Guard 1: Priority Gate
```
preemption_allowed = (
    request.priority in (PriorityTier.CRITICAL, PriorityTier.HIGH)
    AND target.priority in (PriorityTier.LOW, PriorityTier.BATCH)
    AND priority_diff(request.priority, target.priority) >= 2
)
```
Priority diff calculation: CRITICAL=5, HIGH=4, NORMAL=3, LOW=2, BATCH=1
Requires difference >= 2 (e.g., HIGH can preempt BATCH, CRITICAL can preempt LOW).

### Guard 2: Age Threshold
```
preemption_allowed = preemption_allowed AND target.age > 60.0
```
Executions younger than 60 seconds are not preempted (stability guard).

### Guard 3: Checkpoint Availability
```
preemption_allowed = preemption_allowed AND target.checkpoint_available
```
Preemption is only allowed if the target execution can be gracefully
checkpointed (RULE 3 — Recoverability).

### Guard 4: Cooldown Per Worker
```
preemption_allowed = preemption_allowed AND not worker_in_preempt_cooldown(worker_id)
```
A worker can only be preempted once per cooldown period to prevent
thrashing.

### Preemption Algorithm Pseudocode
```
Input:  request (ResourceRequest), active (List[AssignmentRecord])
Output: decision (Optional[SchedulingDecision])

1. candidates = [a for a in active
                  if a.preemptible
                  and priority_diff(request.priority, a.resources.priority) >= 2
                  and age(a.assigned_at) > 60.0
                  and a.checkpoint_available]

2. if not candidates:
3.     return None   # No preemption possible

4. sort candidates by priority ascending (lowest first)
5. target = candidates[0]

6. return SchedulingDecision(
        status=PREEMPTED,
        assigned_worker=target.worker_id,
        preempted_id=target.execution_id,
        reason=f"Preempted {target.execution_id} for {request.execution_id}"
   )
```

## 3. Starvation Detection & Recovery

### Starvation Conditions

Starvation occurs when a request remains in QUEUED state beyond a
configurable threshold without receiving resources.

| Priority | Starvation Threshold | Action |
|----------|---------------------|--------|
| BATCH | 300s (5 min) | Boost to LOW |
| LOW | 120s (2 min) | Boost to NORMAL |
| NORMAL | 60s (1 min) | Boost to HIGH |
| HIGH | 30s | Notify — no boost (already high) |
| CRITICAL | 10s | Escalate — system alert |

### Priority Boost Rules

```
boost_map = {
    BATCH:  LOW,
    LOW:    NORMAL,
    NORMAL: HIGH,
    HIGH:   HIGH,     # No boost — already high
    CRITICAL: CRITICAL,  # No boost — already critical
}
```

### Starvation Detection Algorithm Pseudocode
```
Input:  queue (List[QueuedRequest])
Output: starved (List[StarvationReport])

1. for each request in queue:
2.     wait_time = now - request.submitted_at
3.     threshold = get_threshold(request.priority)
4.     if wait_time > threshold:
5.         new_priority = boost_map[request.priority]
6.         report = StarvationReport(
                       execution_id=request.execution_id,
                       wait_time_sec=wait_time,
                       priority=request.priority,
                       boost_applied=(new_priority != request.priority),
                       new_priority=new_priority,
                       action_taken=f"Boosted {request.priority} → {new_priority}"
                  )
7.         request.priority = new_priority
8.         reports.append(report)
9. return reports
```

### Recovery Path After Boost

```
Starvation Detected
    │
    ▼
Apply Priority Boost ──→ Re-evaluate on next cycle
    │
    ▼
[boost to NORMAL or HIGH] ──→ RESOURCE_MATCH ──→ (attempt assign again)
    │
    ▼
[boost already applied] ──→ Fallback Worker
    │
    ▼
Fallback assigned (relaxed topology constraints)
```

## 4. Resource Matching Algorithm

```
Input:  request (ResourceRequest), offers (List[ResourceOffer])
Output: decision (SchedulingDecision)

1. Filter offers where:
     offer.available_cpu >= request.cpu_cores
     AND offer.available_mem >= request.memory_mb
     AND (request.gpu_memory_mb == 0 OR GPU_AVAILABLE in offer.hardware_topology)

2. If no offers match:
     If request.max_wait_sec > 0 → QUEUE
     Else if request.priority in (CRITICAL, HIGH) → PREEMPT (try)
     Else → REJECT

3. Score remaining offers:
     for each offer:
         score = 0
         for each cap in request.hardware_requirements:
             if cap in offer.hardware_topology: score += 1.0
         for each affinity_tag:
             if tag in offer.affinity_tags: score += 0.5
         score -= (1 - offer.available_cpu / offer.total_cpu) * 0.2  # fragmentation penalty

4. Select highest-scored offer.
   Tie-break: prefer worker with more available CPU.

5. Return ASSIGNED with selected worker.
```

## 5. Resource Reservation Strategy (Soft vs Hard)

| Type | Mechanism | Use Case |
|------|-----------|----------|
| **Soft reservation** | Resources marked as reserved but not consumed; can be borrowed by lower-priority if unused within TTL | Standard executions with flexible start times |
| **Hard reservation** | Resources deducted from available pool immediately; cannot be borrowed | CRITICAL/HIGH priority, SLA-bound executions |
| **TTL on soft** | Soft reservation expires after `ttl_sec` if not consumed; resources re-released to pool | Prevents deadlock from abandoned reservations |

## 6. Compliance Matrix

| Rule | Implementation Point | Verification |
|------|--------------------|--------------|
| LAW 5 (Observability) | All scheduling states return SchedulingDecision with reason | decision.status and decision.reason mandatory |
| LAW 8 (Fairness) | Fair share computation + starvation detection + boost | imbalance_ratio monitored per cycle |
| LAW 10 (Resource limits) | Hard limit enforces rejection; soft limit warns | QuotaPolicy with soft_limit ≤ hard_limit |
| LAW 11 (No global state) | All trackers per-instance; no class-level mutable dicts | QuotaPool, AssignmentRecord are instance-scoped |
| RULE 1 (Determinism) | Scoring algorithm is pure; tie-break is deterministic | Same offers + same request → same score |
| RULE 2 (Reversibility) | refund_on_failure reverses quota consumption | QuotaUsage refund logic documented |
| RULE 3 (Recoverability) | Preemption requires checkpoint_available | Guard 3 — checkpoint must exist |
| RULE 4 (Terminal) | REJECT is terminal; no transition out of REJECT | State machine enforces REJECT finality |
| RULE 5 (Idempotency) | Preemption, assignment are idempotent | Double-preempt returns existing decision |
