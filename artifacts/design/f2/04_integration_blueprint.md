# Phase F2 — Integration Blueprint: Control Plane ↔ F1 API ↔ D8 Mesh

## 1. Architecture Overview

```
                    ┌──────────────────────┐
                    │    F1 UnifiedRuntime  │
                    │  (register_worker,    │
                    │   scale, observe)     │
                    └──────┬───────────┬────┘
                           │           │
                    ┌──────▼───┐ ┌─────▼──────┐
                    │ Control  │ │  EventBus   │
                    │  Plane   │ │ (D8 Mesh)   │
                    │  F2      │ │             │
                    └──┬───┬───┘ └──┬───┬───┬──┘
                       │   │        │   │   │
              ┌────────▼───▼──┐  ┌──▼───▼───▼────┐
              │  IAutoscaler  │  │ IHealthSuperv. │
              │  (scaling)    │  │ (probe/evict)  │
              └───────────────┘  └────────────────┘
```

## 2. Data Flow: HealthSupervisor → EventBus → Autoscaler → ControlPlane → F1

### Step-by-Step Flow

```
                        ┌──────────┐
                        │  Worker  │
                        └────┬─────┘
                             │
                  1. probe   │  (IHealthSupervisor.probe_worker)
                             ▼
                   ┌──────────────────┐
                   │ HealthSupervisor │
                   └────────┬─────────┘
                            │
                 2. assess  │  (assess_degradation)
                            ▼
                   ┌──────────────────┐
                   │ DegradationLevel │
                   └────────┬─────────┘
                            │
              3. publish    │  (publish_health_event → EventBus)
                            ▼
                   ┌──────────────────┐
                   │  EventBus (D8)   │
                   │  runtime.health.*│
                   └────────┬─────────┘
                            │
              4. consume    │  (IAutoscaler triggered by health event)
                            ▼
                   ┌──────────────────┐
                   │   IAutoscaler    │
                   │  (evaluate_load) │
                   └────────┬─────────┘
                            │
              5. signal     │  (ScalingSignal: UP/DOWN/HOLD/DRAIN)
                            ▼
                   ┌──────────────────┐
                   │  IControlPlane   │
                   │  (reconcile,     │
                   │   enforce_policy)│
                   └────────┬─────────┘
                            │
              6. apply      │  (F1 API.register_worker / drain_worker)
                            ▼
                   ┌──────────────────┐
                   │ F1 UnifiedRuntime │
                   └──────────────────┘
```

## 3. Connection Points to F1 API (Phase F1)

| F1 Method | F2 Consumer | Purpose |
|-----------|-------------|---------|
| `register_worker(manifest)` | IControlPlane.enforce_policy → IAutoscaler.apply_scaling | Register new workers during SCALE_UP |
| `scale(target_count, policy)` | IAutoscaler.apply_scaling | Trigger scaling via F1 scale path |
| `observe(execution_id)` | IReconciliationLoop.observe_current | Pull cluster state for reconciliation |
| `runtime.execution.*` (EventBus) | IHealthSupervisor | Monitor execution health per worker |

## 4. Connection Points to D8 Mesh (Phase D8)

| D8 Service | F2 Consumer | Purpose |
|------------|-------------|---------|
| EventBus | All F2 components | Publish/consume health, scaling, and reconciliation events |
| FailureMatrix | IHealthSupervisor | Classify worker failures (F01-F08) for degradation assessment |
| ExecutionScheduler | IReconciliationLoop | Drain workers by removing from scheduler pool |
| ExecutionLeaseManager | Worker draining lifecycle | Force-release leases during RELEASE_LEASES phase |
| ExecutionStateStore | IReconciliationLoop | Query worker state and lease counts |

## 5. EventBus Topics (F2)

| Topic | Publisher | Subscriber | Payload |
|-------|-----------|------------|---------|
| `runtime.health.probe` | IHealthSupervisor | IAutoscaler | HealthProbeResult |
| `runtime.health.degraded` | IHealthSupervisor | IControlPlane | HealthEvent (MINOR/MAJOR) |
| `runtime.health.critical` | IHealthSupervisor | IControlPlane, IAutoscaler | HealthEvent (CRITICAL) |
| `runtime.health.recovered` | IHealthSupervisor | IAutoscaler | HealthEvent (NONE) |
| `runtime.scaling.signal` | IAutoscaler | IControlPlane | ScalingSignalRecord |
| `runtime.scaling.applied` | IControlPlane | All | ScalingReceipt |
| `runtime.scaling.throttled` | IControlPlane | All | PolicyResult |
| `runtime.reconcile.report` | IReconciliationLoop | IControlPlane | ReconcileReport |
| `runtime.worker.draining` | IControlPlane | Scheduler, LeaseManager | DrainReceipt |
| `runtime.worker.drained` | IControlPlane | All | DrainReceipt |
| `runtime.worker.terminated` | IControlPlane | All | EvictionReceipt |

## 6. Reconciliation Interval Strategy

Per §15.9.2, the reconciliation loop operates on three tiered intervals:

| Phase | Interval | Action |
|-------|----------|--------|
| **OBSERVE** | Every **5s** | `IReconciliationLoop.observe_current()` — collect cluster snapshot |
| **EVALUATE** | Every **15s** | `IReconciliationLoop.compare_desired()` + `IAutoscaler.evaluate_load()` — compute drift |
| **ACT** | Every **30s** | `IControlPlane.reconcile()` — schedule and apply corrections |

### Timer Diagram
```
OBSERVE:  |●────●────●────●────●────●────●────●────●────●|
          | 5s | 5s | 5s | 5s | 5s | 5s | 5s | 5s | 5s |
EVALUATE: |●──────────●──────────●──────────●──────────●|
          |    15s     |    15s     |    15s     |    15s |
ACT:      |●─────────────────────●─────────────────────●|
          |        30s           |        30s           |
```

## 7. Hook Points for Critical Events

| Event | Hook | Emitter | Consumer |
|-------|------|---------|----------|
| Worker churn | `runtime.worker.drained` + `runtime.worker.terminated` | IControlPlane | IReconciliationLoop |
| Capacity exhausted | `runtime.scaling.throttled` (reason = "max_workers") | IControlPlane | Monitoring/Alerting |
| Scaling throttled | `runtime.scaling.throttled` (reason = "cooldown") | IControlPlane | IAutoscaler (backoff) |

## 8. Acceptance Criteria

### 8.1 Latency Budgets

| Operation | Budget | Criticality |
|-----------|--------|-------------|
| Worker probe (IHealthSupervisor.probe_worker) | ≤ 100ms | High — blocking path |
| Load evaluation (IAutoscaler.evaluate_load) | ≤ 50ms | High — per-cycle |
| Scaling application (IApplyScaling) | ≤ 500ms | Medium — non-blocking |
| Reconciliation cycle (full) | ≤ 2s | Medium — every 30s |
| EventBus publish (any topic) | ≤ 10ms | High — non-blocking |

### 8.2 Idempotency Guarantees

| Operation | Idempotent? | Strategy |
|-----------|-------------|----------|
| `register_worker` | Yes | Duplicate manifest → return existing registration |
| `drain_worker` | Yes | Already DRAINING → return existing DrainReceipt |
| `trigger_eviction` | Yes | Already TERMINATED → return existing EvictionReceipt |
| `publish_health_event` | Yes | Dedup by event_id within 5s window |
| `apply_scaling` | Yes | Same target_count + same current_count → no-op |

### 8.3 Backpressure Handling

| Condition | Mechanism | Effect |
|-----------|-----------|--------|
| EventBus queue > 1000 events | Throttle publish | Drop lowest-priority health events |
| Scaling requests > 3x in cooldown | Circuit breaker | All scaling requests return HOLD until cooldown |
| Probe failures > 5 consecutive | Exponential backoff | Probe interval increases: 5s → 10s → 20s → 40s |
| Reconciliation drift > 10% | Escalation | Emit `runtime.reconcile.escalation` event |
