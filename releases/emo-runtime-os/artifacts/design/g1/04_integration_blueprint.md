# Phase G1 — Integration Blueprint: Planner ↔ F1/F4/D9/D8

**File:** `04_integration_blueprint.md`  
**Ref:** Canon LAW 1-8 (Core Determinism), LAW 23-27 (Service Isolation)  
**Ref:** DEVELOPER.md §15.2 (F1 Unified API), §15.13 (F4 Observability)  
**Ref:** `core/runtime/api/unified_runtime_api.py` (existing F1)  
**Ref:** `core/runtime/feedback/` (existing D9)  
**Ref:** `core/runtime/observability/` (existing F4)  
**Ref:** `core/runtime/services/` (existing D8)

---

## 1. System Data Flow

```
  ┌─────────────────────────────────────────────────────────────────────────────┐
  │                         Planner Agent (G1)                                  │
  │  ┌──────────┐  ┌──────────────┐  ┌──────────────────┐  ┌────────────────┐  │
  │  │Planner   │  │DAG           │  │Critic Feedback   │  │Swarm           │  │
  │  │Agent     │──│Synthesizer   │──│Loop              │──│Coordinator     │  │
  │  └────┬─────┘  └──────┬───────┘  └────────┬─────────┘  └───────┬────────┘  │
  └───────┼───────────────┼───────────────────┼────────────────────┼──────────┘
          │               │                   │                    │
          ▼               ▼                   ▼                    ▼
  ┌─────────────────────────────────────────────────────────────────────────┐
  │                          Inter-Subsystem Contracts                       │
  └──────┬──────────────┬──────────────┬──────────────┬─────────────────────┘
         │              │              │              │
         ▼              ▼              ▼              ▼
  ┌──────────┐  ┌────────────┐  ┌────────────┐  ┌───────────┐
  │ F1       │  │ D8         │  │ D9         │  │ F4        │
  │ Unified  │  │ Service    │  │ Feedback   │  │ Observ-   │
  │ Runtime  │  │ Mesh       │  │ Loop       │  │ ability   │
  └──────────┘  └────────────┘  └────────────┘  └───────────┘
```

### Flow Steps

| Step | Source | Action | Destination | Protocol / API |
|------|--------|--------|-------------|----------------|
| 1 | User / Agent | Submit intent | Planner Agent | `IPlannerAgent.synthesize_plan(intent, context)` |
| 2 | Planner Agent | Resolve dependencies | DAG Synthesizer | `IDAGSynthesizer.resolve_dependencies()` |
| 3 | DAG Synthesizer | Map nodes to tools | D8 Service Mesh | `D8.tool_registry.lookup()` |
| 4 | DAG Synthesizer | Return topology | Planner Agent | `IDAGSynthesizer.optimize_topology()` |
| 5 | Planner Agent | Validate plan | Critic Feedback | `ICriticFeedbackLoop.evaluate_plan_quality()` |
| 6 | Planner Agent | Publish plan | F1 Unified API | `F1.submit_plan(plan.dag_topology)` via `IPlannerAgent.publish_plan()` |
| 7 | F1 Runtime | Submit to execution | D8 Mesh → Workers | F1 `schedule_and_execute()` |
| 8 | F1 Runtime | Emit trace events | F4 Observability | F4 `TraceCollector` via EventBus `runtime.trace.span` |
| 9 | F4 Observability | Store metrics | Telemetry Aggregator | F4 `ITelemetryAggregator.ingest_event()` |
| 10 | F4 Telemetry | Publish summary | Planner Critic | EventBus `runtime.telemetry.summary` |
| 11 | D9 Feedback | Intake execution data | Feedback Loop | D9 `FeedbackLoop.ingest_execution()` |
| 12 | D9 Feedback | Emit adaptation signal | Planner Agent | EventBus `runtime.planning.adapt` |
| 13 | Planner Agent | Adapt plan | Critic Feedback | `ICriticFeedbackLoop.suggest_corrections()` |
| 14 | Planner Agent | Distribute tasks | Swarm Coordinator | `ISwarmCoordinator.distribute_tasks()` |

---

## 2. Correlation ID Strategy

The `plan_trace_id` flows through all layers to guarantee end-to-end traceability:

| Layer | Field Name | Format | Propagation Mechanism |
|-------|-----------|--------|----------------------|
| **G1 Planner** | `plan_trace_id` | `plan:{plan_id}:v{version}` | Carried in ExecutionPlan dataclass |
| **F1 Unified API** | `trace_id` | `exec:{execution_id}` | Set by `F1.submit()` from plan_trace_id |
| **D8 Service Mesh** | `trace_id` | Forwarded from F1 | EventBus envelope header |
| **F3 Resource Scheduler** | `trace_id` | Forwarded from D8 | RPC header / EventBus |
| **F4 TraceCollector** | `trace_id` | Forwarded from F1 | `ITraceCollector.start_span(trace_id=plan_trace_id)` |
| **D9 Feedback Loop** | `execution_id` | `{execution_id}` | Extracted from EventBus event |

### Correlation Resolution

1. `IPlannerAgent.synthesize_plan()` generates `plan_trace_id = "plan:{uuid}:v1"`
2. `IPlannerAgent.publish_plan()` passes `plan_trace_id` to F1 as `trace_id`
3. F1 creates `execution_id` and maps it to `plan_trace_id` in its metadata
4. F4 `TraceCollector.start_span()` uses the F1 `trace_id` (= plan_trace_id)
5. D9 receives the `execution_id` and can reconstruct the chain via F4 query
6. On adaptation, the new plan carries `plan_trace_id = "plan:{uuid}:v{version+1}"` with `adapted_from = original_plan_id`

---

## 3. EventBus Topic Map

| Topic | Payload Schema | Publisher | Subscriber(s) | Retention |
|-------|---------------|-----------|---------------|-----------|
| `runtime.planning.intent` | ExecutionPlan (DRAFT) | User/Agent | Planner Agent | 5 min |
| `runtime.planning.approved` | ExecutionPlan (APPROVED) | Planner Agent | F1 Runtime | 5 min |
| `runtime.planning.adapt` | Dict{execution_id, feedback} | D9 Feedback Loop | Planner Agent | 5 min |
| `runtime.planning.critic` | CriticVerdict | ICriticFeedbackLoop | Planner Agent | 5 min |
| `runtime.planning.swarm` | SwarmNegotiation | ISwarmCoordinator | Agents | 5 min |
| `runtime.planning.alert` | AlertPayload | Planner Agent | IAlertRouter (F4) | 1 hour |

---

## 4. Hook Points for Planning Events

| Hook | Trigger | Event Published | Consumer |
|------|---------|---------------|----------|
| `PlanningDriftDetected` | DAG synthesis with same context_hash produces different topology | `runtime.planning.alert` with severity CRITICAL | IAlertRouter → halt execution |
| `CriticRejection` | Plan rejected by critic (score < 0.7) | `runtime.planning.alert` with severity WARNING | IAlertRouter → log + operator notify |
| `SwarmDeadlock` | Swarm negotiation stuck in PENDING for > 30s | `runtime.planning.alert` with severity CRITICAL | IAlertRouter → escalate |
| `AdaptationThrottled` | Adaptation blocked by cooldown or max_adaptations | `runtime.planning.alert` with severity INFO | IAlertRouter → log |
| `DeterminismViolation` | Replay produces mismatched plan | `runtime.planning.alert` with severity CRITICAL | IAlertRouter → halt + diagnostics |

### Alert Suppression

| Suppression Key | Cooldown | Scope |
|-----------------|----------|-------|
| `planning_drift:{intent_hash}` | 600s | Per-intent drift detection |
| `critic_rejection:{plan_id}` | 300s | Per-plan rejection |
| `swarm_deadlock:{negotiation_id}` | 120s | Per-negotiation deadlock |
| `adapt_throttled:{plan_trace_id}` | 60s | Per-trace adaptation throttle |

---

## 5. Acceptance Criteria for Integration

### 5.1 Latency Budgets

| Operation | Budget | Measured From |
|-----------|--------|--------------|
| `synthesize_plan()` | ≤ 500ms | Intent received → DAG topology ready |
| `resolve_dependencies()` | ≤ 200ms | Call → dependency edges |
| `map_to_tools()` | ≤ 200ms | Call → tool mappings |
| `evaluate_plan_quality()` | ≤ 300ms | Call → CriticVerdict |
| `publish_plan()` | ≤ 100ms | Call → execution_id from F1 |
| `adapt_plan()` | ≤ 500ms | Feedback received → new plan version |
| `distribute_tasks()` | ≤ 200ms | Call → agent assignments |

### 5.2 Idempotency Guarantees

| Operation | Idempotent? | Strategy |
|-----------|-------------|----------|
| `synthesize_plan(intent, context)` | Yes (RULE 1) | Same (intent, context_hash) → return cached plan |
| `validate_plan(plan_id)` | Yes (RULE 5) | Same plan_id → same validation result |
| `publish_plan(plan_id)` | Yes | Same plan_id → return existing execution_id |
| `adapt_plan(execution_id, feedback)` | Yes (RULE 5) | Same (execution_id, feedback_hash) → return existing adaptation |

### 5.3 Determinism Thresholds

| Property | Guarantee | Verification |
|----------|-----------|-------------|
| Same intent → same DAG | 100% | Topology cache hit |
| Same context → same tool mapping | 100% | Deterministic lookup |
| Same weights → same confidence | ±0.01 | Float rounding tolerance |
| Same feedback → same adaptation | 100% | Deterministic adaptation path |

### 5.4 Backpressure Handling

| Condition | Action |
|-----------|--------|
| Critic queue > 100 pending evaluations | Drop lowest-priority evaluations |
| Swarm negotiation backlog > 50 | Reject new negotiations until cleared |
| Adaptation requests > 10/min | Throttle — apply cooldown |
| Plan publication rate > 100/min | Buffer and batch-publish |

---

## 6. Interaction with Existing Subsystems

| Subsystem | Interaction | Contract |
|-----------|-------------|----------|
| **F1 Unified API** | `publish_plan()` calls `F1.submit(dag_topology)` | F1 returns `execution_id` mapped to `plan_trace_id` |
| **D8 Service Mesh** | `IDAGSynthesizer.map_to_tools()` queries D8 `ServiceRegistry.lookup()` | D8 returns tool specs with `required_capabilities` |
| **D9 Feedback Loop** | `IPlannerAgent.adapt_plan()` subscribes to `runtime.planning.adapt` | D9 emits adaptation signal with confidence ≥ 0.8 |
| **F4 Observability** | `ICriticFeedbackLoop.evaluate_plan_quality()` consumes F4 `AggregationSummary` | F4 publishes summary to `runtime.telemetry.summary` |
| **CompositionRoot** | All G1 components wired via CompositionRoot (LAW 13) | Planner Agent receives F1, D8, D9, F4 as constructor dependencies |
