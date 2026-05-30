# Phase D8 — Isolation Test Blueprint

> Design for 21 isolation tests covering LAW 23-27 enforcement,
> failure propagation completeness, and interface-only boundaries.
>
> Ref: DEVELOPER.md §15.15a D8.3 ("tests/test_service_isolation.py — 21 tests")

---

## 1. Test Group Architecture

### 1.1 Group Classification

| # | Test Group | Tests | What It Prevents | LAW Ref |
|---|------------|-------|-------------------|---------|
| G1 | `TestNoSharedMutableState` | 5 | Direct mutation of another service's domain | LAW 27 |
| G2 | `TestNoHiddenCrossServiceAccess` | 4 | Chained calls through service internals | D8.3 Rule 10 |
| G3 | `TestServiceInterfaceCompliance` | 4 | Interface method ownership boundaries | D8.1 |
| G4 | `TestFailurePropagationCompliance` | 4 | Propagation matrix completeness | LAW 20-22 |
| G5 | `TestCanonServiceOwnership` | 4 | LAW 23-27 runtime enforcement | LAW 23-27 |

### 1.2 Mocking Strategy

Each test group mocks only the services outside its domain:

| Test Group | Service Under Test | Mocks | Real |
|------------|-------------------|-------|------|
| G1 | All 5 services | `unittest.mock.patch` on private state accesses | Protocol definitions |
| G2 | All 5 services | All services mocked except call chain | Protocol definitions |
| G3 | Each service individually | All other 4 services | The service under test |
| G4 | Propagation engine | All 5 services + EventBus | Failure matrix JSON |
| G5 | Canon enforcement | All 5 services | Canon rules engine |

#### Mock Template

```python
from unittest.mock import create_autospec, MagicMock, patch

# Create protocol-compliant mocks
mock_scheduler = create_autospec(IExecutionScheduler)
mock_dispatcher = create_autospec(IExecutionDispatcher)
mock_retry = create_autospec(IExecutionRetryHandler)
mock_store = create_autospec(IExecutionStateStore)
mock_lease = create_autospec(IExecutionLeaseManager)

# Configure return values
mock_scheduler.schedule.return_value = [["node_a"], ["node_b"]]
mock_dispatcher.dispatch_tool_call.return_value = {"status": "completed"}
mock_retry.decide_retry.return_value = False  # terminal failure
```

---

## 2. Test Case Specifications

### 2.1 G1 — TestNoSharedMutableState (5 tests)

| ID | Test | What It Prevents | Method |
|----|------|-----------------|--------|
| G1-T1 | `test_scheduler_does_not_mutate_dispatcher_state` | Scheduler modifies `Dispatcher._tool_registry` | `patch.object(dispatcher, '_tool_registry')` → verify not called |
| G1-T2 | `test_dispatcher_does_not_mutate_scheduler_state` | Dispatcher modifies `Scheduler._level_queue` | `patch.object(scheduler, '_level_queue')` → verify not called |
| G1-T3 | `test_retry_handler_does_not_mutate_state_store` | RetryHandler modifies `StateStore._cache` | `patch.object(store, '_cache')` → verify not called |
| G1-T4 | `test_lease_manager_does_not_mutate_scheduler_state` | LeaseManager modifies `Scheduler._running_futures` | `patch.object(scheduler, '_running_futures')` → verify not called |
| G1-T5 | `test_state_store_does_not_mutate_retry_handler_state` | StateStore modifies `RetryHandler._failure_counts` | `patch.object(retry, '_failure_counts')` → verify not called |

**Pass Criteria**: All 5 tests: zero mutations detected (0/5 → PASS)

**Failure Injection**: 
```python
# Attempt to mutate another service's state
scheduler._tool_registry["new_tool"] = spec  # Should raise/capture
dispatcher._level_queue.append(node)          # Should raise/capture
```

### 2.2 G2 — TestNoHiddenCrossServiceAccess (4 tests)

| ID | Test | What It Prevents | Method |
|----|------|-----------------|--------|
| G2-T1 | `test_no_direct_state_store_access_from_scheduler` | Scheduler calls `StateStore._cache` directly | AST scan: no `state_store` import in `scheduler.py` |
| G2-T2 | `test_no_direct_lease_manager_access_from_dispatcher` | Dispatcher calls `LeaseManager._active_leases` | AST scan: no `lease_manager` import in `dispatcher.py` |
| G2-T3 | `test_all_inter_service_calls_go_through_interfaces` | No bypass of protocol interfaces | Import graph analysis: only protocol imports allowed |
| G2-T4 | `test_no_implementation_imports_across_services` | No `from core.runtime.scheduler import Scheduler` inside Dispatcher | AST scan: only interface imports across domains |

**Pass Criteria**: Zero cross-service implementation imports (4/4 → PASS)

**AST Scan Pattern**:
```python
def test_no_hidden_imports():
    violations = []
    service_dirs = {
        "scheduler": ["dispatcher", "state_store", "retry_handler", "lease_manager"],
        "dispatcher": ["scheduler", "state_store", "retry_handler", "lease_manager"],
        "retry_handler": ["scheduler", "dispatcher", "state_store", "lease_manager"],
        "state_store": ["scheduler", "dispatcher", "retry_handler", "lease_manager"],
        "lease_manager": ["scheduler", "dispatcher", "retry_handler", "state_store"],
    }
    for service, forbidden in service_dirs.items():
        source = Path(f"core/runtime/{service}.py").read_text()
        for target in forbidden:
            if f"from core.runtime.{target}" in source:
                violations.append(f"{service} imports {target} implementation")
    assert len(violations) == 0, f"Hidden imports: {violations}"
```

### 2.3 G3 — TestServiceInterfaceCompliance (4 tests)

| ID | Test | What It Prevents | Method |
|----|------|-----------------|--------|
| G3-T1 | `test_scheduler_has_no_extra_public_methods` | Scheduler exposes methods outside `IExecutionScheduler` | `dir(Scheduler) - IExecutionScheduler` must be empty |
| G3-T2 | `test_dispatcher_has_no_extra_public_methods` | Dispatcher exposes methods outside `IExecutionDispatcher` | `dir(Dispatcher) - IExecutionDispatcher` must be empty |
| G3-T3 | `test_retry_handler_has_no_extra_public_methods` | RetryHandler exposes methods outside `IExecutionRetryHandler` | `dir(RetryHandler) - IExecutionRetryHandler` must be empty |
| G3-T4 | `test_state_store_has_no_extra_public_methods` | StateStore exposes methods outside `IExecutionStateStore` | `dir(StateStore) - IExecutionStateStore` must be empty |

**Pass Criteria**: Zero extra public methods beyond protocol (4/4 → PASS)

**Method**:
```python
def test_service_exposes_only_protocol_methods():
    protocol_methods = set(IExecutionScheduler.__protocol_methods__)
    service_methods = {
        m for m in dir(Scheduler) if not m.startswith("_")
    }
    extra = service_methods - protocol_methods
    assert len(extra) == 0, f"Extra public methods: {extra}"
```

### 2.4 G4 — TestFailurePropagationCompliance (4 tests)

| ID | Test | What It Prevents | Method |
|----|------|-----------------|--------|
| G4-T1 | `test_dispatcher_failure_propagates_correctly` | Dispatcher fail → Scheduler → RetryHandler → LeaseManager → Core | Inject `DispatchError`, verify chain executes |
| G4-T2 | `test_lease_expiry_propagates_correctly` | Lease expiry → Engine → Scheduler → StateStore | Simulate expiry, verify CANCEL+ROLLBACK |
| G4-T3 | `test_state_store_failure_propagates_correctly` | StateStore fail → Core → Scheduler → RetryHandler | Inject `PersistenceError`, verify DEGRADE+BUFFER |
| G4-T4 | `test_matrix_covers_all_source_domains` | Missing propagation paths | All 8 source domains must have entries in matrix |

**Pass Criteria**: All 4 scenarios propagate correctly (4/4 → PASS)

**Failure Injection**:
```python
@pytest.mark.parametrize("scenario", [
    ("Dispatcher", "dispatch_tool_call", DispatchError),
    ("LeaseManager", "monitor_heartbeat", TimeoutError),
    ("StateStore", "save_state", PersistenceError),
    ("Scheduler", "schedule", SchedulingError),
    ("RetryHandler", "decide_retry", RetryDecisionError),
])
def test_failure_propagation(scenario):
    domain, method, error_class = scenario
    with patch(f"core.runtime.{domain.lower()}.{method}") as mock:
        mock.side_effect = error_class("simulated")
        result = propagation_engine.handle(domain, method)
        assert result.action_sequence == EXPECTED_ACTIONS[domain]
```

### 2.5 G5 — TestCanonServiceOwnership (4 tests)

| ID | Test | What It Prevents | Method |
|----|------|-----------------|--------|
| G5-T1 | `test_scheduler_does_not_own_retry` | Scheduler calls `decide_retry` | Verify `decide_retry` not in `IExecutionScheduler` |
| G5-T2 | `test_dispatcher_does_not_own_state` | Dispatcher calls `save_state` | Verify `save_state` not in `IExecutionDispatcher` |
| G5-T3 | `test_retry_handler_does_not_own_scheduling` | RetryHandler calls `schedule` | Verify `schedule` not in `IExecutionRetryHandler` |
| G5-T4 | `test_state_store_does_not_own_dispatch` | StateStore calls `dispatch_tool_call` | Verify `dispatch_tool_call` not in `IExecutionStateStore` |

**Pass Criteria**: Zero ownership violations detected (4/4 → PASS)

**AST Scan**:
```python
def test_canon_service_ownership():
    ownership = {
        "IExecutionScheduler":    {"schedule", "run_with_timeout", "collect_futures"},
        "IExecutionDispatcher":   {"dispatch_tool_call", "validate_contract", "route_service"},
        "IExecutionRetryHandler": {"decide_retry", "apply_backoff", "record_failure"},
        "IExecutionStateStore":   {"save_state", "load_state", "store_checkpoint", "read_trace"},
        "IExecutionLeaseManager": {"acquire_lease", "renew_lease", "release_lease", "monitor_heartbeat"},
    }
    forbidden = {
        "IExecutionScheduler":    {"decide_retry", "dispatch_tool_call", "save_state", "acquire_lease"},
        "IExecutionDispatcher":   {"save_state", "acquire_lease", "decide_retry", "schedule"},
        "IExecutionRetryHandler": {"schedule", "dispatch_tool_call", "save_state", "acquire_lease"},
        "IExecutionStateStore":   {"dispatch_tool_call", "decide_retry", "acquire_lease", "schedule"},
        "IExecutionLeaseManager": {"decide_retry", "dispatch_tool_call", "save_state", "schedule"},
    }
    for protocol, own_set in ownership.items():
        forbid_set = forbidden[protocol]
        overlap = own_set & forbid_set
        assert len(overlap) == 0, f"{protocol} owns forbidden methods: {overlap}"
```

---

## 3. Failure Injection Points

### 3.1 Injection Map

| Injection Point | How | Target Tests |
|----------------|-----|-------------|
| `Scheduler.schedule()` side_effect | `raise SchedulingError(...)` | G4-T4 |
| `Dispatcher.dispatch_tool_call()` side_effect | `raise DispatchError(...)` | G4-T1 |
| `RetryHandler.decide_retry()` side_effect | `raise RetryDecisionError(...)` | G4-T4 |
| `StateStore.save_state()` side_effect | `raise PersistenceError(...)` | G4-T3 |
| `LeaseManager.monitor_heartbeat()` side_effect | `return False` | G4-T2 |
| Private state mutation attempt | `patch.object(service, '_private_dict')` → detect writes | G1-T1 through G1-T5 |
| Direct import parse | AST `import` / `from ... import` scan | G2-T1 through G2-T4 |
| Protocol method mismatch | `dir(impl) - protocol_methods` | G3-T1 through G3-T4 |

### 3.2 E2E Propagation Test Pattern

```python
def test_end_to_end_failure_propagation():
    """Simulate Dispatcher failure and verify full chain."""
    events = []

    with patch.object(EventBus, 'emit', side_effect=lambda e: events.append(e)):
        with patch.object(RetryHandler, 'decide_retry', return_value=False):
            with patch.object(LeaseManager, 'release_lease', return_value=True):
                # Trigger failure
                result = engine.execute(dag_with_dispatcher_failure)

                # Verify propagation chain
                assert result["status"] == "failed"
                assert any(e.event_type == "DISPATCH_FAILED" for e in events)
                assert any(e.event_type == "RETRY_EXHAUSTED" for e in events)
                assert any(e.event_type == "LEASE_RELEASED" for e in events)
```

---

## 4. Acceptance Criteria

### 4.1 Pass/Fail Thresholds

| Group | Tests | Required Pass | Acceptable Failures | Rationale |
|-------|-------|---------------|---------------------|-----------|
| G1 — NoSharedMutableState | 5 | 5 | 0 | Data integrity — zero tolerance |
| G2 — NoHiddenCrossServiceAccess | 4 | 4 | 0 | Architecture enforcement |
| G3 — ServiceInterfaceCompliance | 4 | 4 | 0 | Protocol purity |
| G4 — FailurePropagationCompliance | 4 | 4 | 0 | Matrix completeness |
| G5 — CanonServiceOwnership | 4 | 4 | 0 | LAW 23-27 enforcement |
| **Total** | **21** | **21** | **0** | |

### 4.2 Required Assertions per Group

```
G1: assertEqual(len(mutations), 0)
    assertFalse(hasattr(service, "_other_service_state"))
    assert_called_once_with(mock_patch, ...)  # Never called

G2: assertEqual(len(violations), 0)
    assertNotIn("subprocess", imported_modules)
    assertNotIn("os", imported_modules)

G3: assertEqual(len(extra_methods), 0)
    assertTrue(issubclass(ImplClass, Protocol))
    assertTrue(hasattr(impl, "expected_method"))

G4: assertEqual(result["status"], expected_status)
    assertIn(expected_event, emitted_events)
    assertEqual(propagation_chain, expected_chain)

G5: assertEqual(len(overlap), 0)
    assertNotIn(forbidden_method, protocol_methods)
```

### 4.3 Test Execution

```bash
# Run all D8 service isolation tests
pytest tests/test_service_isolation.py -v

# Run specific group
pytest tests/test_service_isolation.py -v -k "TestNoSharedMutableState"

# Run with coverage
pytest tests/test_service_isolation.py --cov=core/runtime --cov=core/interfaces --cov-report=term-missing

# AST scan for ownership violations
python3 -m pytest tests/test_service_isolation.py -v -k "TestCanonServiceOwnership" --tb=long
```

### 4.4 CI Integration

```yaml
# .github/workflows/d8-service-contracts.yml (design)
d8-service-contracts:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with: { python-version: "3.11" }
    - run: pip install -r requirements.txt
    - run: pytest tests/test_service_isolation.py -v --tb=short
    - name: Zero-Failures Enforced
      if: failure()
      run: echo "D8 service isolation tests MUST pass — DEVELOPER.md §15.15a D8.3" && exit 1
```
