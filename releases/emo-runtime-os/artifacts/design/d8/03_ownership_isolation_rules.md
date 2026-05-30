# Phase D8 — Service Ownership & Isolation Rules

> Design document implementing Canon LAW 23-27 and §15.15a D8.4
> Goal: Zero shared mutable state, strict domain boundaries, interface-only communication

---

## 1. LAW 23-27 Enforcement

### 1.1 Ownership Table

| Law | Service | Owns | Forbidden | Data Sovereignty |
|-----|---------|------|-----------|-----------------|
| LAW 23 | **Scheduler** | execution ordering, concurrency levels, timeout enforcement, future collection | retry decisions, dispatch routing, state persistence, lease management | Level queue, running futures, node→worker mapping |
| LAW 24 | **Dispatcher** | execution routing, contract validation, inter-service routing | state reads/writes, lease acquire/release, retry logic, scheduling | Tool registry, contract schemas, routing table |
| LAW 25 | **RetryHandler** | retry decisions, backoff computation, failure recording | scheduling, dispatch, state access, lease operations | Failure patterns, retry counters, backoff state |
| LAW 26 | **StateStore** | state persistence, checkpoints, trace read/write | dispatch, retry, lease, scheduling | Node states, checkpoints, execution traces, session data |
| LAW 27 | **ALL** | exactly one domain | any shared domain method | No cross-domain data overlap |

### 1.2 Enforcement Rules

```
RULE: A service MUST NOT call methods outside its owned domain.
RULE: A service MUST NOT read or mutate state belonging to another domain.
RULE: A service MUST NOT depend on another service's internal implementation.
RULE: All inter-service communication MUST go through interface protocols.
```

### 1.3 Violation Detection

| Violation Pattern | Detection Method | Action |
|------------------|-----------------|--------|
| `Scheduler.save_state()` | AST scan: `scheduler.py` imports `save_state` | REJECT |
| `Dispatcher.renew_lease()` | AST scan: `dispatcher.py` imports lease methods | REJECT |
| `StateStore.decide_retry()` | AST scan: `state_store.py` imports retry types | REJECT |
| `RetryHandler.schedule()` | AST scan: `retry.py` imports scheduler methods | REJECT |
| `LeaseManager.dispatch()` | AST scan: `lease.py` imports dispatcher methods | REJECT |
| Direct `dict` mutation across services | Runtime boundary guard | BLOCK |

---

## 2. No Shared Mutable State

### 2.1 Design Proof

Each service maintains its own **private state** in a dedicated storage class:

```
Scheduler:
  ├── _level_queue: List[List[Node]]          — private, not exposed
  ├── _running_futures: Dict[str, Future]     — private, not exposed
  └── _node_worker_map: Dict[str, str]        — private, not exposed

Dispatcher:
  ├── _tool_registry: Dict[str, ToolSpec]     — private, not exposed
  ├── _contract_schemas: Dict[str, Schema]    — private, not exposed
  └── _routing_table: Dict[str, str]          — private, not exposed

RetryHandler:
  ├── _failure_counts: Dict[str, int]         — private, not exposed
  ├── _backoff_state: Dict[str, float]        — private, not exposed
  └── _pattern_store: FailureIntelligence     — private, not exposed

StateStore:
  ├── _cache: Dict[str, Any]                  — private, not exposed
  ├── _checkpoints: Dict[str, Checkpoint]     — private, not exposed
  └── _traces: Dict[str, Trace]               — private, not exposed

LeaseManager:
  ├── _active_leases: Dict[str, Lease]        — private, not exposed
  ├── _heartbeat_timers: Dict[str, Timer]     — private, not exposed
  └── _resource_owners: Dict[str, str]        — private, not exposed
```

### 2.2 Communication Rule

All inter-service data exchange occurs **only** through:

1. **Return values** from protocol methods (pass-by-value, no references)
2. **EventBus events** (fire-and-forget, immutable payloads)
3. **Shared models** (read-only dataclasses, no behavior)

```
✅ ALLOWED: scheduler_result = await dispatcher.dispatch_tool_call(...)
❌ FORBIDDEN: dispatcher._tool_registry["tool"] = new_value
❌ FORBIDDEN: state_cache["key"] = value  # if state_cache belongs to StateStore
```

### 2.3 Immutable Event Payloads

```python
@dataclass(frozen=True)
class ServiceEvent:
    """Immutable event for inter-service communication.

    All fields are read-only. No service may mutate another's event.
    """
    source: ServiceDomain
    event_type: str
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0
    trace_id: str = ""
```

---

## 3. Independent Testing

### 3.1 Mock Boundaries

Each service is testable in complete isolation. The mock boundary is defined as:

| Service | Dependencies to Mock | Mock Strategy |
|---------|---------------------|---------------|
| `ExecutionScheduler` | `IExecutionDispatcher`, `IExecutionStateStore`, `IExecutionLeaseManager` | Mock protocols with `unittest.mock.create_autospec()` |
| `ExecutionDispatcher` | `IExecutionRetryHandler`, `IExecutionScheduler` | Mock protocols |
| `ExecutionRetryHandler` | `IExecutionLeaseManager`, `IExecutionStateStore` | Mock protocols |
| `ExecutionStateStore` | (none — leaf service) | Test against in-memory SQLite |
| `ExecutionLeaseManager` | (none — leaf service) | Test with deterministic timers |

### 3.2 Data Isolation Proof

```
Test: ExecutionSchedulerTest
  ├── Uses MockDispatcher, MockStateStore, MockLeaseManager
  ├── Tests scheduling logic without real dispatch/state/lease
  └── Asserts: Scheduler state only (= _level_queue, _running_futures)

Test: ExecutionDispatcherTest
  ├── Uses MockRetryHandler, MockScheduler
  ├── Tests contract validation + routing without real retry/lease
  └── Asserts: Dispatcher state only (= _tool_registry, _contract_schemas)

Test: ExecutionRetryHandlerTest
  ├── Uses MockLeaseManager, MockStateStore
  ├── Tests retry decision + backoff without real dispatch/lease
  └── Asserts: RetryHandler state only (= _failure_counts, _backoff_state)
```

### 3.3 No Cascade Requirement

```
Because each service is independently testable:
  ✅ Scheduler tests pass WITHOUT Dispatcher
  ✅ Dispatcher tests pass WITHOUT RetryHandler
  ✅ RetryHandler tests pass WITHOUT StateStore
  ✅ StateStore tests pass WITHOUT anyone
  ✅ LeaseManager tests pass WITHOUT anyone
```

---

## 4. Interface-Only Boundaries

### 4.1 Allowed Communication Flow

```
┌──────────────────┐     IExecutionScheduler     ┌──────────────────┐
│  ExecutionEngine │ ──────────────────────────▶ │ ExecutionScheduler│
│  (thin coord.)   │                              └────────┬─────────┘
└──────────────────┘                                       │
                    ┌───────────────────────────────────────┤
                    │                                       │
                    ▼                                       ▼
        ┌──────────────────┐                    ┌──────────────────┐
        │ExecutionDispatcher│                    │ ExecutionStateStore│
        │  (LAW 24)        │                    │  (LAW 26)        │
        └────────┬─────────┘                    └──────────────────┘
                 │
                 ▼
        ┌──────────────────┐
        │ExecutionRetryHandler│
        │  (LAW 25)        │
        └────────┬─────────┘
                 │
                 ▼
        ┌──────────────────┐
        │ExecutionLeaseManager│
        │  (LAW 23)        │
        └──────────────────┘

KEY:
  ──▶ interface call (Protocol)
  - - ▶ optional call (event/async)
```

### 4.2 Forbidden Communication Flow

```
❌ Scheduler ──▶ StateStore.save_state()     [LAW 23 forbids state]
❌ Dispatcher ──▶ LeaseManager.renew_lease() [LAW 24 forbids lease]
❌ RetryHandler ──▶ Scheduler.schedule()     [LAW 25 forbids scheduling]
❌ StateStore ──▶ Dispatcher.dispatch()      [LAW 26 forbids dispatch]
❌ LeaseManager ──▶ RetryHandler.record()    [LAW 23 forbids retry]
❌ Any service ──▶ Another service._private  [encapsulation violation]
```

### 4.3 Event Bus Integration

Services may communicate through EventBus for non-blocking notifications:

| Event | Source | Consumers | Payload |
|-------|--------|-----------|---------|
| `NODE_COMPLETED` | Scheduler | StateStore, Dispatcher | node_id, result, duration |
| `NODE_FAILED` | Scheduler | RetryHandler, StateStore | node_id, error, attempt |
| `LEASE_EXPIRED` | LeaseManager | Scheduler, Engine | resource_id, owner |
| `DISPATCH_FAILED` | Dispatcher | RetryHandler, Scheduler | tool_name, error |
| `CHECKPOINT_SAVED` | StateStore | Core, Engine | session_id, node_id |

---

## 5. Consistency & Isolation Summary

| Rule | Design Evidence | Enforcement |
|------|----------------|-------------|
| No shared mutable state | Private dicts per service, pass-by-value returns, frozen events | AST scan + test isolation |
| Independent testing | Mock boundaries defined per service (3.1) | CI gate per service |
| Interface-only boundaries | Allowed/forbidden flow diagrams (4.1-4.2) | Protocol conformance tests |
| LAW 23-27 compliance | Ownership table (1.1), forbidden matrix (1.3) | `TestCanonServiceOwnership` |
| Event-driven communication | Event bus table (4.3) | `TestNoHiddenCrossServiceAccess` |
