# Phase L — Memory Lifecycle State Machine & Pruning

## Overview

The Cognitive Memory Layer defines a state machine that governs how execution
traces flow through the four memory layers (WORKING → EPISODIC → PROCEDURAL →
SEMANTIC) and how deterministic forgetting (pruning) policies are applied.

Every transition is guarded by tenant isolation checks (LAW 11 / LAW 15) and
logged via `cognitive_trace_id` for full auditability (LAW 8).

### References

- ROADMAP 🔟 FINAL — Phase L: Cognitive Memory OS
- DEVELOPER.md §15.14, §15.16
- Canon LAW 6, LAW 8, LAW 11, LAW 14, LAW 15
- RULE 1 (No cross-layer imports), RULE 3 (Replay safety)
- `artifacts/design/phase_l/protocols/01_cognitive_memory_protocols.py`
- `artifacts/design/phase_l/models/02_memory_and_context_models.py`
- `artifacts/design/j2/03_tenant_isolation_machine.md`

---

## 1. State Transition Map

```
                         ┌──────────────────────────────────────┐
                         │          EXECUTION COMPLETE          │
                         │  (ExecutionEvent → EventBus hook)    │
                         └────────────┬─────────────────────────┘
                                      │ T1: on_execution_complete
                                      ▼
                         ┌──────────────────────────────────────┐
                         │         TRACE ARCHIVE (EPISODIC)     │
                         │  Store raw trace + metadata          │
                         │  Guard G-M1: tenant_id matches       │
                         └────────────┬─────────────────────────┘
                                      │ T2: on_trace_archived
                                      ▼
                         ┌──────────────────────────────────────┐
                         │       CONTEXT EXTRACTION (WORKING)   │
                         │  Compress trace → ContextWindow      │
                         │  Guard G-M2: token budget respected  │
                         │  Guard G-M3: scope_verified check    │
                         └──────┬──────────────┬───────────────┘
                                │              │
                    T3a: skill  │              │ T3b: semantic
                    detected    │              │ facts present
                                ▼              ▼
              ┌──────────────────────┐  ┌──────────────────────┐
              │  LAYER ROUTING       │  │  LAYER ROUTING       │
              │  → PROCEDURAL        │  │  → SEMANTIC          │
              │  Guard G-M4:         │  │  Guard G-M5:         │
              │  skill_intent_match  │  │  fact_consistency    │
              └──────────┬───────────┘  └──────────┬───────────┘
                         │                         │
                         └──────┬──────────────────┘
                                │ T4: route_complete
                                ▼
              ┌──────────────────────────────────────┐
              │        STORE / PRUNE / INDEX         │
              │  Apply ForgettingPolicy → PruneDecision │
              │  Guard G-M6: deterministic eviction  │
              └──────────────────────────────────────┘
```

### Transition Table

| ID  | From                  | To                    | Trigger                | Guards |
|-----|-----------------------|-----------------------|------------------------|--------|
| T1  | EXECUTION_COMPLETE    | TRACE_ARCHIVE         | EventBus hook received | G-M1   |
| T2  | TRACE_ARCHIVE         | CONTEXT_EXTRACTION    | Archive acknowledged   | G-M2   |
| T3a | CONTEXT_EXTRACTION    | ROUTE_TO_PROCEDURAL   | Skill intent detected  | G-M3, G-M4 |
| T3b | CONTEXT_EXTRACTION    | ROUTE_TO_SEMANTIC     | Semantic facts present | G-M3, G-M5 |
| T4  | ROUTE_TO_PROCEDURAL/SEMANTIC | STORE_INDEX   | Route complete         | G-M6   |
| T5  | STORE_INDEX           | IDLE/READY            | Prune/index done       | (none) |

### Guard Descriptions

| Guard | Name                    | Check                                                         |
|-------|-------------------------|---------------------------------------------------------------|
| G-M1  | Tenant Match            | Trace `tenant_id` == Memory `tenant_id`                       |
| G-M2  | Token Budget Respect    | ContextWindow.token_count <= TokenBudget.max_tokens            |
| G-M3  | Scope Verified          | scope_verified==True for cross-tenant access (else BLOCK)     |
| G-M4  | Skill Intent Match      | query_intent similarity >= threshold (configurable, default 0.7) |
| G-M5  | Fact Consistency        | Semantic facts do not contradict existing graph state          |
| G-M6  | Deterministic Eviction  | Same input state + same policy = same eviction set            |

---

## 2. Memory Consistency Matrix

How the memory hierarchy prevents cross-tenant context leakage and ensures
deterministic behaviour.

| Concern                      | Mechanism                                                     | Canon Law |
|------------------------------|---------------------------------------------------------------|-----------|
| Cross-tenant context leak    | Every `MemoryEntry` carries `tenant_id`. Retrieval filters by tenant. G-M3 enforces `scope_verified` for cross-tenant. | LAW 11, LAW 15, RULE 3 |
| Context drift                | `ContextWindow._hash` is deterministic; same trace + budget = same hash. | LAW 14 |
| Stale skill recommendations  | `SkillNode.success_rate` + `relevance_score` decay over idle time via `ForgettingPolicy`. | LAW 8 |
| Forgetting non-determinism   | `PruningPolicy` TTL is wall-clock based; same policy applied at same time to same state = same eviction set. | LAW 14 |
| Layer overflow               | `max_entries` per (layer, tenant_id) enforces capacity; oldest/lowest-scored evicted first. | RULE 1 |
| Compiler hallucination       | `SafetyBounds._safety_hash` locks the isolation contract; `validate_boundary_safety()` rejects mismatches. | LAW 15, RULE 3 |

---

## 3. Deterministic Retrieval Table

The ContextCompiler guarantees that the same (trace_id, tenant_id, max_tokens,
scope_verified) input produces the SAME ContextWindow output across repeated
calls.  This is the foundation for replay-safe prompt construction.

| Input Component       | Deterministic? | Notes                                               |
|-----------------------|----------------|-----------------------------------------------------|
| Trace ID              | YES            | Maps to exact EPISODIC entry                        |
| Tenant ID             | YES            | Filter key, part of safety hash                     |
| Max Tokens            | YES            | Clips context at exact boundary                     |
| Scope Verified        | YES            | Boolean flag, part of safety hash                   |
| Skill Retrieval       | PARTIAL        | Same top-K results for same query; ordering stable  |
| Semantic Facts        | YES            | Graph is immutable between mutations                |
| Forgetting History    | YES            | Prune decisions are deterministic per policy         |

### Context Drift Prevention

```
Same Trace
    │
    ├── Call 1: compress_trace_to_context(trace_id="X", max_tokens=4096)
    │           → ContextWindow{_hash: "abc123", ...}
    │
    ├── Call 2: compress_trace_to_context(trace_id="X", max_tokens=4096)
    │           → ContextWindow{_hash: "abc123", ...}  ✓ identical
    │
    └── Call 3: compress_trace_to_context(trace_id="X", max_tokens=2048)
                → ContextWindow{_hash: "def456", ...}  ✓ different budget → expected
```

If any call produces a different hash for the same inputs, the system has a
determinism violation and MUST trigger a ContextDrift alert.

---

## 4. Pruning Lifecycle

```
    ┌──────────┐    TTL Expired?    ┌──────────────┐
    │ Memory   │ ─────────────────→ │ Candidate    │
    │ Entry    │                    │ for Eviction │
    │ stored   │                    └──────┬───────┘
    └──────────┘                           │
        │                            Frequency check
        │ Capacity exceeded?         (FREQUENCY_BASED)
        │                              │
        ▼                              ▼
    ┌──────────┐                 ┌──────────────┐
    │ Evict by │                 │ Evict by     │
    │ TTL      │                 │ access_count │
    └──────────┘                 └──────────────┘
        │                              │
        └──────────┬───────────────────┘
                   ▼
        ┌──────────────────────┐
        │  PruneDecision       │
        │  → audit log         │
        │  → MemoryPruneEvent  │
        │  → update indices    │
        └──────────────────────┘
```

### Pruning Guarantees

1. **Determinism**: Applying the same `ForgettingPolicy` (layer, policy_type,
   ttl_seconds, max_entries, decay_factor, tenant_id) to the same memory state
   always produces the same `PruneDecision.evicted_keys`.
2. **Isolation**: Pruning is scoped by `tenant_id`. No tenant's entries are
   evicted by another tenant's pruning cycle.
3. **Auditability**: Every `PruneDecision` is tagged with `cognitive_trace_id`
   and stored for replay.
4. **Dry-run support**: `IMemoryHierarchy.prune(dry_run=True)` reports what
   WOULD be evicted without mutating state.

---

## 5. Event Hooks

| Event                          | Emitted By            | Payload                          |
|--------------------------------|-----------------------|----------------------------------|
| `MemoryPruneTriggered`         | Pruning cycle         | `MemoryPruneTriggeredReport`     |
| `ContextOverflow`              | ContextCompiler       | `ContextOverflowReport`          |
| `SkillMismatch`                | SkillGraphManager     | `SkillMismatchReport`            |
| `TenantIsolationEnforced`      | All protocols         | `TenantIsolationEnforcedReport`  |

All events carry `cognitive_trace_id` and `tenant_id` for correlation with
the originating execution trace.
