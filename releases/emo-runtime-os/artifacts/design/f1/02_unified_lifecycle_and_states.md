# Phase F1 — Unified Lifecycle & State Machine

> Design document covering the unified execution state machine, transition guards,
> and API → Service Mesh routing for IUnifiedRuntimeAPI.
>
> Ref: DEVELOPER.md §15.2, §15.3, §15.12
> Ref: Canon LAW 1-13, RULE 1-5
> Ref: Phase D8 Service Mesh Contracts

---

## 1. Unified State Machine

### 1.1 State Diagram

```
                       ┌──────────────────────────────────────────────┐
                       │                                              │
                       ▼                                              │
                   ┌─────────┐                                       │
          submit() │         │ resume()                               │
        ┌─────────▶│SUBMITTED│◀────────────────────┐                 │
        │          └────┬────┘                      │                 │
        │               │ validate                  │                 │
        │               ▼                           │                 │
        │          ┌─────────┐                      │                 │
        │          │ QUEUED  │                      │                 │
        │          └────┬────┘                      │                 │
        │               │ lease acquired            │                 │
        │               ▼                           │                 │
        │          ┌─────────┐                      │                 │
        │          │ LEASED  │                      │                 │
        │          └────┬────┘                      │                 │
        │               │ schedule()                │                 │
        │               ▼                           │                 │
        │          ┌──────────┐                     │                 │
        │          │ PLANNING │                     │                 │
        │          └────┬─────┘                     │                 │
        │               │ level dispatch            │                 │
        │               ▼                           │                 │
        │          ┌──────────┐                     │                 │
        │          │EXECUTING │                     │                 │
        │          └──┬───┬───┘                     │                 │
        │             │   │                         │                 │
        │     ┌───────┘   └───────┐                 │                 │
        │     ▼                   ▼                 │                 │
        │  ┌───────┐         ┌────────┐            │                 │
        │  │FAILED │         │CANCELLED│            │                 │
        │  └───┬───┘         └───┬────┘            │                 │
        │      │ rollback()      │ release          │                 │
        │      ▼                 ▼                  │                 │
        │  ┌──────────┐    ┌──────────┐            │                 │
        │  │ROLLED_BACK│    │ TERMINAL │            │                 │
        │  └──────────┘    └──────────┘            │                 │
        │                                          │                 │
        │           ┌──────────┐                   │                 │
        │           │COMPLETED │                   │                 │
        │           └──────────┘                   │                 │
        │                                          │                 │
        │           ┌──────────┐                   │                 │
        │           │REPLAYING │ (replay path)     │                 │
        │           └──────────┘                   │                 │
        │                                          │                 │
        │           ┌──────────┐                   │                 │
        │           │ ORPHANED │ ← lease expires   │                 │
        │           └──────────┘                   │                 │
        │                │ recover()               │                 │
        │                ▼                         │                 │
        │           ┌──────────┐                   │                 │
        │           │RECOVERED │───────────────────┘                 │
        │           └──────────┘                                     │
        │                                                             │
        └─────────────────────────────────────────────────────────────┘
```

### 1.2 State Definitions

| State | Meaning | Entry Condition | Exit Condition |
|-------|---------|-----------------|----------------|
| **SUBMITTED** | DAG received, validation pending | `submit()` called | DAG passes validation |
| **QUEUED** | DAG valid, awaiting schedule slot | Available capacity > 0 | Lease acquired |
| **LEASED** | Execution lease acquired, ready to plan | `IExecutionLeaseManager.acquire_lease()` OK | `IExecutionScheduler.schedule()` called |
| **PLANNING** | Nodes partitioned into levels | DAG levels computed | First level dispatched |
| **EXECUTING** | Nodes actively running | `IExecutionDispatcher.dispatch()` called | All levels completed |
| **COMPLETED** | All nodes succeeded | No remaining nodes + no errors | Terminal |
| **FAILED** | Non-retryable node failure | `IExecutionRetryHandler.decide_retry()` = False | `ROLLED_BACK` |
| **CANCELLED** | User-initiated stop | `cancel()` called | `TERMINAL` or `ROLLED_BACK` |
| **ROLLED_BACK** | Partial execution undone | Rollback complete | Terminal |
| **REPLAYING** | Deterministic re-execution | `replay()` called | Same as submit path |
| **ORPHANED** | Lease expired, worker unreachable | Heartbeat timeout | `RECOVERED` or `FAILED` |
| **RECOVERED** | Execution reclaimed by new owner | Lease re-acquired | `QUEUED` (for resume) |
| **TERMINAL** | Final cancelled state | Cleanup complete | Terminal |

### 1.3 State Transition Table

| From | To | Trigger | Guard Condition |
|------|----|---------|-----------------|
| SUBMITTED | QUEUED | validate_dag passes | `ExecutionCore.validate_dag(dag)` returns empty `errors` |
| SUBMITTED | FAILED | validate_dag fails | `errors` non-empty |
| QUEUED | LEASED | acquire_lease succeeds | `IExecutionLeaseManager.acquire_lease()` returns lease_id |
| QUEUED | FAILED | acquire_lease fails | `QuotaExceeded` or `LeaseConflict` |
| LEASED | PLANNING | schedule() succeeds | `IExecutionScheduler.schedule()` returns levels |
| LEASED | FAILED | schedule() fails | `SchedulingError` (cycle or invalid deps) |
| PLANNING | EXECUTING | dispatch first level | `IExecutionDispatcher.dispatch_tool_call()` succeeds |
| PLANNING | CANCELLED | cancel() during planning | `cancel_flag.is_set()` |
| EXECUTING | COMPLETED | all levels done + no failures | Level queue empty, all results success |
| EXECUTING | FAILED | node failure + no retry | `IExecutionRetryHandler.decide_retry()` == False |
| EXECUTING | CANCELLED | cancel() during execution | User or system invokes cancel |
| EXECUTING | ORPHANED | lease expiry | `IExecutionLeaseManager.monitor_heartbeat()` == False |
| FAILED | ROLLED_BACK | rollback complete | `IExecutionStateStore.load_state()` + `IExecutionScheduler.schedule()` reverse |
| CANCELLED | TERMINAL | cleanup + lease release | `IExecutionLeaseManager.release_lease()` succeeds |
| ROLLED_BACK | (terminal) | cleanup complete | State persisted |
| REPLAYING | COMPLETED | replay execution succeeds | All steps match original trace |
| REPLAYING | FAILED | replay mismatch | Output hash differs |
| ORPHANED | RECOVERED | lease re-acquired | `IExecutionLeaseManager.acquire_lease()` returns new lease_id |
| ORPHANED | FAILED | recovery impossible | No checkpoint or max recovery attempts exceeded |
| RECOVERED | QUEUED | resume from checkpoint | `IExecutionStateStore.has_checkpoint()` == True |
| COMPLETED | REPLAYING | replay() called | Trace available |
| TERMINAL | (none) | — | Terminal state |

---

## 2. Transition Guards

### 2.1 Guard Matrix

| Transition | Guard Function | Precondition | Postcondition |
|-----------|---------------|--------------|---------------|
| SUBMITTED → QUEUED | `check_dag_valid(dag)` | DAG has nodes | DAG nodes validated |
| QUEUED → LEASED | `can_acquire_lease(exec_id, owner)` | Capacity available | Lease held by owner |
| LEASED → PLANNING | `can_schedule(dag)` | DAG acyclic | Levels computed |
| PLANNING → EXECUTING | `can_dispatch(level)` | Level has dispatchable nodes | Nodes dispatched |
| EXECUTING → COMPLETED | `all_nodes_done(results)` | No pending nodes | Telemetry archived |
| EXECUTING → FAILED | `is_terminal_failure(error, attempt)` | `decide_retry()` == False | Error classified |
| EXECUTING → CANCELLED | `cancel_flag.is_set()` | Cancel requested | Executions killed |
| EXECUTING → ORPHANED | `heartbeat_timed_out()` | No heartbeat > TTL | Lease expired |
| FAILED → ROLLED_BACK | `can_rollback(dag, failed_node)` | Rollback graph computed | State restored |
| ORPHANED → RECOVERED | `checkpoint_exists(session_id)` | StateStore has checkpoint | Lease re-acquired |
| RECOVERED → QUEUED | `can_resume(ticket_id)` | State is resumable | State restored |
| COMPLETED → REPLAYING | `trace_available(exec_id)` | Trace exists | Replay started |

### 2.2 Idempotency Guarantees

| Operation | Idempotent? | Mechanism |
|-----------|-------------|-----------|
| `submit()` | ✅ (via dag hash) | Same DAG hash → returns existing ticket |
| `resume()` | ✅ (via checkpoint ID) | Same checkpoint → restores same state |
| `cancel()` | ✅ | Cancel of already-cancelled returns success |
| `observe()` | ✅ | Read-only, no side effects |
| `replay()` | ✅ (via execution ID) | Same trace → same replay |
| `scale()` | ✅ (via policy) | Same target count → no-op |
| `register_worker()` | ✅ (via worker_id) | Same worker → returns existing registration |

### 2.3 Guard Implementation Contracts

```python
# Each guard is a pure function — no side effects, deterministic.

def guard_submit_to_queued(dag: DependencyGraph) -> Tuple[bool, List[str]]:
    """Guard: DAG must be valid (LAW 1, LAW 7)."""
    errors = ExecutionCore.validate_dag(dag)
    return (len(errors) == 0, errors)

def guard_queued_to_leased(exec_id: str, owner: str) -> Tuple[bool, Optional[str]]:
    """Guard: Lease must be available (LAW 3, LAW 10)."""
    lease_id = LeaseManager.acquire_lease(exec_id, owner)
    return (lease_id is not None, lease_id)

def guard_executing_to_completed(results: Dict[str, Any]) -> bool:
    """Guard: All nodes must have completed status (LAW 8)."""
    return all(r.get("status") == "completed" for r in results.values())

def guard_executing_to_cancelled(flag: Event) -> bool:
    """Guard: Cancel flag must be set (RULE 4)."""
    return flag.is_set()

def guard_orphaned_to_recovered(session_id: str) -> bool:
    """Guard: Checkpoint must exist for recovery (LAW 4, LAW 8)."""
    return StateStore.has_checkpoint(session_id)
```

---

## 3. API → Service Mesh Routing

### 3.1 submit() Routing

```
submit(dag, context, options)
  │
  ├── 1. ExecutionCore.validate_dag(dag)                → LAW 1
  ├── 2. IExecutionLeaseManager.acquire_lease()          → LAW 3
  ├── 3. IExecutionStateStore.store_checkpoint()         → LAW 12
  ├── 4. IExecutionScheduler.schedule(dag, strategy)     → LAW 23
  ├── 5. IExecutionDispatcher.dispatch_tool_call()       → LAW 24
  ├── 6. IEventBus.publish("EXECUTION_SUBMITTED")        → LAW 5
  │
  └── Return: ExecutionTicket
```

### 3.2 resume() Routing

```
resume(ticket_id, from_checkpoint)
  │
  Guard: IExecutionStateStore.has_checkpoint(ticket_id)
  │
  ├── 1. IExecutionStateStore.read_trace(ticket_id)      → LAW 12
  ├── 2. IExecutionStateStore.load_state(node_id)         → LAW 26
  ├── 3. IExecutionLeaseManager.acquire_lease()           → LAW 3
  ├── 4. IExecutionScheduler.schedule(remaining_nodes)    → LAW 23
  ├── 5. IExecutionDispatcher.dispatch_tool_call()        → LAW 24
  ├── 6. IEventBus.publish("EXECUTION_RESUMED")           → LAW 5
  │
  └── Return: ExecutionStatus
```

### 3.3 cancel() Routing

```
cancel(ticket_id, reason, force)
  │
  Guard: not is_terminal(state)
  │
  ├── 1. ExecutionEngine.cancel()                         → RULE 4
  ├── 2. IExecutionScheduler.collect_futures()             → LAW 23
  ├── 3. ISandboxExecutor.kill(exec_id)                    → RULE 4
  ├── 4. IExecutionLeaseManager.release_lease()            → LAW 3
  ├── 5. IExecutionStateStore.store_checkpoint()           → LAW 8
  ├── 6. IEventBus.publish("EXECUTION_CANCELLED")          → LAW 5
  │
  └── Return: CancellationReceipt
```

### 3.4 observe() Routing

```
observe(ticket_id, stream=False)
  │
  ├── 1. IExecutionStateStore.read_trace(ticket_id)       → LAW 12
  ├── 2. IExecutionLeaseManager.monitor_heartbeat()        → LAW 3
  ├── 3. Build LiveStateStream from state
  ├── 4. If stream: subscribe to IEventBus live updates    → LAW 5
  │
  └── Return: LiveStateStream
```

### 3.5 replay() Routing

```
replay(execution_id, deterministic=True)
  │
  Guard: IExecutionStateStore.read_trace(execution_id) exists
  │
  ├── 1. IExecutionStateStore.read_trace(execution_id)    → LAW 4
  ├── 2. IExecutionStateStore.store_checkpoint()           → LAW 8
  ├── 3. Freeze random seeds (if deterministic)
  ├── 4. IExecutionScheduler.schedule(replay_nodes)        → LAW 23
  ├── 5. IExecutionDispatcher.dispatch_tool_call()         → LAW 24
  ├── 6. Compare output hashes
  ├── 7. IEventBus.publish("REPLAY_COMPLETED")             → LAW 5
  │
  └── Return: ReplayTicket
```

### 3.6 scale() Routing

```
scale(target_worker_count, policy)
  │
  ├── 1. Calculate delta = target - current
  ├── 2. If delta > 0: IExecutionLeaseManager.acquire_lease() per new worker
  ├── 3. If delta < 0: drain + IExecutionLeaseManager.release_lease()
  ├── 4. IExecutionScheduler.rebalance(policy)             → LAW 23
  ├── 5. IEventBus.publish("WORKER_POOL_SCALED")           → LAW 5
  │
  └── Return: ScalingReceipt
```

### 3.7 register_worker() Routing

```
register_worker(worker_manifest)
  │
  ├── 1. Validate manifest (worker_id, capabilities, endpoints)
  ├── 2. WorkerRegistry.register(manifest)                 → §15.4
  ├── 3. IExecutionLeaseManager.acquire_lease(worker_id)   → LAW 3
  ├── 4. IEventBus.publish("WORKER_REGISTERED")            → LAW 5
  │
  └── Return: WorkerRegistration
```

---

## 4. Concurrency & Consistency Rules

| API Method | Concurrency Model | Consistency | Lock Scope |
|-----------|------------------|-------------|------------|
| `submit()` | Serial (per DAG) | STRONG | DAG-level write lock |
| `resume()` | Serial (per ticket) | STRONG | Checkpoint read lock |
| `cancel()` | Parallel (per node kill) | STRONG | Lease-level lock |
| `observe()` | Parallel (read-only) | EVENTUAL | None (read-only) |
| `replay()` | Serial (deterministic) | STRONG | Execution-level lock |
| `scale()` | Serial (pool mutation) | EVENTUAL | Worker pool lock |
| `register_worker()` | Serial (registry mutation) | STRONG | Registry write lock |

### 4.1 Backpressure Rules

| Method | Backpressure Strategy | Max Queue |
|--------|----------------------|-----------|
| `submit()` | Reject when queue > max_pending | 1000 DAGs |
| `resume()` | Same as submit | 100 |
| `cancel()` | Fire-and-forget (lease-level) | Unlimited |
| `observe()` | Drop oldest when stream buffer full | 1000 events |
| `replay()` | Serial queue per execution_id | 10 |
| `scale()` | Synchronous, block until complete | 1 |
| `register_worker()` | Synchronous | 10 concurrent |
