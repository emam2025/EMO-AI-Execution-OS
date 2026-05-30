# R2 — Memory OS Architecture Manifest

> **EMO AI — Release 2: Memory Operating System**
> Status: **Interface & Isolation Layer (DRAFT)**
> Date: 2026-05-30

---

## 1. Overview

Memory OS transforms EMO from a task execution system into a system that **remembers, learns, and evolves** from its history. This release adds persistent memory layers with full tenant isolation, cognitive trace propagation, and controlled forgetting.

### Guard OS Principles Applied

| Principle | Enforcement |
|-----------|-------------|
| Memory stores, never executes | All interfaces are storage/retrieval only. No execution logic. |
| Retrieval is deterministic | Every retrieve() carries tenant_id + cognitive_trace_id filter. |
| Forgetting is policy-controlled | PruningPolicy enum governs TTL, LRU, importance-based eviction. |
| No cross-tenant leakage | tenant_id is mandatory on every operation (LAW-6). |
| Full audit trail | cognitive_trace_id propagates through every node (LAW-11). |

---

## 2. Isolation Matrix

| Concern | R1 (Runtime OS) | R2 (Memory OS) |
|---------|------------------|-----------------|
| Core Engine | ExecutionEngine, Orchestrator, Gateway | Memory interfaces + models only |
| State | Runtime state, agent state, task queues | Memory entries, context windows, skill graph |
| Data Flow | submit → execute → observe | store → retrieve → compile → recall |
| Governance | RBAC, Audit Trail, Tenant Isolation | (Delegates to R1 governance layer via IPC) |
| UI | Dashboard, RuntimeMonitor, TraceExplorer, Settings | MemoryHierarchy, ContextBrowser, TraceRecall |
| Deployment | releases/runtime-os/ | releases/memory-os/ |

### Zero Shared State

- No global variables shared between R1 and R2.
- No direct imports from `releases/runtime-os/`.
- All cross-release communication routes through IPC contracts only.

---

## 3. Canon Law Compliance

### LAW-6: Tenant Isolation

- **Applies to**: All memory operations (store, retrieve, prune, record, compress).
- **Enforcement**: `tenant_id` is a mandatory parameter in every interface method.
- **Violation**: Any operation without tenant_id → `IsolationViolation`.

### LAW-8: Context Safety Boundaries

- **Applies to**: `IContextCompiler.validate_boundary()`.
- **Enforcement**: Compiled context carries `safety_bounds` dict validated before injection.
- **Violation**: Context exceeding token budget or safety bounds → blocked.

### LAW-11: Cognitive Trace Propagation

- **Applies to**: Every interface method across all three protocols.
- **Enforcement**: `cognitive_trace_id` is mandatory on every call.
- **Chain**: `EventBus → MemoryRouter → IContextCompiler → IMemoryHierarchy → ISkillGraphManager`
- **Violation**: Missing trace_id → audit failure.

### LAW-14: Token Budget & Safety Bounds

- **Applies to**: `ContextWindow` model, `IContextCompiler.compress_trace()`.
- **Enforcement**: `ContextWindow.token_budget` vs `ContextWindow.tokens_used` enforced.
- **Violation**: `budget_exceeded` flag → caller must reduce context.

---

## 4. Trace Propagation Chain

```
EventBus.publish(topic, event)
    │
    ▼
MemoryRouter.route(event, tenant_id, cognitive_trace_id)
    │
    ├──► IContextCompiler.compress_trace(trace_id, tenant_id, cognitive_trace_id)
    │       │
    │       ├──► IContextCompiler.inject_intelligence(context, tenant_id, cognitive_trace_id)
    │       │
    │       └──► IContextCompiler.validate_boundary(context, tenant_id, cognitive_trace_id)
    │
    ├──► IMemoryHierarchy.store(layer, key, payload, tenant_id, cognitive_trace_id)
    │
    ├──► IMemoryHierarchy.retrieve(layer, query, tenant_id, cognitive_trace_id)
    │
    └──► ISkillGraphManager.record(skill, pattern, tenant_id, cognitive_trace_id)
```

Every node in this chain **MUST** forward the `cognitive_trace_id` unmodified.

---

## 5. Directory Structure

```
releases/memory-os/
├── core/
│   ├── __init__.py
│   ├── interfaces/memory/
│   │   ├── __init__.py
│   │   ├── hierarchy.py      # IMemoryHierarchy
│   │   ├── compiler.py        # IContextCompiler
│   │   └── skill_graph.py     # ISkillGraphManager
│   ├── models/
│   │   ├── __init__.py
│   │   └── memory.py          # MemoryEntry, ContextWindow, ForgettingPolicy
│   └── memory/
│       └── __init__.py         # Reserved for implementation
├── desktop/
│   └── emo-memory-explorer/    # Tauri/React skeleton
├── docs/
│   └── R2_MEMORY_ARCHITECTURE_MANIFEST.md
├── tests/
│   └── test_r2_isolation_and_contracts.py
├── deployment/                 # Reserved
├── certificates/              # Reserved
└── artifacts/
    └── RELEASE_MANIFEST_R2_DRAFT.json
```

---

## 6. Protocol Signatures Summary

| Interface | Method | Mandatory Params |
|-----------|--------|-------------------|
| IMemoryHierarchy | store() | layer, key, payload, tenant_id, cognitive_trace_id |
| IMemoryHierarchy | retrieve() | layer, query, tenant_id, cognitive_trace_id, limit |
| IMemoryHierarchy | prune() | layer, policy, tenant_id, cognitive_trace_id |
| IMemoryHierarchy | get_context_window() | tenant_id, cognitive_trace_id, window_size |
| IContextCompiler | compress_trace() | trace_id, tenant_id, cognitive_trace_id, max_tokens |
| IContextCompiler | inject_intelligence() | context, tenant_id, cognitive_trace_id |
| IContextCompiler | validate_boundary() | context, tenant_id, cognitive_trace_id |
| ISkillGraphManager | record() | skill_name, pattern, tenant_id, cognitive_trace_id |
| ISkillGraphManager | retrieve() | query, tenant_id, cognitive_trace_id |
| ISkillGraphManager | update_weight() | skill_id, delta, tenant_id, cognitive_trace_id |

---

## 7. Design Artifact

See `artifacts/design/memory_architecture_blueprint.md` for:
- MemoryOS data flow diagram
- Layer isolation boundaries
- Integration blueprint with R1 governance

---

*Prepared by EMO AI — Memory OS Foundation Phase*
*2026-05-30 · Interface-only release · Zero R1 mutations*
