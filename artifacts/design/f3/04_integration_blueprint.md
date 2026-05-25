# Phase F3 — Integration Blueprint: Resource Scheduler ↔ F2 Control Plane ↔ F1 API ↔ D8 Mesh

## 1. Architecture Overview

```
┌────────────────────────────────────────────────────────────────────────┐
│                           F1 UnifiedRuntime                            │
│  submit() → resume() → cancel() → observe() → replay() → scale()      │
└────────────────────────┬───────────────────────────────────────────────┘
                         │ F1.submit() triggers resource request
                         ▼
┌────────────────────────────────────────────────────────────────────────┐
│                        F2 ControlPlane                                 │
│  reconcile() → enforce_policy() → publish_state() → drain_worker()     │
└────────────────────────┬───────────────────────────────────────────────┘
                         │ F2.reconcile() invokes F3 for worker assignment
                         ▼
┌────────────────────────────────────────────────────────────────────────┐
│                        F3 ResourceScheduler                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌────────────┐│
│  │ IResourceScheduler │QuotaArbitrator│ FairnessEngine│TopologyMapper│
│  └───────┬──────┘  └──────┬───────┘  └──────┬───────┘  └─────┬──────┘│
└──────────┼─────────────────┼─────────────────┼─────────────────┼───────┘
           │                 │                 │                 │
           ▼                 ▼                 ▼                 ▼
┌────────────────────────────────────────────────────────────────────────┐
│                         D8 Service Mesh                                │
│  EventBus │ Scheduler │ StateStore │ Dispatcher │ LeaseManager         │
└────────────────────────────────────────────────────────────────────────┘
           │
           ▼
┌────────────────────────────────────────────────────────────────────────┐
│                          Worker Node                                   │
│  Execution │ Checkpoint │ Resource Monitoring                          │
└────────────────────────────────────────────────────────────────────────┘
```

## 2. End-to-End Flow: F1.submit() → Worker Assignment

```
F1.submit(dag)
    │
    ├─ 1. Create ResourceRequest from DAG requirements
    │      - cpu_cores = sum of tool resource estimates
    │      - memory_mb = max tool memory requirement
    │      - priority = from SubmissionOptions
    │
    ├─ 2. F3.IQuotaArbitrator.check_quota(execution_id, request, policy)
    │      - Check execution-level quota
    │      - Check worker pool global quota
    │      - RETURN: True/False
    │
    ├─ 3. If quota check fails → F3.IResourceScheduler → QUEUE or REJECT
    │
    ├─ 4. F3.IFairnessEngine.compute_fair_share(worker_id, total, active)
    │      - Compute fair per-execution allocation
    │      - Check for starvation of queued requests
    │      - Apply priority boost if needed
    │
    ├─ 5. F3.ITopologyMapper.map_to_hardware(request, available_offers)
    │      - Get available offers from F2 ControlPlane
    │      - Score offers by topology match
    │      - RETURN: TopologyMapping
    │
    ├─ 6. F3.IResourceScheduler.match_resources(request, scored_offers)
    │      - Assign best worker
    │      - Or preempt if needed
    │      - Or queue
    │      - RETURN: SchedulingDecision
    │
    ├─ 7. If ASSIGNED:
    │      - F3.IResourceScheduler.assign_worker(decision, offer)
    │      - F3.IQuotaArbitrator.consume_usage(execution_id, request)
    │      - F2.ControlPlane registers worker via F1.register_worker()
    │      - D8.Scheduler dispatches to worker
    │
    ├─ 8. If QUEUED:
    │      - Add to pending queue
    │      - StarvationDetection monitors wait_time
    │
    ├─ 9. If PREEMPTED:
    │      - F3.IResourceScheduler.preempt_if_needed()
    │      - D8.LeaseManager releases preempted leases
    │      - Checkpoint and re-queue preempted execution
    │      - Assign freed resources to new request
    │
    └─ 10. On completion/failure:
           - F3.IResourceScheduler.release_resources(execution_id, assign)
           - F3.IQuotaArbitrator.refund_on_failure() if failed
           - EventBus: runtime.resource.released
```

## 3. Connection Points to F1 API (Phase F1)

| F1 Method | F3 Consumer | Purpose |
|-----------|-------------|---------|
| `submit(dag, options)` | IResourceScheduler.match_resources | Create ResourceRequest from DAG; assign worker |
| `scale(target, policy)` | IQuotaArbitrator.check_quota | Verify quota before scaling; update pool limits |
| `observe(execution_id)` | IFairnessEngine.compute_fair_share | Report resource metrics in observation snapshot |
| ExecutionOptions.priority | PriorityTier mapping | Map submission priority to resource priority tier |

## 4. Connection Points to F2 Control Plane (Phase F2)

| F2 Component | F3 Consumer | Purpose |
|-------------|-------------|---------|
| ControlPlane.publish_state() | IResourceScheduler.match_resources | Get available worker offers from cluster state |
| ControlPlane.drain_worker() | IResourceScheduler.release_resources | Release resources on drain; reassign active |
| Autoscaler.apply_scaling() | IQuotaArbitrator | Adjust global quota pool on scale events |
| ReconciliationLoop.observe_current() | IFairnessEngine.balance_load | Feed worker load data for fairness rebalancing |

## 5. Connection Points to D8 Service Mesh

| D8 Service | F3 Consumer | Purpose |
|------------|-------------|---------|
| EventBus | All F3 components | Publish/consume resource events (runtime.resource.*) |
| ExecutionScheduler | IResourceScheduler.assign_worker | Route execution to assigned worker |
| ExecutionLeaseManager | Preemption path | Force-release leases on preempted execution |
| ExecutionStateStore | IQuotaArbitrator | Persist quota usage and reservation state |

## 6. EventBus Topics (F3)

| Topic | Publisher | Subscriber | Payload |
|-------|-----------|------------|---------|
| `runtime.resource.requested` | IResourceScheduler | IQuotaArbitrator | ResourceRequest |
| `runtime.resource.assigned` | IResourceScheduler | F2, D8 | SchedulingDecision |
| `runtime.resource.queued` | IResourceScheduler | IFairnessEngine | SchedulingDecision |
| `runtime.resource.preempted` | IResourceScheduler | D8.LeaseManager | SchedulingDecision (with preempted_id) |
| `runtime.resource.released` | IResourceScheduler | IQuotaArbitrator | AssignmentRecord |
| `runtime.quota.exceeded` | IQuotaArbitrator | F2, Monitoring | QuotaUsage |
| `runtime.quota.refunded` | IQuotaArbitrator | F2 | QuotaUsage |
| `runtime.fairness.rebalanced` | IFairnessEngine | IResourceScheduler | FairShareSnapshot |
| `runtime.starvation.detected` | IFairnessEngine | IResourceScheduler | StarvationReport |
| `runtime.topology.mapped` | ITopologyMapper | IResourceScheduler | TopologyMapping |

## 7. Resource Reservation Strategy

### Soft Reservation Flow
```
1. Request submitted with soft_reserve=True
2. Resources marked as reserved in QuotaPool (not deducted from offers)
3. TTL clock starts (default 60s)
4. If execution starts within TTL → convert to hard reservation
5. If TTL expires → resources released; request re-queued
6. Low-priority executions can borrow soft-reserved resources if:
     - Unused for > 30s
     - Borrowing execution is preemptible
```

### Hard Reservation Flow
```
1. Request submitted with hard_reserve=True (CRITICAL/HIGH priority)
2. Resources deducted from available offers immediately
3. No borrowing allowed
4. If execution fails → refund_on_failure releases hard reservation
```

## 8. Acceptance Criteria

### 8.1 Latency Budgets

| Operation | Budget | Criticality |
|-----------|--------|-------------|
| ResourceRequest → SchedulingDecision (match) | ≤ 50ms | High |
| Quota check (check_quota) | ≤ 10ms | High |
| Fair share computation | ≤ 30ms | Medium |
| Starvation detection cycle | ≤ 20ms | Medium |
| Topology mapping (map_to_hardware) | ≤ 50ms | High |
| Preemption decision (preempt_if_needed) | ≤ 100ms | Medium |
| Resource release (release_resources) | ≤ 20ms | High |

### 8.2 Idempotency Guarantees

| Operation | Idempotent? | Strategy |
|-----------|-------------|----------|
| `match_resources` | Yes | Same request + offers → same decision (pure) |
| `assign_worker` | Yes | Already assigned → return existing assignment |
| `preempt_if_needed` | Yes | Already preempted → return existing decision |
| `check_quota` | Yes | Read-only — no side effects |
| `consume_usage` | Yes | Dedup by execution_id |
| `refund_on_failure` | Yes | Double-refund → clamp at 0 |

### 8.3 Backpressure Handling

| Condition | Mechanism | Effect |
|-----------|-----------|--------|
| Queue depth > 100 | Throttle new submissions | New requests immediately REJECTED with "backpressure" |
| Quota hard limit hit | Cooldown timer starts | Further requests from same execution_id blocked for cooldown_sec |
| Preemption rate > 5/min | Circuit breaker | New preemptions blocked until rate drops |
| Starvation detected > 3 per cycle | Escalation | Emit runtime.starvation.escalation event to F2 |
| Topology mapping failures > 10% | Fallback-only mode | Skip topology scoring; use first-fit matching |

### 8.4 Rollback on Preemption

```
1. Preemption triggered → SchedulingDecision(status=PREEMPTED)
2. D8.LeaseManager.force_release(execution_id) — release leases
3. Checkpoint current state via F1.replay() → F1.checkpoint
4. Emit runtime.resource.preempted(preempted_id)
5. Preempted execution re-queued with priority boost (if preemptible)
6. New execution assigned to freed resources
7. On completion of new execution: re-evaluate queued preempted execution
```
