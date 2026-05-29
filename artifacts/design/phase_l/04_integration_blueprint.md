# Phase L — Integration Blueprint: F1 / J2 / I1 / F4 / L

## Overview

This document specifies how the Phase L Cognitive Memory Layer integrates with
the existing runtime architecture without breaking enterprise isolation, service
boundaries, or deterministic wiring.

Three integration surfaces are defined:

1. **EventBus hook** — `ExecutionEvent` → `MemoryRouter` subscription
2. **ContextCompiler pipeline** — `IMemoryHierarchy.retrieve()` → `IContextCompiler.compress()`
3. **SkillGraph feedback loop** — `ISkillGraphManager` ↔ `F4.Observability`

### References

- ROADMAP 🔟 FINAL — Phase L: Cognitive Memory OS
- DEVELOPER.md §15.14, §15.16
- Canon LAW 6 (Shared models), LAW 8 (Recoverability), LAW 11 (Enterprise Isolation)
- Canon LAW 14 (Deterministic Retrieval), LAW 15 (Tenant Context Isolation)
- RULE 1 (No cross-layer imports), RULE 2 (All systems require interfaces)
- RULE 3 (Replay safety), RULE 4 (Deterministic Wiring)
- `artifacts/design/phase_l/protocols/01_cognitive_memory_protocols.py`
- `artifacts/design/phase_l/models/02_memory_and_context_models.py`
- `artifacts/design/j2/04_integration_blueprint.md`

---

## 1. Data Flow Diagram

```
  ┌──────────────┐     ┌──────────────────┐     ┌─────────────────┐
  │  F1 Runtime  │     │   J2 Enterprise  │     │  I1 Object      │
  │  (UnifiedAPI)│     │   TenantRouter   │     │  Storage        │
  └──────┬───────┘     └────────┬─────────┘     └────────┬────────┘
         │                      │                        │
         │ ExecutionEvent       │ enterprise_trace_id     │ trace archives
         ▼                      ▼                        ▼
  ┌───────────────────────────────────────────────────────────────┐
  │                    EventBus (InMemoryEventBus)                 │
  │  Topics:  execution.completed │ tenant.routed │ audit.logged  │
  └──────┬──────────────────────────────────────────────┬─────────┘
         │ subscribe("execution.completed")             │
         ▼                                              │
  ┌──────────────────────┐                              │
  │   MemoryRouter       │                              │
  │   (Phase L Gateway)  │                              │
  │                      │                              │
  │  T1: on_exec_event() │                              │
  │  → extract tenant_id │                              │
  │  → generate cog_tid  │                              │
  │  → route to layer    │                              │
  └──────┬───────────────┘                              │
         │                                              │
    ┌────┴────────────────────┐                         │
    │                         │                         │
    ▼                         ▼                         │
  ┌────────────────┐  ┌─────────────────┐              │
  │ IMemoryHierarchy│  │ IContextCompiler │             │
  │                │  │                 │              │
  │ store()        │  │ compress_trace() │             │
  │ retrieve()     │  │ inject_intel()   │             │
  │ prune()        │  │ validate_safety()│             │
  │ get_context()  │  └────────┬────────┘              │
  └──────┬─────────┘           │                       │
         │                     │                       │
         ▼                     ▼                       │
  ┌──────────────────────────────────┐                 │
  │   ISkillGraphManager             │                 │
  │   (Procedural Memory)            │                 │
  │                                  │                 │
  │  record_successful_plan()        │                 │
  │  retrieve_skill()                │                 │
  │  update_procedural_weight()      │                 │
  │  record_failure_pattern()        │                 │
  └──────────┬───────────────────────┘                 │
             │                                         │
             ▼                                         ▼
  ┌──────────────────┐                     ┌────────────────────┐
  │  F4 Observability│                     │  ContextStore      │
  │  (events/alerts) │                     │  (EPISODIC backing)│
  └──────────────────┘                     └────────────────────┘
```

### Flow Description

1. `F1.UnifiedRuntimeAPI` completes execution → publishes `ExecutionEvent` on
   `EventBus` topic `execution.completed`.
2. `MemoryRouter` (Phase L gateway) subscribes to `execution.completed`.
3. On event: extracts `tenant_id`, `trace_id`, generates `cognitive_trace_id`,
   and calls `IMemoryHierarchy.store(layer=EPISODIC, ...)`.
4. If the trace contains skill-worthy patterns, `ISkillGraphManager.record_successful_plan()`
   is invoked (→ PROCEDURAL layer).
5. On context request: `IContextCompiler.compress_trace_to_context()` retrieves
   from EPISODIC, enriches from PROCEDURAL/SEMANTIC, validates safety bounds.
6. Compiled `ContextWindow` is returned to the requesting layer (F1 or J2).
7. All events (overflow, mismatch, prune, isolation violation) are published to
   F4 Observability via dedicated EventBus topics.

---

## 2. Correlation ID Strategy: `cognitive_trace_id`

### Trace Chain Across Layers

```
F1 trace_id ──┬──→ enterprise_trace_id (J2)
              │
              └──→ cognitive_trace_id (Phase L)
```

**Rule**: Each Phase L operation generates a unique `cognitive_trace_id` that
is correlated with the originating `enterprise_trace_id` and `F1 trace_id`.

### ID Format

```
cognitive_trace_id = "cog_<sha256(tenant_id + session_id + timestamp_ns)>[:28]"
```

This follows the same convention as `enterprise_trace_id` (`entr_...`) for
consistency across phases.

### Backward Trace Resolution

```
ContextWindow._hash   ──→   cognitive_trace_id   ──→   enterprise_trace_id   ──→   F1 trace_id
     (compiler output)         (memory operation)        (J2 routing)               (execution)
```

Given any `ContextWindow`, a security auditor can resolve ALL the way back to
the originating `F1 trace_id` and `ExecutionEvent`.  This satisfies LAW 8
(Recoverability) and LAW 12 (Traceability).

---

## 3. Integration Hook Points

### Hook 1: EventBus → MemoryRouter

| Element | Specification |
|---------|---------------|
| Topic | `execution.completed` |
| Subscription | `MemoryRouter._on_execution_completed(event: ExecutionEvent)` |
| Guard | `event.tenant_id` must be non-empty (G-M1) |
| Output | `IMemoryHierarchy.store(layer=EPISODIC, ...)` |
| Error handling | Logged; does NOT crash EventBus (subscriber isolation per CHAOS-001) |

### Hook 2: ContextCompiler → Enterprise Layer

| Element | Specification |
|---------|---------------|
| Integration | `IContextCompiler.compress_trace_to_context()` calls `TenantRouter.validate_tenant_scope()` |
| Purpose | Verify tenant isolation before releasing context |
| Trigger | Every context compilation |
| Cost | +1 async call, budgeted within 50ms latency budget |
| Failure mode | Returns `{"status": "violation"}` ; ContextOverflowReport emitted |

### Hook 3: SkillGraph → F4 Observability

| Element | Specification |
|---------|---------------|
| Integration | `ISkillGraphManager.record_successful_plan()` publishes to topic `skill.recorded` |
| Purpose | F4 aggregates skill success rates, pruning events, context overflow alerts |
| Events | `MemoryPruneTriggered`, `ContextOverflow`, `SkillMismatch`, `TenantIsolationEnforced` |
| Retention | 7 days in EventBus history; archived to I1 ObjectStorage |

---

## 4. Integration Acceptance Criteria

### Latency Budgets

| Operation | Budget | Violation Action |
|-----------|--------|------------------|
| Memory store (EPISODIC) | ≤ 50ms | Log warning, continue |
| Context compilation | ≤ 200ms | Emit ContextOverflow report |
| Skill retrieval | ≤ 100ms | Fall back to exact-only mode |
| Pruning cycle | ≤ 500ms | Defer to background batch |
| Full context window build | ≤ 300ms | Return partial window |

### Determinism Thresholds

| Metric | Threshold | Enforcement |
|--------|-----------|-------------|
| Context hash match rate | ≥ 99.9% | `ContextWindow._hash` comparison |
| Skill retrieval stability | ≥ 99.0% | Same top-K across 3 consecutive calls |
| Prune decision determinism | 100% | `PruneDecision._hash` across dry runs |

### Isolation Thresholds

| Metric | Threshold | Enforcement |
|--------|-----------|-------------|
| Cross-tenant context leakage | 0 | `SafetyBounds._safety_hash` + G-M3 |
| Cross-tenant data in prune | 0 | Pruning scoped by `tenant_id` |
| Scope-verified bypass attempts | 0 | All cross-tenant access requires `scope_verified=True` |

### Rollback Conditions

| Condition | Action |
|-----------|--------|
| Context hash mismatch (same inputs) | ROLLBACK compiler to last known-good version |
| Cross-tenant data found in ContextWindow | STOP + AUDIT all windows for that tenant |
| Skill graph corruption detected | RESTORE from last deterministic checkpoint |
| Pruning evicts wrong tenant's data | RESTORE from I1 archive |

---

## 5. Architectural Boundaries

```
┌─────────────────────────────────────────────────────────────┐
│                   Phase L Boundary                          │
│                                                             │
│  IMemoryHierarchy    IContextCompiler    ISkillGraphManager  │
│       │                    │                    │            │
│       └────────────────────┼────────────────────┘            │
│                            │                                 │
│                     MemoryRouter                             │
│                            │                                 │
│                     EventBus (topic hook)                    │
└────────────────────────────┼─────────────────────────────────┘
                             │
              ┌──────────────┴──────────────┐
              │                             │
              ▼                             ▼
     ┌────────────────┐           ┌──────────────────┐
     │  F1 Runtime    │           │  J2 Enterprise   │
     │  (unmodified)  │           │  (unmodified)    │
     └────────────────┘           └──────────────────┘
```

**Key constraint**: Phase L has NO direct access to `ExecutionCore`, `GovernancePlane`,
or `Service Mesh`.  All integration is through `EventBus` topics and
`EmoRuntimeFacade` protocol methods — the same surfaces used by HTTP routers.
