# Phase F1 — Integration Blueprint

> Design document mapping IUnifiedRuntimeAPI → CompositionRoot → D8 Service Mesh → EventBus.
>
> Ref: DEVELOPER.md §15.2 (High-Level Architecture)
> Ref: DEVELOPER.md §15.12 (Runtime Decomposition Rules)
> Ref: Phase D8 Service Contracts (LAW 23-27)
> Ref: Canon LAW 13 (CompositionRoot), RULE 1 (No Direct Execution)

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Multi-Agent Layer                            │
│  (Planner, Critic, Optimizer, Memory, Negotiation, Coordination)    │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │               IUnifiedRuntimeAPI (Protocol)                  │  │
│  │  submit | resume | cancel | observe | replay | scale | reg   │  │
│  └───────────────────────────┬──────────────────────────────────┘  │
│                              │                                      │
│  ┌───────────────────────────▼──────────────────────────────────┐  │
│  │              CompositionRoot (LAW 13)                        │  │
│  │  ┌──────────────────────────────────────────────────────┐   │  │
│  │  │  UnifiedRuntime (Implementation)                     │   │  │
│  │  │  - validates inputs                                   │   │  │
│  │  │  - resolves dependencies                              │   │  │
│  │  │  - routes to D8 services                              │   │  │
│  │  │  - manages state machine                              │   │  │
│  │  │  - emits events                                       │   │  │
│  │  └───────────┬──────────────────────────────────────────┘   │  │
│  └──────────────┼──────────────────────────────────────────────┘  │
└─────────────────┼──────────────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│               D8 Service Mesh (LAW 23-27)                          │
│                                                                     │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐   │
│  │ Scheduler  │  │ Dispatcher │  │RetryHandler│  │ StateStore │   │
│  │ (LAW 23)   │  │ (LAW 24)   │  │ (LAW 25)   │  │ (LAW 26)   │   │
│  └──────┬─────┘  └──────┬─────┘  └──────┬─────┘  └──────┬─────┘   │
│         │               │               │               │          │
│         └───────────────┼───────────────┼───────────────┘          │
│                         │               │                          │
│                  ┌──────▼───────────────▼──────┐                   │
│                  │     LeaseManager (LAW 23)   │                   │
│                  └─────────────────────────────┘                   │
└─────────────────────────────────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     IEventBus (Phase 3.5)                          │
│  runtime.execution.submitted   runtime.execution.completed          │
│  runtime.execution.cancelled   runtime.execution.failed             │
│  runtime.worker.registered     runtime.worker.scaled                │
│  runtime.lease.acquired        runtime.lease.expired                │
│  runtime.state.transition      runtime.checkpoint.saved             │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. Flow: UnifiedRuntime → CompositionRoot → D8 Services

### 2.1 Dependency Injection Wiring

```python
# CompositionRoot — the ONLY valid construction point (LAW 13)
class CompositionRoot:
    def create_unified_runtime(self) -> UnifiedRuntime:
        # Resolve D8 service mesh
        scheduler = ExecutionScheduler()
        dispatcher = ExecutionToolDispatcher()
        retry_handler = ExecutionRetryHandler()
        state_store = ExecutionStateStore()
        lease_manager = ExecutionLeaseManager()

        # Resolve infrastructure
        event_bus = EventBus()
        execution_engine = ExecutionEngine(
            event_bus=event_bus,
            optimizer=DAGOptimizer(),
            checkpoint_manager=CheckpointManager(state_store),
        )
        sandbox = SandboxManager()

        # Build UnifiedRuntime
        return UnifiedRuntime(
            execution_engine=execution_engine,
            scheduler=scheduler,
            dispatcher=dispatcher,
            retry_handler=retry_handler,
            state_store=state_store,
            lease_manager=lease_manager,
            event_bus=event_bus,
            sandbox_manager=sandbox,
        )
```

### 2.2 Correlation ID Flow

```
                        trace_id = generate_uuid()
                        correlation_id = trace_id
                             │
                             ▼
   Agent Layer ──▶ UnifiedRuntime ──▶ CompositionRoot
                      │                    │
                      │ trace_id            │ trace_id (propagated)
                      ▼                    ▼
                  D8 Service Mesh ──▶ EventBus
                      │                    │
                      │ trace_id            │ trace_id in event payload
                      ▼                    ▼
                  StateStore ──▶ Checkpoint ──▶ Trace Log
                  (trace_id stored          (trace_id as primary key)
                   in every record)
```

**LAW 12 enforcement**: Every log, event, checkpoint, and error response carries `trace_id`.

**Propagation Rules**:
1. `trace_id` generated once in `UnifiedRuntime.submit()`
2. Propagated to all D8 service calls as first parameter
3. Stored in every `IExecutionStateStore` record
4. Included in every `IEventBus.publish()` event payload
5. Returned in `ResponseEnvelope` for client correlation
6. Carried in `RuntimeError.trace_id` for error debugging

---

## 3. Event Hooks

### 3.1 Event Topic Hierarchy

```
runtime/
  ├── execution/
  │   ├── submitted      # dag submitted, ticket issued
  │   ├── queued         # dag validated, awaiting resources
  │   ├── leased         # execution lease acquired
  │   ├── planned        # dag scheduled into levels
  │   ├── started        # first node dispatched
  │   ├── progress       # node completed (streamed)
  │   ├── completed      # all nodes done
  │   ├── failed         # terminal failure
  │   ├── cancelled      # user-cancelled
  │   ├── rolled_back    # partial state undone
  │   └── resumed        # resumed from checkpoint
  ├── worker/
  │   ├── registered     # new worker joined
  │   ├── unregistered   # worker removed
  │   ├── online         # worker heartbeat received
  │   ├── offline        # worker heartbeat timeout
  │   ├── scaled         # pool size changed
  │   └── drained        # worker gracefully drained
  ├── lease/
  │   ├── acquired       # lease granted
  │   ├── renewed        # lease refreshed
  │   ├── expired        # lease TTL passed
  │   └── released       # lease returned
  ├── checkpoint/
  │   ├── saved          # checkpoint persisted
  │   └── restored       # checkpoint loaded
  ├── replay/
  │   ├── started        # deterministic replay begun
  │   ├── completed      # replay matched original
  │   └── mismatch       # replay diverged
  └── state/
      └── transition     # any state machine transition
```

### 3.2 Hook Points in UnifiedRuntime

```
submit()       → emit("runtime.execution.submitted")   after ticket creation
                 emit("runtime.execution.queued")       after validation
                 emit("runtime.execution.leased")       after lease acquire
                 emit("runtime.execution.planned")      after scheduling
                 emit("runtime.execution.started")      after first dispatch

resume()       → emit("runtime.execution.resumed")     after state restore
                 emit("runtime.execution.leased")       after lease re-acquire
                 emit("runtime.execution.planned")      after re-schedule

cancel()       → emit("runtime.execution.cancelled")   on cancel request
                 emit("runtime.execution.rolled_back")  on rollback complete
                 emit("runtime.lease.released")         on lease release

observe()      → emit("runtime.state.transition")      on each state change (stream)
                 (subscriber receives live events)

replay()       → emit("runtime.replay.started")        on replay begin
                 emit("runtime.replay.completed")       on match
                 emit("runtime.replay.mismatch")        on divergence

scale()        → emit("runtime.worker.scaled")          on pool change

register_worker() → emit("runtime.worker.registered")   on registration
                      emit("runtime.worker.online")     on heartbeat start
```

### 3.3 Subscription Integration

```python
# EventBus subscription pattern for observability
event_bus.subscribe("runtime.execution.*", callback=telemetry.record)
event_bus.subscribe("runtime.worker.*", callback=worker_monitor.update)
event_bus.subscribe("runtime.lease.*", callback=lease_audit.log)
event_bus.subscribe("runtime.replay.*", callback=replay_verifier.compare)
event_bus.subscribe("runtime.state.*", callback=state_machine.audit)

# Live state streaming (observe with stream=True)
def observe_stream(ticket_id: str) -> Iterator[LiveStateStream]:
    with event_bus.subscribe(f"runtime.execution.{ticket_id}.*") as stream:
        for event in stream:
            yield LiveStateStream(
                ticket_id=ticket_id,
                current_state=event.payload["state"],
                completed_nodes=event.payload.get("completed", 0),
                active_nodes=event.payload.get("active", 0),
                events=[event.to_dict()],
            )
```

---

## 4. Acceptance Criteria

### 4.1 Latency Budgets

| API Operation | Target | Warning | Critical | Notes |
|--------------|--------|---------|----------|-------|
| `submit()` | < 100ms | > 200ms | > 500ms | DAG validation + scheduling |
| `resume()` | < 200ms | > 400ms | > 1s | Checkpoint load + re-dispatch |
| `cancel()` | < 50ms | > 100ms | > 300ms | Flag set + lease release |
| `observe()` (snapshot) | < 20ms | > 50ms | > 100ms | State read + snapshot build |
| `observe()` (stream) | < 10ms per event | > 30ms | > 100ms | Event bus subscription |
| `replay()` | < submit() × 1.5 | — | — | Same path + hash compare |
| `scale()` | < 2s | > 5s | > 10s | Worker pool mutation |
| `register_worker()` | < 500ms | > 1s | > 3s | Manifest validation + lease |

### 4.2 Backpressure Handling

| Scenario | Strategy | Implementation |
|----------|----------|---------------|
| Submit queue full | REJECT with Retry-After header | `QueueFullError` → HTTP 429 |
| Event bus buffer full | DROP_OLDEST (non-critical events) | Circular buffer, oldest overwritten |
| Scale in progress | BLOCK until complete | Mutex on worker pool |
| Observe stream overwhelmed | SAMPLE (reduce event rate) | Configurable throttling per subscription |
| Replay queue congested | SERIALIZE per execution_id | Per-key queue, max 10 pending |

### 4.3 Idempotency Guarantees

| Operation | Idempotency Key | Window | Behavior |
|-----------|----------------|--------|----------|
| `submit(dag)` | dag.hash() | 5 min | Same hash → return existing ticket |
| `cancel(ticket_id)` | ticket_id | Until terminal | Second cancel → no-op |
| `resume(ticket_id)` | ticket_id | 30s | Same resume → same state |
| `replay(execution_id)` | execution_id | 10 min | Same trace → same replay |
| `register_worker(id)` | worker_id | Until unregistered | Same worker → update existing |
| `scale(count, policy)` | (count, policy) hash | 1 min | Same params → no-op |

### 4.4 LAW 13 (CompositionRoot) Enforcement

```
✅ CompositionRoot.create_unified_runtime() — the ONLY path to instantiate UnifiedRuntime
✅ UnifiedRuntime receives all dependencies via constructor injection
✅ No module may call UnifiedRuntime() constructor directly
✅ No module may import D8 service implementations directly
✅ All cross-layer communication goes through Protocol interfaces

Verify via pre-commit AST scan:
  def test_no_direct_unified_runtime_construction():
      """LAW 13: CompositionRoot is the only valid entry point."""
      source = Path("core/runtime").read_text()
      assert "UnifiedRuntime(" not in source  # constructor call bypass
      assert "ExecutionScheduler(" not in source  # direct D8 instantiation
```

### 4.5 RULE 4 (Everything Killable) Enforcement

```
✅ Every submit() returns a ticket that can be cancelled
✅ Every cancel() triggers SIGKILL on active subprocesses
✅ Every execution has a timeout (from SubmissionOptions.ttl)
✅ Every lease has a TTL — expiry triggers reassignment
✅ Every observe() stream can detect orphaned executions
✅ Every replay() can be cancelled mid-execution
```

### 4.6 State Machine Integrity

```
✅ Every state transition has a guard (precondition check)
✅ Every guard returns (allowed: bool, reason: str)
✅ Every transition emits a "runtime.state.transition" event
✅ Every terminal state is truly terminal (no outgoing edges)
✅ Every non-terminal state has a cancel path to CANCELLED
✅ Every failed state has a rollback path to ROLLED_BACK
✅ Every orphaned state has a recovery path through RECOVERED
```
