# Phase G — Orchestration Lifecycle & Failure Model

**State machine, consistency guards, deterministic handoff, and failure propagation matrix for the Cognitive Orchestration Layer.**

---

## 1. State Machine: Intent → Execution

```
                    ┌──────────────────────────────────────────────┐
                    │              FEEDBACK LOOP                   │
                    │  (max_retries = 3, then → ABORTED)          │
                    └──────┬───────────────────────────────┬───────┘
                           │                               │
                    ┌──────▼──────┐                 ┌──────▼──────┐
  Intent ──► PLANNING ──► CRITICIZING ──► APPROVED ──► OPTIMIZING ──► EXECUTING ──► COMPLETED
                    │               │                               │
                    │               ▼                               │
                    │          REJECTED ──► (Feedback loop back to  │
                    │                        PLANNING or ABORTED)   │
                    │                                               │
                    └────────────────── ABORTED ◄───────────────────┘
```

### State Definitions

| State | Owner | Description |
|-------|-------|-------------|
| `PLANNING` | IPlannerAgent | Synthesizing DAG from intent + context_window |
| `CRITICIZING` | ICriticAgent | Evaluating proposal against constraints |
| `OPTIMIZING` | IOptimizerAgent | Improving approved DAG for resource efficiency |
| `APPROVED` | Orchestrator | Plan accepted by Critic, awaiting handoff |
| `REJECTED` | Orchestrator | Plan rejected, entering feedback loop |
| `ABORTED` | Orchestrator | Max retries exceeded or unrecoverable conflict |
| `EXECUTING` | EmoRuntimeFacade | DAG submitted to runtime |
| `COMPLETED` | Orchestrator | Execution finished |

### Transitions

| ID | From | To | Trigger | Guard |
|----|------|----|---------|-------|
| G-T1 | `PLANNING` | `CRITICIZING` | IPlannerAgent.synthesize_dag() returns PlanProposal | G-P1: retry_count ≤ MAX_RETRY |
| G-T2 | `CRITICIZING` | `APPROVED` | ICriticAgent.evaluate_plan() → is_valid=True | G-P2: scope_verified=True if cross-tenant |
| G-T3 | `CRITICIZING` | `REJECTED` | ICriticAgent.evaluate_plan() → is_valid=False | G-P3: rejection_reason non-empty |
| G-T4 | `REJECTED` | `PLANNING` | IPlannerAgent.adapt_on_failure() → RevisedPlan | G-P4: plan_hash ≠ original (no oscillation) |
| G-T5 | `REJECTED` | `ABORTED` | retry_count > MAX_RETRY | G-P5: max_retries_exceeded |
| G-T6 | `PLANNING` | `ABORTED` | Intent irreconcilable or tenant violation | G-P6: abort_signal_received |
| G-T7 | `APPROVED` | `OPTIMIZING` | IOptimizerAgent.optimize_execution_graph() ready | G-P7: proposal_hash unchanged |
| G-T8 | `OPTIMIZING` | `EXECUTING` | DAG submitted via EmoRuntimeFacade.submit() | G-P8: facade.submit() returns ok |
| G-T9 | `EXECUTING` | `COMPLETED` | Execution finished successfully | — |

---

## 2. Consistency Guards (G-P1–G-P8)

| Guard | Rule | Effect |
|-------|------|--------|
| G-P1 | `retry_count ≤ MAX_RETRY (default 3)` | Prevents infinite Planner↔Critic loops |
| G-P2 | `scope_verified=True` if proposal cross-tenant | Blocks unverified cross-tenant plans (LAW 15) |
| G-P3 | `rejection_reason` must be non-empty | Prevents silent rejects |
| G-P4 | `plan_hash` of revised ≠ original | Blocks plan oscillation (same plan resubmitted) |
| G-P5 | `retry_count > MAX_RETRY → ABORTED` | Hard limit on negotiation cycles |
| G-P6 | Abort if intent cannot be mapped to any tool chain | Prevents stalled planning |
| G-P7 | `proposal_hash` unchanged between APPROVED→OPTIMIZING | Prevents optimizer from changing the approved plan |
| G-P8 | `facade.submit()` must return `status=ok` | Ensures DAG actually reached runtime |

---

## 3. Failure Propagation Matrix

| Failure Mode | Impact | Containment | Recovery |
|-------------|--------|-------------|----------|
| **Planner timeout** | PLAN_PROPOSED never emitted | G-P6 → ABORTED | Retry with backoff (max 3) |
| **Critic rejection (valid)** | Plan → REJECTED | G-P3 requires reason | Feedback loop → adapt_on_failure |
| **Critic rejection (oscillating)** | Same plan resubmitted | G-P4 detects hash match | Escalate → ABORTED |
| **Optimizer failure** | OPTIMIZATION_APPLIED not emitted | G-P7 preserves original | Fall back to non-optimized DAG |
| **Facade submit failure** | DAG not executed | G-P8 blocks EXECUTING | Retry or ABORTED |
| **Tenant scope violation** | Cross-tenant context in plan | G-P2 blocks; T1_SCOPE_VIOLATION emitted | Plan scrapped; ABORTED |
| **Memory layer unavailable** | ContextWindow retrieval fails | Graceful: fall back to empty context | Planner works with minimal context |
| **EventBus partition** | Events lost between agents | Correlation ID detects gaps | Resend on EventBus reconnect |

---

## 4. Deterministic Handoff Table

Same (intent + context + constraints) must produce the same orchestration path.
This table documents the expected deterministic behaviour:

| Pattern | Input Triplet | Expected Path | Expected Hash |
|---------|---------------|---------------|---------------|
| P1 | (intent="summarize", context={...}, budget=4k) | PLANNING → CRITICIZING → APPROVED → OPTIMIZING → EXECUTING | `sha256(intent + hash(context) + str(budget))` |
| P2 | (intent="unknown", context={}, budget=1k) | PLANNING → CRITICIZING → REJECTED → ABORTED | `sha256("unknown" + "" + "1000")` |
| P3 | (intent="transcribe", context={...cross-tenant...}, budget=2k) | PLANNING → CRITICIZING → REJECTED (scope violation) | Blocked at G-P2 |

**Determinism guarantee**: Given the same (intent, context_window._hash, constraints JSON),
the orchestration layer MUST produce the same:
- state transition sequence
- PlanProposal._hash
- final outcome (APPROVED / REJECTED / ABORTED)

---

## 5. Orchestration Consistency Anti-Patterns (Prevented by Design)

| Anti-Pattern | Prevention |
|-------------|------------|
| **Infinite Planner↔Critic loop** | G-P1: max_retry=3, then G-P5 → ABORTED |
| **Plan oscillation** | G-P4: same plan_hash → blocked |
| **Optimizer diverging from approved plan** | G-P7: proposal_hash enforced |
| **Silent critic rejection** | G-P3: non-empty reason required |
| **Cross-tenant data leak via plan** | G-P2: scope_verified required |
| **DAG submitted without optimizer** | G-T7: APPROVED → OPTIMIZING mandatory (even if optimizer is no-op) |
