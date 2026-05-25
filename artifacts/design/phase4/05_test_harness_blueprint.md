# Phase 4 — Test Harness Blueprint

> Design for 81 isolation tests covering Process Isolation, Capability Enforcement,
> Network Block, Filesystem Control, Resource Quotas, and E2E Flow.
>
> Ref: DEVELOPER.md §15.15b ("tests/test_runtime_isolation.py — 81 tests")

---

## 1. Test Group Architecture

### 1.1 Group Classification

| # | Group | Tests | Focus | §15.15b Ref |
|---|-------|-------|-------|-------------|
| G1 | Process Isolation | 12 | Subprocess spawn, timeout kill, sandbox cleanup, worker isolation | §4.1 |
| G2 | Capability Enforcement | 15 | NO capability → NO execution, capability mismatch, capability inheritance | §4.2 |
| G3 | Network Block | 12 | Block all, allow-list, DNS filtering, outbound intercept | §4.3 |
| G4 | Filesystem Control | 12 | Read-only, write-temp, full access, path whitelist, extension filter | §4.3 |
| G5 | Resource Quotas | 15 | CPU limit, memory limit, wall-time timeout, per-execution/worker/global | §4.4 |
| G6 | E2E Flow | 15 | Complete IsolationRuntime path, failure propagation, cleanup guarantee | §4.5 |

### 1.2 Mocking Strategy

All subprocess/IO calls MUST be mocked for deterministic testing.

| Real Component | Mock Strategy | Isolation Guarantee |
|---------------|--------------|-------------------|
| `subprocess.Popen` | `unittest.mock.patch('subprocess.Popen')` → return `MockProc` | No real OS process spawned |
| `tempfile.NamedTemporaryFile` | `unittest.mock.patch('tempfile.NamedTemporaryFile')` → return `MockFile` | No real filesystem writes |
| `os.unlink` | `unittest.mock.patch('os.unlink')` | No real file cleanup |
| `resource.setrlimit` | `unittest.mock.patch('resource.setrlimit')` | No real OS limit changes |
| `socket.socket` | `unittest.mock.patch('socket.socket')` | No real network access |
| `time.time` | `unittest.mock.patch('time.time', side_effect=[...])` | Deterministic timing |
| `threading.Thread` | Subclass `MockThread` that calls target synchronously | Deterministic threading |

#### `MockProc` Specification

```python
@dataclass
class MockProc:
    stdout: MockIO = field(default_factory=lambda: MockIO(b'{"status":"completed"}'))
    stderr: MockIO = field(default_factory=lambda: MockIO(b''))
    returncode: int = 0
    pid: int = 12345
    _waited: threading.Event = field(default_factory=threading.Event)

    def communicate(self) -> tuple[bytes, bytes]:
        return self.stdout.read(), self.stderr.read()

    def poll(self) -> Optional[int]:
        return self.returncode if self._waited.is_set() else None

    def wait(self, timeout: Optional[float] = None) -> int:
        self._waited.set()
        return self.returncode

    def kill(self) -> None:
        self.returncode = -9
        self._waited.set()
```

---

## 2. Test Case Specifications

### 2.1 G1 — Process Isolation (12 tests)

| ID | Test | Expected | Failure Injection |
|----|------|----------|-------------------|
| G1-T1 | SandboxExecutor spawns subprocess with Python executable | `subprocess.Popen` called with `sys.executable` | — |
| G1-T2 | SandboxExecutor creates temp worker script | `NamedTemporaryFile` called with `.py` suffix | — |
| G1-T3 | SandboxExecutor returns stdout JSON | `status == "completed"`, `result == parsed` | Mock stdout returns invalid JSON |
| G1-T4 | SandboxExecutor kills on timeout | `proc.kill()` called; `ExecutionTimeoutError` raised | `proc.wait(timeout)` raises |
| G1-T5 | SandboxExecutor cleanup after success | Worker file deleted via `os.unlink` | — |
| G1-T6 | SandboxExecutor cleanup after failure | Worker file deleted even on exception | `proc.communicate()` raises |
| G1-T7 | kill() sends SIGKILL to subprocess | `proc.kill()` called; process removed from registry | — |
| G1-T8 | kill() returns False for unknown exec_id | `False` returned | — |
| G1-T9 | SandboxManager.create_sandbox() returns unique ID | UUID hex string, 16 chars | — |
| G1-T10 | SandboxManager.destroy_sandbox() removes from active | `active_count()` decrements | — |
| G1-T11 | SandboxManager shutdown destroys all | `active_count() == 0` after shutdown | — |
| G1-T12 | SandboxManager blocks create after shutdown | `SandboxViolationError` raised | — |

### 2.2 G2 — Capability Enforcement (15 tests)

| ID | Test | Expected | Failure Injection |
|----|------|----------|-------------------|
| G2-T1 | No capability → execution blocked | `CapabilityViolation` raised | CapabilityRegistry returns None |
| G2-T2 | Full capability → execution allowed | `CapabilityStatus.allowed == True` | — |
| G2-T3 | Network=READ → filesystem READ allowed | `Capability.network` limited, FS read ok | — |
| G2-T4 | Network=NONE → CapabilityViolation on net op | Block at capability check | Input contains "http" |
| G2-T5 | Filesystem=NONE → CapabilityViolation on FS op | Block at capability check | Input contains file path |
| G2-T6 | Capability timeout > context timeout → context wins | `SandboxContext.timeout == min(cap.timeout, ctx.timeout)` | — |
| G2-T7 | CapabilityRegistry maps tool → capability correctly | Registry lookup returns matching Capability | — |
| G2-T8 | Unknown tool → no capability → blocked | `CapabilityViolation` raised | Registry missing tool |
| G2-T9 | Allowed_domains capability → network access for domains | `allowed_domains` propagates to context | — |
| G2-T10 | Allowed_paths capability → filesystem access for paths | `allowed_paths` propagates to context | — |
| G2-T11 | Capability with max_cpu=0 → unlimited CPU | `SandboxContext.cpu_limit == 0` | — |
| G2-T12 | Capability with max_memory=0 → unlimited memory | `SandboxContext.memory_limit == 0` | — |
| G2-T13 | CapabilityGuard.validate() rejects oversized input | `CapabilityViolation` raised | Input > 10 MB |
| G2-T14 | Capability subprocess=False → subprocess blocked | Block at capability check | Tool tries subprocess |
| G2-T15 | Capability overrides from SandboxContext apply | Context.cpu_limit < Capability.max_cpu → Context wins | — |

### 2.3 G3 — Network Block (12 tests)

| ID | Test | Expected | Failure Injection |
|----|------|----------|-------------------|
| G3-T1 | NetworkMode=NONE → all outbound blocked | `IOViolation` or `NetworkBlocked` raised | — |
| G3-T2 | NetworkMode=FULL → all outbound allowed | Passes | — |
| G3-T3 | NetworkMode=ALLOW_LIST → only listed domains allowed | Blocked for unknown.com | — |
| G3-T4 | NetworkIsolation.check_request() blocks IP-based URLs | `NetworkBlocked` raised | IP not in allow-list |
| G3-T5 | NetworkIsolation.check_request() allows subdomains | `allowed_domain="example.com"` allows `sub.example.com` | — |
| G3-T6 | IOPolicyEngine.check("network.get") enforces domain rules | Blocked if domain not allowed | — |
| G3-T7 | IOPolicyEngine.check("network.get") enforces max_size | Blocked if payload > max_size | — |
| G3-T8 | IsolationRuntime.check_network() delegates correctly | Returns same as NetworkIsolation | — |
| G3-T9 | Capability network=NONE → IsolationRuntime blocks network | All network operations blocked | — |
| G3-T10 | Capability network=FULL → IsolationRuntime allows all | All network operations allowed | — |
| G3-T11 | Tool's network policy independent per tool | Tool A blocked, Tool B allowed | — |
| G3-T12 | Network block after capability passes → still blocked | IO check independent of capability | — |

### 2.4 G4 — Filesystem Control (12 tests)

| ID | Test | Expected | Failure Injection |
|----|------|----------|-------------------|
| G4-T1 | FilesystemMode=NONE → all FS ops blocked | `FileAccessViolation` raised | — |
| G4-T2 | FilesystemMode=READ_ONLY → reads allowed, writes blocked | Read passes, `FileAccessViolation` on write | — |
| G4-T3 | FilesystemMode=FULL → all FS ops allowed | Read + write pass | — |
| G4-T4 | Path whitelist → only whitelisted paths accessible | `/tmp` read ok, `/etc` blocked | — |
| G4-T5 | Path whitelist with write → write allowed on whitelisted path | Write to `/tmp/test` ok | — |
| G4-T6 | Extension filter → `.py` allowed, `.key` blocked | — | — |
| G4-T7 | IOPolicyEngine.check("file.read") enforces path rules | Blocked if path not allowed | — |
| G4-T8 | IOPolicyEngine.check("file.write") enforces max_size | Blocked if file > max_size | — |
| G4-T9 | IsolationRuntime.check_filesystem_* delegates correctly | Returns same as FilesystemIsolation | — |
| G4-T10 | Capability filesystem=NONE → IsolationRuntime blocks FS | All FS ops blocked | — |
| G4-T11 | SandboxContext.is_path_allowed() with symlinks | Resolves symlink before check | — |
| G4-T12 | Multiple tools with different FS policies | Tool A read-only, Tool B full — both enforced | — |

### 2.5 G5 — Resource Quotas (15 tests)

| ID | Test | Expected | Failure Injection |
|----|------|----------|-------------------|
| G5-T1 | check_before_scheduling() passes within quota | Returns None | — |
| G5-T2 | check_before_scheduling() blocks when over global quota | `QuotaExceeded` raised | Pre-fill global quota |
| G5-T3 | enforce() returns True when within limits | `True` | — |
| G5-T4 | enforce() returns False when over CPU limit | `False` | CPU > max_cpu |
| G5-T5 | enforce() returns False when over memory limit | `False` | Memory > max_memory |
| G5-T6 | finish() records telemetry correctly | `ResourceTracker.complete_execution()` returns accurate usage | — |
| G5-T7 | Per-execution quota independent of others | Exe A blocked, Exe B passes | — |
| G5-T8 | Worker quota scoped to worker processes | Multiple exes share worker quota | — |
| G5-T9 | Global quota across all workers | All executions share global limit | — |
| G5-T10 | Quota release after finish() | Next execution can proceed | — |
| G5-T11 | Quota not released on failed execution | ResourceUsage still tracked | — |
| G5-T12 | ResourceTracker tracks CPU, memory, wall time, IO separately | Each field independently updated | — |
| G5-T13 | RLIMIT_AS enforced in subprocess preexec_fn | `resource.setrlimit` called with memory_limit | — |
| G5-T14 | RLIMIT_CPU enforced in subprocess preexec_fn | `resource.setrlimit` called with cpu_limit | — |
| G5-T15 | Multiple concurrent executions = summed resource usage | Tracker.usage reflects total | — |

### 2.6 G6 — E2E Flow (15 tests)

| ID | Test | Expected | Failure Injection |
|----|------|----------|-------------------|
| G6-T1 | Full successful path through IsolationRuntime | `status == "completed"`, sandbox destroyed | — |
| G6-T2 | CapabilityViolation blocked before resource check | IsolationRuntime returns blocked, sandbox not created | CapabilityGuard raises |
| G6-T3 | QuotaExceeded blocked before sandbox creation | IsolationRuntime returns blocked, sandbox not created | ResourceEnforcer raises |
| G6-T4 | Sandbox error blocked before execution | IsolationRuntime returns sandbox_error | SandboxManager raises |
| G6-T5 | Execution timeout handled with sandbox cleanup | Sandbox destroyed after timeout | Mock proc.wait(timeout) raises |
| G6-T6 | SIGKILL from IsolationRuntime.kill() | `proc.kill()` called, `status == "cancelled"` | — |
| G6-T7 | IO violation during execution (mid-flight) | IOPolicyEngine.check() blocks mid-execution | — |
| G6-T8 | Secret injection before execution | `secret_injector.inject()` called | — |
| G6-T9 | Multiple concurrent executions isolated | Each has separate sandbox, separate context | — |
| G6-T10 | IsolationRuntime.shutdown() destroys all sandboxes | `active_count() == 0` | — |
| G6-T11 | EventBus events emitted for each state transition | All 5 step events verified | — |
| G6-T12 | Error recovery — SandboxError caught, sandbox destroyed | `finally` block executes cleanup | — |
| G6-T13 | execute_direct() fallback for non-serializable runners | Thread execution, not subprocess | — |
| G6-T14 | Canon enforcement before Step 1 | `validate_canon()` called first | Mock canon_validator returns blocked |
| G6-T15 | ExecutionResult contains all telemetry fields | status, elapsed, sandbox_id, telemetry all present | — |

---

## 3. Failure Injection Points

### 3.1 Injection Map

| Injection Point | How | Target Tests |
|----------------|-----|-------------|
| `CapabilityGuard.validate()` side_effect | `raise CapabilityViolation(...)` | G2-T1, G2-T4, G2-T5, G2-T13 |
| `QuotaManager.check()` side_effect | `raise QuotaExceeded(...)` | G5-T2, G5-T4, G5-T5 |
| `SandboxManager.create_sandbox()` side_effect | `raise SandboxViolationError(...)` | G6-T4 |
| `subprocess.Popen` side_effect | `raise OSError(...)` | G6-T4 |
| `proc.wait(timeout)` side_effect | `time.sleep(timeout+1)` or raise | G1-T4, G6-T5 |
| `proc.communicate()` side_effect | `raise RuntimeError(...)` | G1-T6 |
| `stdout.read()` return_value | `b"invalid json"` | G1-T3 |
| `time.time()` side_effect | Simulate time passing | G5-T4, G5-T5 |
| `os.unlink()` side_effect | `raise OSError(...)` | G1-T6 |
| `resource.setrlimit` side_effect | `raise ValueError(...)` | G5-T13, G5-T14 |
| `secret_injector.inject()` side_effect | `raise SecretInjectionError(...)` | G6-T8 |

### 3.2 Mock Pattern Template

```python
from unittest.mock import patch, MagicMock, PropertyMock

@patch('core.runtime.sandbox.sandbox_executor.subprocess.Popen')
def test_timeout_kill(self, mock_popen):
    mock_proc = MagicMock()
    mock_proc.poll.return_value = None  # still running
    mock_proc.wait.side_effect = subprocess.TimeoutExpired(
        cmd="python", timeout=1.0
    )
    mock_popen.return_value = mock_proc

    executor = SandboxExecutor()
    context = SandboxContext(timeout=0.1)

    with self.assertRaises(ExecutionTimeoutError):
        executor.execute("test_tool", {}, context)

    mock_proc.kill.assert_called_once()
```

---

## 4. Acceptance Criteria

### 4.1 Pass/Fail Thresholds

| Group | Tests | Required Pass | Acceptable Failures |
|-------|-------|---------------|---------------------|
| G1 — Process Isolation | 12 | 12 | 0 (OS boundary) |
| G2 — Capability Enforcement | 15 | 15 | 0 (security) |
| G3 — Network Block | 12 | 12 | 0 (security) |
| G4 — Filesystem Control | 12 | 12 | 0 (security) |
| G5 — Resource Quotas | 15 | 14 | 1 (platform-dependent RLIMIT) |
| G6 — E2E Flow | 15 | 15 | 0 (integration) |
| **Total** | **81** | **80** | **1** |

### 4.2 Hardening Rules

1. **Security tests (G2, G3, G4)**: Zero tolerance for failure. A failing security test is a P0 incident.
2. **OS-boundary tests (G1)**: All must pass. Subprocess handling is critical for RULE 4.
3. **Quota tests (G5)**: RLIMIT tests may fail on platforms without `resource` module (Windows). Must skip gracefully.
4. **E2E tests (G6)**: All must pass. Integration path is the Phase 4 deliverable.

### 4.3 Required Assertions per Group

```
G1: assert_called_with(sys.executable, ...)
    assert_called_once() on cleanup
    assertRaises(ExecutionTimeoutError)
    assertFalse(kill("unknown_id"))

G2: assertRaises(CapabilityViolation)
    assertEqual(CapabilityStatus.allowed, True/False)
    assertIn("allowed_paths", context.__dict__)

G3: assertRaises(IOViolation)
    assertRaises(NetworkBlocked)
    assertEqual(NetworkMode, expected)
    assertIsInstance(result, dict)

G4: assertRaises(FileAccessViolation)
    assertEqual(FilesystemMode, expected)
    assertTrue/False(is_path_allowed(path))

G5: assertRaises(QuotaExceeded)
    assertEqual(enforce(), True/False)
    assertGreater(tracker.usage.cpu_time, 0)

G6: assertEqual(result["status"], "completed"/"blocked"/"failed")
    assertIsNotNone(result["elapsed"])
    assertEqual(active_count(), 0 after cleanup)
```

---

## 5. Test Execution

```bash
# Run all Phase 4 isolation tests
pytest tests/test_runtime_isolation.py -v

# Run specific group via marker
pytest tests/test_runtime_isolation.py -v -k "test_capability or test_network_block"

# Run with coverage
pytest tests/test_runtime_isolation.py --cov=core/runtime/isolation --cov=core/runtime/sandbox --cov=core/runtime/io --cov=core/runtime/resources --cov-report=term-missing
```

### 5.1 CI Integration

```yaml
# .github/workflows/phase4-isolation.yml (design)
phase4-isolation:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with: { python-version: "3.11" }
    - run: pip install -r requirements.txt
    - run: pytest tests/test_runtime_isolation.py -v --tb=short --no-header
    - name: Enforce Zero-Failures
      if: failure()
      run: echo "Phase 4 isolation tests must pass — see DEVELOPER.md §15.15b" && exit 1
```
