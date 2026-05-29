# Phase G — Integration Blueprint: Memory Layer ↔ EventBus ↔ EmoRuntimeFacade

**Data flow, correlation ID strategy, hook points, and acceptance criteria for the Cognitive Orchestration Layer integration with Phase L (Memory) and F1 (Runtime).**

---

## 1. Data Flow Diagram

```
                    ┌────────────────── Phase G ──────────────────┐
                    │                                              │
  Intent ─────► ┌──────────┐  context_window  ┌──────────┐       │
                │ PLANNER  │◄───────────────── │  MEMORY  │       │
                │  AGENT    │                   │  LAYER   │       │
                └────┬─────┘   (via EventBus)  └──────────┘       │
                     │                                              │
               PlanProposal     ┌──────────┐   via EventBus──┐     │
                     ├─────────►│  CRITIC  │                 │     │
                     │          │  AGENT   │                 │     │
                     │          └────┬─────┘                 │     │
                     │               │                        │     │
                     │               ▼                        │     │
                     │         CritiqueReport                 │     │
                     │               │                        │     │
                     │               ▼                        │     │
                     │         ┌──────────┐  OptimizedDAG     │     │
                     │         │OPTIMIZER ├────────►          │     │
                     │         │  AGENT   │                   │     │
                     │         └──────────┘                   │     │
                     │               │                        │     │
                     ▼               ▼                        ▼     │
               ┌──────────────────────────────────────┐            │
               │         EventBus (F4)                │            │
               │  orchestration_trace_id propagation  │            │
               └──────────┬───────────────────────────┘            │
                          │                                        │
                          ▼                                        │
               ┌─────────────────────┐                             │
               │  EmoRuntimeFacade   │                             │
               │   .submit(plan)     │                             │
               └──────────┬──────────┘                             │
                          │                                        │
                          ▼                                        │
               ┌─────────────────────┐                             │
               │     DAG Runtime     │                             │
               │   (Phase F1 / L)    │                             │
               └─────────────────────┘                             │
                          │                                        │
                          ▼                                        │
               ExecutionFeedback ──► PlannerAgent.adapt_on_failure │
                          │                                        │
                          └─────── (or COMPLETED) ─────────────────┘
```

---

## 2. Correlation ID Chain

The orchestration layer introduces `orchestration_trace_id` that chains through every participating layer.

```
orchestration_trace_id ──► cognitive_trace_id ──► enterprise_trace_id ──► F1 trace_id
         │                        │                        │                    │
    Phase G                   Phase L                  Phase J2             Phase F1
    Orchestrator              Memory                   Enterprise           Runtime
```

### Propagation Rules (P-G1–P-G5)

| Rule | Description |
|------|-------------|
| P-G1 | Every agent call must carry `orchestration_trace_id` from parent context |
| P-G2 | `orchestration_trace_id` = `cog_{sha256(intent + tenant_id + ns)}` |
| P-G3 | On submit to facade, `orchestration_trace_id` is forwarded as `cognitive_trace_id` |
| P-G4 | Memory retrieve requests from planner embed `orchestration_trace_id` → stored in MemoryEntry |
| P-G5 | On execution feedback, the `orchestration_trace_id` is the join key back to the original plan |

**Format**: `og_{SHA256(intent + tenant_id + timestamp_ns)[:28]}`

---

## 3. Hook Points (EventBus Events)

| Hook | Emitter | Event Type | Payload |
|------|---------|------------|---------|
| **Plan Proposed** | IPlannerAgent | `plan_proposed` | PlanProposal, orchestration_trace_id, tenant_id |
| **Critic Evaluating** | ICriticAgent | `critic_evaluating` | proposal_id, orchestration_trace_id |
| **Plan Approved** | Orchestrator | `plan_approved` | proposal_id, execution_path_hash, orchestration_trace_id |
| **Plan Rejected** | Orchestrator | `plan_rejected` | CritiqueReport (violations), orchestration_trace_id |
| **Optimization Applied** | IOptimizerAgent | `optimization_applied` | OptimizedDAG summary, orchestration_trace_id |
| **Feedback Loop** | Orchestrator | `feedback_loop_triggered` | retry_count, proposal_id, orchestration_trace_id |
| **Tenant Scope Violation** | Guard (G-P2) | `tenant_scope_violation` | expected_tenant, detected_tenant, proposal_id |
| **Plan Conflict** | Orchestrator | `plan_conflict_detected` | ConflictType, involved_agents, orchestration_trace_id |
| **Orchestration Aborted** | Orchestrator | `orchestration_aborted` | reason, retry_count, orchestration_trace_id |

All hooks are consumed by:
- **GovernancePlane**: audit logging, compliance verification.
- **Observability Stack**: Metrics, latency tracking, SLI/SLO.
- **Phase L Memory**: Stored as Episodic memory for future planning reference.

---

## 4. Agent ↔ Memory Access Protocol

Memory Layer is consumed exclusively via EventBus. No agent has a direct reference to `IMemoryHierarchy`, `IContextCompiler`, or `ISkillGraphManager`.

```
Agent (Planner/Critic/Optimizer)
    │
    ▼
EventBus.request("memory.retrieve", {
    "layer": "semantic",
    "query": {...},
    "tenant_id": "...",
    "orchestration_trace_id": "...",
})
    │
    ▼
MemoryRouter (EventBus subscriber) ──► IMemoryHierarchy.retrieve()
    │
    ▼
EventBus.response(proposal_id, {
    "results": [...],
    "cognitive_trace_id": "...",
})
```

### Zero-Direct-Access Rule
- Agents MUST NOT import `core.memory.*`.
- Agents MUST NOT instantiate `MemoryHierarchy`, `ContextCompiler`, `SkillGraphManager`.
- Agents interact with Memory only via EventBus request/response or through facade methods.
- Direct access is a STOP-CONDITION violation.

---

## 5. Acceptance Criteria for Integration

| Criterion | Threshold | Measurement |
|-----------|-----------|-------------|
| **Latency: Plan → Compile Context** | ≤ 500ms p99 | EventBus round-trip timing |
| **Latency: Orchestration → Facade Submit** | ≤ 200ms p99 | Orchestrator internal |
| **Determinism: Same intent → same plan** | 100% identical PlanProposal._hash | Replay test across 3+ rounds |
| **Zero Direct Access** | 0 imports of `core.memory.*` in `core/orchestration/*` | Code review / grep |
| **Trace Completeness** | 100% of events carry orchestration_trace_id | Audit of all 9 hook events |
| **Rollback on Plan Invalidation** | 100% — no orphaned DAG in runtime | G-P8 guards submit; abort cleans up |
| **Tenant Isolation** | 0 cross-tenant leaks in plans | G-P2 guard enforcement |
| **Conflict Detection** | 100% of oscillation/hash-match conflicts detected | G-P4 guard; test with identical resubmit |

---

## 6. Resource Budget Allocation

| Component | CPU Budget | Memory Budget | Throughput |
|-----------|-----------|--------------|------------|
| IPlannerAgent.synthesize_dag() | 200ms p99 | 64 MB | 50 req/s |
| ICriticAgent.evaluate_plan() | 100ms p99 | 32 MB | 100 req/s |
| IOptimizerAgent.optimize_execution_graph() | 300ms p99 | 128 MB | 20 req/s |
| EventBus request/response overhead | 10ms p99 | 1 MB | 500 req/s |

---

## 7. Rollback Protocol on Plan Invalidation

If a plan is submitted to the runtime (EXECUTING state) but later invalidated:

1. **Detect invalidation** via execution feedback or critic post-hoc analysis.
2. **Emit** `plan_conflict_detected` event with conflict type.
3. **PlannerAgent.adapt_on_failure()** generates a revised plan.
4. **If MAX_RETRY exceeded**: Emit `orchestration_aborted`; runtime receives cancellation signal.
5. **Memory cleanup**: Episodic memory entries for aborted plans are tagged `status=aborted`.
6. **Governance audit**: Full invalidation trail written to ComplianceAuditor.
