# Phase G3 — Optimizer Agent: State Machine & Safe Patch Guards
Date: 2026-05-22
Status: DESIGN ONLY
Ref: Canon LAW 8 (Governance), LAW 14 (Resource Governance), LAW 15 (Cost Limits), LAW 16 (Fair Scheduling)
Ref: Canon RULE 1 (Determinism), RULE 3 (Feedback-Adaptation), RULE 5 (Recovery)
Ref: DEVELOPER.md §15.2, §15.9, §15.10

---

## 1. State Map

```
                         ┌──────────────────────────────────────┐
                         │          PLAN_RECEIVED               │
                         │  (G1 plan + F3 metrics arrive)       │
                         └────────────┬─────────────────────────┘
                                      │
                                      ▼
                         ┌──────────────────────────────┐
                         │       TOPOLOGY_EVAL           │
                         │  (IDAGTopologyOptimizer       │
                         │   analyses DAG structure)     │
                         └────────────┬──────────────────┘
                                      │
                                      ▼
                         ┌──────────────────────────────────┐
                         │     COST_LOAD_ANALYSIS           │
                         │  (ICostOptimizer +               │
                         │   IResourceBalancer)             │
                         └───┬──────────┬──────────┬────────┘
                             │          │          │
                    ┌────────┘    ┌─────┘    ┌────┘
                    ▼             ▼          ▼
           ┌────────────┐  ┌──────────┐  ┌────────┐
           │APPROVE     │  │PROPOSE   │  │ REJECT │
           │(no patch   │  │PATCH     │  │ (plan  │
           │ needed)    │  │(apply    │  │  has   │
           │            │  │ patch)   │  │ flaws) │
           └────────────┘  └──────────┘  └────────┘
                                │
                                ▼
                       ┌────────────────┐
                       │   DEFER        │
                       │ (wait for      │
                       │  better        │
                       │  conditions)   │
                       └────────────────┘
```

### Transition Table

| From | To | Guard | Description |
|------|----|-------|-------------|
| PLAN_RECEIVED | TOPOLOGY_EVAL | `guard_has_plan` | Plan must contain nodes + dag_topology |
| TOPOLOGY_EVAL | COST_LOAD_ANALYSIS | `guard_dag_integrity` | DAG integrity check passes |
| TOPOLOGY_EVAL | REJECT | `guard_dag_invalid` | DAG has structural flaws (cycles, orphans) |
| COST_LOAD_ANALYSIS | APPROVE | `guard_no_optimization_needed` | Cost/latency within 5% of optimal |
| COST_LOAD_ANALYSIS | PROPOSE_PATCH | `guard_safe_patch` | See §2 |
| COST_LOAD_ANALYSIS | REJECT | `guard_reject` | Budget exceeded OR load imbalance critical |
| PROPOSE_PATCH | DEFER | `guard_defer` | Confidence < 0.6 OR rollback_plan draft |
| PROPOSE_PATCH | COST_LOAD_ANALYSIS | `guard_re_evaluate` | Patch applied; re-evaluate |
| DEFER | COST_LOAD_ANALYSIS | `guard_retry` | Retry cooldown elapsed |
| APPROVE | (terminal) | — | Plan approved; notify G1 |
| REJECT | (terminal) | — | Plan rejected; notify G1 |

---

## 2. Safe Patch Guards (RULE 3, LAW 14)

A topology patch SHALL be allowed **only when**:

| Guard | Condition | Rationale |
|-------|-----------|-----------|
| `cost_reduction >= 5%` OR `latency_improvement >= 10%` | Measurable improvement required | Prevents churn without benefit (RULE 3) |
| `rollback_plan != None` | Patch must be reversible | Ensures recovery safety (RULE 5) |
| `dag_integrity_check == true` | DAG remains valid after patch | Prevents structural corruption (LAW 14) |

### Guard Violation Responses

| Failed Guard | Response |
|-------------|----------|
| cost_reduction < 5% AND latency_improvement < 10% | Set state to DEFER; emit `OptimizerPatchInsufficientBenefit` |
| rollback_plan == None | Reject patch; emit `OptimizerPatchMissingRollback` |
| dag_integrity_check == false | Reject patch; emit `OptimizerPatchIntegrityFailed`; escalate severity to ERROR |

### Guard Evaluation Flow (Pseudocode)

```
def evaluate_safe_patch_guards(proposal: OptimizationProposal) -> SafePatchGuardResult:
    cost_ok = proposal.estimated_cost_delta_pct <= -5.0
    latency_ok = proposal.latency_impact_pct <= -10.0
    has_rollback = proposal.rollback_plan is not None
    integrity = proposal.dag_integrity_check

    if not (cost_ok or latency_ok):
        return SafePatchGuardResult(False, "Insufficient improvement", INSUFFICIENT_COST_REDUCTION,
                                    cost_reduction_pct=proposal.estimated_cost_delta_pct)
    if not has_rollback:
        return SafePatchGuardResult(False, "Missing rollback plan", MISSING_ROLLBACK_PLAN)
    if not integrity:
        return SafePatchGuardResult(False, "DAG integrity check failed", DAG_INTEGRITY_FAILED)

    return SafePatchGuardResult(True, "All guards passed")
```

---

## 3. Deterministic Optimization Guard (RULE 1)

The Optimizer MUST produce the **same proposals** for the same
`(plan, metrics, cost_budget)` input triple, regardless of execution
time or system load.

### Mechanism

```
optimizer_cache_key = sha256(
    normalize(plan) +
    normalize(metrics) +
    normalize(cost_budget)
).hexdigest()

# If cache_key exists and confidence >= 0.7 → replay cached proposals
# If cache_key exists and confidence < 0.7 → re-optimize with expanded analysis
# If cache_key does not exist → optimize and store
```

### Determinism Guarantees

| Layer | Determinism Strategy |
|-------|---------------------|
| Topology analysis | Sorted node/edge iteration; no random state |
| Cost estimation | Pure function of node tool_name + baseline_costs map |
| Load distribution | Snapshot sorted by worker_id; deterministic computation |
| Patch generation | Greedy algorithm with deterministic tie-breaking (lexicographic) |
| Budget enforcement | Threshold comparison; no stochastic sampling |

### Non-Deterministic Drift Prevention

If the Deterministic Optimization Guard detects that:
- The same optimizer_cache_key produces different proposals
- OR the same patch_cache_key produces different topology

Then:
1. Emit `OptimizationDriftDetected(plan_id, optimizer_trace_id, expected_hash, actual_hash)` to EventBus
2. Set state to REJECT
3. Log determinism violation for F4 Observability

---

## 4. State Machine Parameter Summary

| Parameter | Default | Min | Max |
|-----------|---------|-----|-----|
| cost_reduction_threshold_pct | 5.0 | 1.0 | 50.0 |
| latency_improvement_threshold_pct | 10.0 | 1.0 | 80.0 |
| min_confidence_for_patch | 0.6 | 0.3 | 1.0 |
| retry_cooldown_ms | 10000 | 5000 | 60000 |
| max_patches_per_plan | 3 | 1 | 10 |
| determinism_cache_ttl_s | 3600 | 60 | 86400 |
| fairness_threshold | 0.2 | 0.05 | 0.5 |

---

## 5. EventBus Topics

| Topic | Emitted When |
|-------|-------------|
| `optimizer.plan.evaluated` | COST_LOAD_ANALYSIS → APPROVE/PROPOSE_PATCH/REJECT |
| `optimizer.patch.proposed` | PROPOSE_PATCH state entered |
| `optimizer.patch.applied` | Patch applied and re-evaluated |
| `optimizer.patch.rejected` | Safe Patch Guard fails |
| `optimizer.budget.exceeded` | Budget enforcement fails |
| `optimizer.drift.detected` | Determinism hash mismatch |
| `optimizer.balancer.recommending` | Hotspot detected / reassignment suggested |
