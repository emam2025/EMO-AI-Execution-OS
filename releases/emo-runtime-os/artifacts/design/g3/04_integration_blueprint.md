# Phase G3 — Integration Blueprint: Optimizer × G1 × G2 × F3
Date: 2026-05-22
Status: DESIGN ONLY
Ref: Canon LAW 2 (Interface Authority), LAW 7, LAW 11, LAW 14-16
Ref: Canon RULE 1, RULE 3, RULE 5
Ref: DEVELOPER.md §15.2, §15.9, §15.10, §15.13

---

## 1. Flow Map

```
  G1 Planner                     G3 Optimizer                    G2 Critic / F3 Scheduler
  ══════════                     ════════════                    ════════════════════════

  G1.synthesize() ──plan──►  IOptimizerAgent.evaluate_plan()
                               │
                               ▼
                          IDAGTopologyOptimizer
                          ICostOptimizer
                          IResourceBalancer
                               │
                               ▼
                          IOptimizerAgent.propose_optimization()
                               │
                               ├──► G2 Critic (optional critique via EventBus)
                               │
                               ▼
                          IOptimizerAgent.apply_topology_patch()
                               │
                               ├──► G1.adapt_plan() (with optimiser patches)
                               │
                               ▼
                          IOptimizerAgent.publish_report()
                               │
                               ├──► F3 ResourceScheduler (updated load profile)
                               ├──► EventBus (optimizer.* topics)
                               └──► F4 TelemetryAggregator (record span)
```

## 2. Correlation ID Strategy

A single `optimizer_trace_id` propagates across all layers:

| Layer | Generated At | Format | Propagation |
|-------|-------------|--------|-------------|
| G3 Optimizer | `IOptimizerAgent.evaluate_plan()` | `opt_{plan_id}_{sha256(metrics)[:12]}` | Included in every OptimizationProposal, TopologyPatch, OptimizerReport |
| G1 Planner | G3 → G1 via `adapt_plan()` | Passed as `metadata["optimizer_trace_id"]` | Stored in ExecutionPlan.metadata |
| G2 Critic | G3 → G2 via EventBus | Passed as event payload field | Recorded in DiagnosisReport metadata |
| F3 Scheduler | G3 → F3 via EventBus | Passed as event payload field | Recorded in ResourceAllocation metadata |
| F4 Observability | G3 → F4 via `publish_report()` | Passed as span attribute | Recorded in TraceSpan.metadata |

### Back-Tracing

```python
# F4 TraceCollector → locate all spans with optimizer_trace_id
f4_query: trace_collector.query_traces(optimizer_trace_id="opt_p1_a1b2c3")

# G1 PlannerAgent → locate plan + optimization history
g1_query: planner_agent.plans["p1"].metadata.get("optimizer_trace_id")

# G2 CriticAgent → locate critic assessments triggered by optimisation
g2_query: critic_agent.trace_correlator.resolve_plan_id(optimizer_trace_id)

# F3 ResourceScheduler → locate load reports
f3_query: resource_scheduler.history.filter(lambda h: h.metadata.get("optimizer_trace_id") == id)
```

---

## 3. Hook Points for EventBus Emissions

### `optimizer.plan.evaluated`
Emitted when COST_LOAD_ANALYSIS reaches APPROVE / PROPOSE_PATCH / REJECT.

```python
payload = {
    "plan_id": plan_id,
    "optimizer_trace_id": optimizer_trace_id,
    "evaluation_score": score,
    "cost_efficiency": cost_eff,
    "load_balance_score": load_score,
    "state": "approve" | "propose_patch" | "reject",
}
event_bus.publish("optimizer.plan.evaluated", payload)
```

### `optimizer.patch.proposed`
Emitted when PROPOSE_PATCH state is entered.

```python
payload = {
    "plan_id": plan_id,
    "optimizer_trace_id": optimizer_trace_id,
    "proposals": [p.to_dict() for p in proposals],
}
event_bus.publish("optimizer.patch.proposed", payload)
```

### `optimizer.patch.rejected`
Emitted when Safe Patch Guard fails.

```python
payload = {
    "plan_id": plan_id,
    "optimizer_trace_id": optimizer_trace_id,
    "reason": guard_result.reason,
    "failed_guard": guard_result.failed_guard,
}
event_bus.publish("optimizer.patch.rejected", payload)
```

### `optimizer.drift.detected`
Emitted when Deterministic Optimization Guard detects hash mismatch.

```python
payload = {
    "plan_id": plan_id,
    "optimizer_trace_id": optimizer_trace_id,
    "expected_hash": expected_hash,
    "actual_hash": actual_hash,
}
event_bus.publish("optimizer.drift.detected", payload)
```

### `optimizer.budget.exceeded`
Emitted when any cost/latency budget is exceeded.

```python
payload = {
    "plan_id": plan_id,
    "optimizer_trace_id": optimizer_trace_id,
    "exceeded_fields": ["cpu_seconds", "api_calls"],
    "overage_percent": 15.0,
    "recommended_actions": ["prune_node_n3", "replace_tool_search"],
}
event_bus.publish("optimizer.budget.exceeded", payload)
```

### `optimizer.balancer.recommending`
Emitted when IResourceBalancer detects a hotspot or suggests reassignment.

```python
payload = {
    "plan_id": plan_id,
    "optimizer_trace_id": optimizer_trace_id,
    "hotspot_worker": "worker_3",
    "overloaded_resource": "cpu",
    "current_load": 0.92,
    "recommended_actions": ["move_node_n5_to_worker_1"],
}
event_bus.publish("optimizer.balancer.recommending", payload)
```

---

## 4. LAW 7 & LAW 11 Integration

| Law | Integration Point |
|-----|-------------------|
| LAW 7 (Failure Propagation) | Optimizer detects cost overruns and load imbalances as failure signals. `optimizer.budget.exceeded` events feed into F4 FailureMatrix for circuit-breaker analysis. |
| LAW 11 (No Global State) | All optimizer state is per-instance. No global `active_optimizations` dict. Each `evaluate_plan()` call uses fresh state from the passed `metrics` and `cost_budget` dicts. |
| LAW 14 (Resource Governance) | Topology patches MUST pass `validate_dag_integrity` before application. DAG structural integrity is the resource governance mechanism. |
| LAW 15 (Cost Limits) | `enforce_budget()` is the final gate before patch application. Hard limits are absolute; soft limits trigger warnings. |
| LAW 16 (Fair Scheduling) | `validate_fairness()` ensures worker load is within `fairness_threshold` of the mean. Violations block patch application. |

---

## 5. Acceptance Criteria for Integration

| Criterion | Threshold | Verification |
|-----------|-----------|--------------|
| Latency budget (evaluate → report) | ≤ 800ms per optimisation cycle | F4 trace span duration |
| Idempotency | Same plan + metrics + budget → same proposals | Deterministic replay test × 10 runs |
| Determinism | 100% identical proposals across 10 runs | optimizer_cache_key match |
| Safe Patch | 100% of applied patches pass all 3 guards | GuardResult assertion |
| Rollback safety | 100% of patches carry rollback_plan | OptimizationProposal assertion |
| Backpressure | ≥ 50 evaluations/sec without data loss | F4 BackpressureSampler ensures CRITICAL spans never dropped |
| Fairness | Worker load variance ≤ 0.2 × mean | validate_fairness() assertion |
| EventBus delivery | At-least-once per topic | D8 FailureMatrix confirms receipt |
