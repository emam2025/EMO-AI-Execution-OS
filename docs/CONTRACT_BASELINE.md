# D8 Service Mesh — Contract Baseline

**Source of Truth:** `core/runtime/services/*`
**Status:** FROZEN — do not modify implementations without updating this baseline
**Date:** 2026-06-01
**Branch:** fix/async-taskmanager

---

## 1. IExecutionScheduler

**File:** `core/runtime/services/scheduler.py`
**Class:** `ExecutionScheduler`
**LAW 23:** execution ordering only

### Signatures

```python
def schedule(
    self,
    dag: Any,
    session_id: Optional[str] = None,
    strategy: str = "balanced",
) -> List[List[Any]]:
    """
    Partition DAG nodes into execution levels.
    Returns levels of parallel-executable nodes.
    Raises:
        SchedulingError: If DAG contains cycles or invalid dependencies.
    """

def run_with_timeout(
    self,
    node: Any,
    runner: Callable[..., Any],
    timeout: float = 30.0,
) -> Any:
    """
    Execute a single node with timeout enforcement.
    Raises:
        TimeoutError: If execution exceeds timeout.
    """

def collect_futures(
    self,
    futures: Dict[Any, Any],
    session_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Collect and process completed futures from a level.
    Raises:
        CollectError: If future collection encounters unhandled errors.
    """
```

### Exceptions
- `SchedulingError` — DAG scheduling fails (cycles, invalid deps)
- `CollectError` — future collection encounters unhandled errors

---

## 2. IExecutionDispatcher

**File:** `core/runtime/services/tool_dispatcher.py`
**Class:** `ExecutionToolDispatcher`
**LAW 24:** execution routing only

### Signatures

```python
def register_tool(
    self,
    tool_name: str,
    executor: Any,
    contract_schema: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Register a tool for dispatch.
    LAW 24: Dispatcher owns the tool registry.
    """

def dispatch_tool_call(
    self,
    tool_name: str,
    inputs: Dict[str, Any],
    context: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Route a tool call to the appropriate execution path.
    Returns: {"status": "completed", "tool": tool_name, "result": result}
    Raises:
        UnknownToolError: If tool_name is not registered.
        DispatchError: If routing fails.
    """

def validate_contract(
    self,
    tool_name: str,
    inputs: Dict[str, Any],
) -> bool:
    """
    Validate that a tool call conforms to its contract.
    Returns: True if valid, False otherwise.
    Raises:
        ContractViolationError: If contract is violated.
    """

def route_service(
    self,
    service_domain: str,
    method: str,
    payload: Dict[str, Any],
) -> Any:
    """
    Route an inter-service call to the correct service.
    NOTE: Currently raises RoutingError — inter-service calls use EventBus.
    Raises:
        RoutingError: If service domain or method is unknown.
    """
```

### Exceptions
- `DispatchError` — tool dispatch routing fails
- `UnknownToolError` — tool_name is not registered
- `ContractViolationError` — tool call violates its contract
- `RoutingError` — service domain or method is unknown

---

## 3. IExecutionRetryHandler

**File:** `core/runtime/services/retry_handler.py`
**Class:** `ExecutionRetryHandler`
**LAW 25:** retry semantics only

### Signatures

```python
def decide_retry(
    self,
    node_id: str,
    error: Exception,
    attempt: int,
    max_attempts: int = 3,
) -> bool:
    """
    Decide whether a failed execution should be retried.
    Returns: True if retry should proceed, False if failure is terminal.
    Raises:
        RetryDecisionError: If retry decision cannot be computed.
    """

def apply_backoff(
    self,
    attempt: int,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
) -> float:
    """
    Compute the backoff delay before the next retry.
    Returns: Delay in seconds (clamped to [0.1, max_delay]).
    """

def record_failure(
    self,
    node_id: str,
    error: Exception,
    attempt: int,
    context: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Record a failure for telemetry and pattern detection.
    Raises:
        RecordingError: If failure cannot be persisted.
    """
```

### Exceptions
- `RetryDecisionError` — retry decision cannot be computed
- `RecordingError` — failure cannot be persisted

---

## 4. IExecutionStateStore

**File:** `core/runtime/services/state_store.py`
**Class:** `ExecutionStateStore`
**LAW 26:** persistence + traces only

### Signatures

```python
def save_state(
    self,
    node_id: str,
    state: Any,
    session_id: str = "",
) -> None:
    """
    Persist a node's state.
    Raises:
        PersistenceError: If state cannot be written.
    """

def load_state(
    self,
    node_id: str,
    session_id: str = "",
) -> Optional[Any]:
    """
    Load a node's persisted state.
    Returns: The persisted state, or None if not found.
    Raises:
        LoadError: If state cannot be read.
    """

def store_checkpoint(
    self,
    session_id: str,
    dag: Any,
    last_node_id: str,
    result: Dict[str, Any],
) -> None:
    """
    Store an execution checkpoint for resume.
    Raises:
        CheckpointError: If checkpoint cannot be written.
    """

def read_trace(
    self,
    session_id: str,
) -> Optional[Dict[str, Any]]:
    """
    Read the full execution trace for a session.
    Returns: Execution trace dict, or None if no trace exists.
    Raises:
        TraceError: If trace cannot be read.
    """
```

### Exceptions
- `PersistenceError` — state cannot be persisted
- `LoadError` — state cannot be read
- `CheckpointError` — checkpoint cannot be written
- `TraceError` — trace cannot be read

---

## 5. IExecutionLeaseManager

**File:** `core/runtime/services/lease_manager.py`
**Class:** `ExecutionLeaseManager`
**LAW 23 (complement):** distributed ownership only

### Signatures

```python
def acquire_lease(
    self,
    resource_id: str,
    owner: str,
    ttl: float = 30.0,
) -> Optional[str]:
    """
    Acquire an execution lease for a distributed resource.
    Returns: Lease ID if acquired, None if lease is held by another owner.
    Raises:
        LeaseError: If lease cannot be acquired due to system error.
    """

def renew_lease(
    self,
    lease_id: str,
    ttl: float = 30.0,
) -> bool:
    """
    Renew an existing lease to prevent expiry.
    Returns: True if renewed, False if lease has expired or is invalid.
    Raises:
        LeaseError: If lease renewal encounters system error.
    """

def release_lease(
    self,
    lease_id: str,
) -> bool:
    """
    Release a lease, making the resource available.
    Returns: True if released, False if lease was not found.
    Raises:
        LeaseError: If lease release encounters system error.
    """

def monitor_heartbeat(
    self,
    lease_id: str,
    timeout: float = 5.0,
) -> bool:
    """
    Monitor heartbeat for a leased resource.
    Returns: True if heartbeat received within timeout, False otherwise.
    Raises:
        HeartbeatError: If heartbeat monitoring fails.
    """
```

### Exceptions
- `LeaseError` — lease operation encounters a system error
- `HeartbeatError` — heartbeat monitoring fails

---

## 6. FailureMatrix (Failure Propagation)

**File:** `core/runtime/services/failure_propagation.py`
**Class:** `FailureMatrix`
**LAW 20-22:** failure propagation

### Signatures

```python
def apply(self, source_domain: str) -> List[str]:
    """
    Get the action sequence for a source domain failure.
    Returns: List of FailureMode action codes to execute.
    Raises: KeyError — If source_domain has no defined propagation policy.
    """

def record_circuit_break(self, source_domain: str) -> None:
    """Record a circuit break event for a source domain."""

def reset_circuit_breaker(self, source_domain: str) -> None:
    """Reset the circuit breaker for a source domain."""

def get_all_scenarios(self) -> List[Dict[str, Any]]:
    """Return all F01-F08 scenarios for test verification."""
```

### Scenarios (F01-F08)
| ID | Source Domain | Action Sequence |
|----|---------------|-----------------|
| F01 | Dispatcher | RETRY, CLASSIFY, RELEASE, NOTIFY |
| F02 | LeaseManager | CANCEL, ROLLBACK, REASSIGN, RECORD |
| F03 | StateStore | DEGRADE, BUFFER, CONTINUE, DEFER |
| F04 | Scheduler | FAIL_FAST, RECORD, NOTIFY |
| F05 | RetryHandler | FAIL_FAST, RELEASE, RECORD, NOTIFY |
| F06 | Engine | CANCEL, RELEASE, RECORD, NOTIFY |
| F07 | LeaseManager_acquire | DEFER, NOTIFY |
| F08 | Core | CLASSIFY, RETRY, RELEASE, RECORD |

---

## 7. Exception Map

| Exception | Source Service |
|-----------|---------------|
| `SchedulingError` | ExecutionScheduler |
| `CollectError` | ExecutionScheduler |
| `DispatchError` | ExecutionToolDispatcher |
| `UnknownToolError` | ExecutionToolDispatcher |
| `ContractViolationError` | ExecutionToolDispatcher |
| `RoutingError` | ExecutionToolDispatcher |
| `RetryDecisionError` | ExecutionRetryHandler |
| `RecordingError` | ExecutionRetryHandler |
| `PersistenceError` | ExecutionStateStore |
| `LoadError` | ExecutionStateStore |
| `CheckpointError` | ExecutionStateStore |
| `TraceError` | ExecutionStateStore |
| `LeaseError` | ExecutionLeaseManager |
| `HeartbeatError` | ExecutionLeaseManager |

---

## 8. Canonical Method Cross-Reference

| Old Protocol Method (deprecated) | Actual Contract Method |
|----------------------------------|----------------------|
| `IExecutionScheduler.order_levels()` | `ExecutionScheduler.schedule()` |
| `IExecutionScheduler.select_ready_nodes()` | `ExecutionScheduler.schedule()` (combined) |
| `IExecutionScheduler.allocate_worker()` | `ExecutionScheduler.schedule()` (combined) |
| `IExecutionScheduler.estimate_execution_order()` | `ExecutionScheduler.schedule()` (strategy param) |
| `IExecutionDispatcher.resolve_tool()` | `ExecutionToolDispatcher.dispatch_tool_call()` |
| `IExecutionDispatcher.can_dispatch()` | `ExecutionToolDispatcher.dispatch_tool_call()` (combined) |
| `IExecutionDispatcher.dispatch_local()/dispatch_remote()` | `ExecutionToolDispatcher.dispatch_tool_call()` |
| `IExecutionDispatcher.validate_output()` | (not implemented) |
| `IExecutionRetryHandler.classify_failure()` | `ExecutionRetryHandler.decide_retry()` (combined) |
| `IExecutionRetryHandler.should_retry()` | `ExecutionRetryHandler.decide_retry()` |
| `IExecutionRetryHandler.compute_backoff()` | `ExecutionRetryHandler.apply_backoff()` |
| `IExecutionRetryHandler.handle_exhaustion()` | `ExecutionRetryHandler.decide_retry()` (max_attempts) |
| `IExecutionRetryHandler.record_attempt()` | `ExecutionRetryHandler.record_failure()` |
| `IExecutionStateStore.get_state()` | `ExecutionStateStore.load_state()` |
| `IExecutionStateStore.set_state()` | `ExecutionStateStore.save_state()` |
| `IExecutionStateStore.store_trace()` | `ExecutionStateStore.save_state()` (with session_id) |
| `IExecutionStateStore.save_checkpoint()` | `ExecutionStateStore.store_checkpoint()` |
| `IExecutionStateStore.restore_checkpoint()` | (not implemented) |
| `IExecutionLeaseManager.acquire()` | `ExecutionLeaseManager.acquire_lease()` |
| `IExecutionLeaseManager.release()` | `ExecutionLeaseManager.release_lease()` |
| `IExecutionLeaseManager.heartbeat()` | `ExecutionLeaseManager.monitor_heartbeat()` |
| `IExecutionLeaseManager.is_expired()` | `ExecutionLeaseManager.renew_lease()` (combined) |
| `IExecutionLeaseManager.owner()` | (not implemented as separate method) |
| `IExecutionLeaseManager.release_all()` | (not implemented) |
