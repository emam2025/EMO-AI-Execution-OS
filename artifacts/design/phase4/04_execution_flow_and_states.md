# Phase 4 — Execution Flow & State Machine

> Design document conforming to DEVELOPER.md §15.15b
> Enforces RULE 1-4 as defined in Architecture Canon §16

---

## 1. RULE 3 — 5-Step Execution Flow

All execution MUST follow exactly this sequence. No step may be skipped or reordered.

```
┌─────────────────────────────────────────────────────────────────┐
│  ExecutionEngine                                                 │
│    ↓ (NO direct subprocess — MUST go through IsolationRuntime)   │
├─────────────────────────────────────────────────────────────────┤
│  IIsolationRuntime.execute(tool_name, inputs)                    │
│                                                                  │
│  Step 1: ICapabilityGuard.validate(tool, inputs)                 │
│    │  Verifies capability exists + inputs respect restrictions   │
│    │  → CapabilityViolation if not permitted                    │
│    ↓                                                             │
│  Step 2: IResourceEnforcer.check_before_scheduling()             │
│    │  Pre-checks quotas (per-execution, per-worker, global)      │
│    │  → QuotaExceeded if thresholds breached                    │
│    ↓                                                             │
│  Step 3: SandboxManager.create_sandbox(context)                  │
│    │  Creates isolated subprocess executor                       │
│    │  Injects secrets (E3 integration)                           │
│    │  → SandboxError on creation failure                        │
│    ↓                                                             │
│  Step 4: ISandboxExecutor.execute(tool, inputs, context)         │
│    │  Spawns subprocess with RLIMIT_AS / RLIMIT_CPU              │
│    │  Enforces timeout via watchdog thread                       │
│    │  Supports SIGKILL via kill(exec_id)                         │
│    │  → ExecutionTimeoutError / ResourceLimitExceeded            │
│    ↓                                                             │
│  Step 5: IResourceEnforcer.finish()                              │
│    │  Captures telemetry (cpu, memory, wall_time, io_bytes)      │
│    │  Archives usage to ResourceTracker                          │
│    │  Destroys sandbox                                           │
│    ↓                                                             │
│  Return ExecutionResult                                          │
└─────────────────────────────────────────────────────────────────┘
```

### RULE 1 Enforcement (No Direct Execution)

- `ExecutionEngine` MUST NOT call `subprocess.Popen()`, `ThreadPoolExecutor.submit()`, or any OS-level function directly.
- All node execution MUST route through `IsolationRuntime.execute()`.
- The `_pool.submit(self._runtime.execute_node_safe, ...)` pattern in `ExecutionEngine.execute()` MUST be replaced with `IsolationRuntime.execute(tool_name, inputs)`.

### RULE 2 Enforcement (No Uncontrolled IO)

- All IO operations must pass through `IOPolicyEngine.check()` before proceeding.
- Internal runtime IO (config files, logs) MUST be explicitly allowed via `IOPolicyEngine.set_policy("runtime", "*", IOPolicy(allowed=True))`.
- External IO (network requests, file reads/writes by tools) MUST be validated against tool capability.

### RULE 4 Enforcement (Everything is Killable)

- Every subprocess spawn MUST be tracked by `execution_id` in `SandboxExecutor._processes`.
- `kill(exec_id)` must send SIGKILL and wait up to 5s for process death.
- No infinite loops — all execution has a timeout from `SandboxContext.timeout`.
- RLIMIT_AS / RLIMIT_CPU enforce memory and CPU bounds at the OS level.

---

## 2. State Transition Matrix

| From | To | Condition | Action |
|------|----|-----------|--------|
| PENDING | VALIDATED | CapabilityGuard.validate() passes | Proceed to Step 2 |
| PENDING | FAILED | CapabilityGuard.validate() raises | Return CapabilityViolation |
| VALIDATED | RESOURCE_CHECKED | ResourceEnforcer.check_before_scheduling() passes | Proceed to Step 3 |
| VALIDATED | FAILED | ResourceEnforcer raises QuotaExceeded | Return quota error |
| RESOURCE_CHECKED | SANDBOX_CREATED | SandboxManager.create_sandbox() succeeds | Proceed to Step 3.5 |
| RESOURCE_CHECKED | FAILED | SandboxManager.create() raises SandboxError | Return sandbox error |
| SANDBOX_CREATED | EXECUTING | SandboxExecutor.execute() call accepted | Proceed to Step 4 |
| SANDBOX_CREATED | FAILED | Secret injection fails | Return secret error |
| EXECUTING | TELEMETRY_ARCHIVED | SandboxExecutor completes (success/error) | Proceed to Step 5 |
| EXECUTING | KILLED | IsolationRuntime.kill() called externally | Return cancelled |
| EXECUTING | TIMED_OUT | Watchdog detects timeout > context.timeout | Return timeout error |
| EXECUTING | FAILED | ResourceEnforcer.enforce() returns False | Kill + return quota error |
| EXECUTING | FAILED | Subprocess returns non-zero exit code | Return execution error |
| TELEMETRY_ARCHIVED | (terminal) | ResourceEnforcer.finish() + sandbox destroy | Return ExecutionResult |
| FAILED | (terminal) | Error captured + telemetry archived | Return ExecutionResult |
| KILLED | (terminal) | Process killed + cleanup complete | Return cancelled result |
| TIMED_OUT | (terminal) | Process killed + timeout error returned | Return timeout result |

---

## 3. Failure Propagation Matrix

| Step | Failure Exception | Severity | Action | Canon Ref |
|------|------------------|----------|--------|-----------|
| 1 — Capabilities | `CapabilityViolation` | HIGH | **KILL** — Return 403 blocked | LAW 10, RULE 3 |
| 1 — Capabilities | `CapabilityRegistryError` | HIGH | **KILL** — Return 500 internal | LAW 23-27 |
| 2 — Resources | `QuotaExceeded` | MEDIUM | **RELEASE_LEASE** — Return 429 retry-after | LAW 10 |
| 2 — Resources | `ResourceLimitExceeded` | MEDIUM | **RELEASE_LEASE** — Return 429 retry-after | LAW 10 |
| 3 — Sandbox Create | `SandboxViolationError` | HIGH | **KILL** — Return 500 sandbox error | RULE 4 |
| 3 — Sandbox Create | `FileNotFoundError` (worker script) | MEDIUM | **RETRY** — Rebuild worker script | RULE 1 |
| 3.5 — Secrets | `SecretInjectionError` | HIGH | **KILL** — Return 401 secret error | LAW 23-27 |
| 4 — Execution | `ExecutionTimeoutError` | MEDIUM | **KILL** — SIGKILL + return timeout | RULE 4 |
| 4 — Execution | `ResourceLimitExceeded` (mid-flight) | MEDIUM | **KILL** — SIGKILL + return quota | RULE 4 |
| 4 — Execution | Subprocess non-zero exit | LOW | **RETRY** (if retry policy exists) | LAW 10 |
| 4 — Execution | Subprocess crash (SIGSEGV) | MEDIUM | **NOTIFY** — EventBus alert | LAW 10 |
| 5 — Telemetry | `TrackerError` | LOW | **NOTIFY** — Log warning, continue | Canon §9 |
| 5 — Telemetry | Quota release failure | LOW | **NOTIFY** — Monitor alert | LAW 23-27 |
| Any | `Exception` (uncaught) | CRITICAL | **KILL** — IsolateRuntime.shutdown() | RULE 4, LAW 10 |

### Action Definitions

| Action | Description |
|--------|-------------|
| **KILL** | Terminate execution immediately. Send SIGKILL to subprocess. Release lease. Return error to caller. |
| **RETRY** | Attempt re-execution (up to N retries defined by tool's RetryPolicy). Exponential backoff. |
| **RELEASE_LEASE** | Release resource lease for retry. Do NOT kill — the execution may be rescheduled. |
| **NOTIFY** | Emit event to EventBus. Do NOT kill — execution may continue (warnings only). |

---

## 4. RULE 4 — Killable Enforcement Architecture

### 4.1 SIGKILL Path
```
IsolationRuntime.kill(exec_id)
  → SandboxExecutor.kill(exec_id)
    → cancel_event.set()                [thread-based]
    → proc = _processes.pop(exec_id)     [subprocess-based]
    → proc.kill()                         [SIGKILL]
    → proc.wait(timeout=5.0)              [ensure death]
    → logger.info("Killed execution %s")
```

### 4.2 RLIMIT Mapping

| SandboxContext Field | RLIMIT | Behavior on Exceed |
|----------------------|--------|-------------------|
| `memory_limit` | `RLIMIT_AS` | `SIGSEGV` / `MemoryError` in subprocess |
| `cpu_limit` | `RLIMIT_CPU` | `SIGXCPU` followed by `SIGKILL` after grace |
| `timeout` | watchdog thread | `proc.kill()` → SIGKILL |

### 4.3 Termination Guarantees

- **No zombie processes**: `proc.wait()` called after `proc.kill()` with 5s timeout.
- **No dangling threads**: All watcher threads are daemon threads.
- **No infinite sandboxes**: `SandboxManager.shutdown()` destroys all active sandboxes.
- **No resource leaks**: `finally` block in `SandboxExecutor.execute()` always pops process tracking and cleans up worker scripts.

### 4.4 Guard Against RULE 4 Violations

| Anti-Pattern | Detection | Fix |
|-------------|-----------|-----|
| Non-daemon thread in runtime | AST scan (`phase4_boundary_analysis.py`) | Convert to daemon=True |
| `ThreadPoolExecutor` outside SandboxManager | AST scan | Replace with per-node `SandboxExecutor.execute_direct()` |
| Manual `threading.Thread` without cancel event | AST scan | Wrap with `SandboxExecutor.execute_direct()` |
| Infinite `while True` without timeout | Code review | Add `context.cpu_limit` via `RLIMIT_CPU` |

---

## 5. Integration with Existing Components

### 5.1 ExecutionEngine → IsolationRuntime

`ExecutionEngine.execute()` current flow (Phase 3) → target flow (Phase 4):

```
PHASE 3 (Current):
  ExecutionEngine
    → _pool.submit(_runtime.execute_node_safe, node, runner, dag, session_id, strategy)
    → ExecutionRuntime.execute_node_safe()
      → Executes tool function directly in thread pool

PHASE 4 (Target):
  ExecutionEngine
    → IsolationRuntime.execute(tool_name, inputs)
      → CapabilityGuard.validate()
      → ResourceEnforcer.check_before_scheduling()
      → SandboxManager.create_sandbox()
      → SandboxExecutor.execute(tool_name, inputs, context)
      → ResourceEnforcer.finish()
    → Collects result, DAG state transitions
```

### 5.2 EventBus Integration

All state transitions emit events:

| State Transition | Event | Payload |
|-----------------|-------|---------|
| PENDING → VALIDATED | `EXECUTION_PLANNED` | tool_name, execution_id |
| VALIDATED → RESOURCE_CHECKED | `RESOURCE_CHECKED` | execution_id, quotas |
| RESOURCE_CHECKED → SANDBOX_CREATED | `SANDBOX_CREATED` | sandbox_id, execution_id |
| SANDBOX_CREATED → EXECUTING | `EXECUTION_STARTED` | tool_name, sandbox_id |
| EXECUTING → TELEMETRY_ARCHIVED | `EXECUTION_COMPLETED` | result, telemetry |
| Any → FAILED | `EXECUTION_FAILED` | error, reason, step |
| Any → KILLED | `EXECUTION_CANCELLED` | execution_id |

### 5.3 CanonValidator Integration

`IsolationRuntime` must expose a `validate_canon()` method that runs the `CanonValidationContext` before Step 1:

```python
def validate_canon(self, tool_name: str, codegraph: Any) -> CanonResult:
    ctx = CanonValidationContext(
        graph=codegraph,
        coupling_score=getattr(self, "_coupling_score", None),
        risk_score=getattr(self, "_risk_score", None),
    )
    return self._canon_validator.validate(ctx)
```

This is the Phase 3.7-4.5 integration point, ensuring Canon enforcement applies before isolation checks.
