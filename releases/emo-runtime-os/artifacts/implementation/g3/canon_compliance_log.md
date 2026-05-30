# G3 Optimizer Agent — Canon Compliance Log

## Laws & Rules

| Law/Rule | Compliance | Evidence |
|----------|-----------|----------|
| LAW 12 | ✅ Traceability | OptimizerTraceCorrelator propagates optimizer_trace_id G3→G1→F3→G2 |
| LAW 14 | ✅ Topology integrity | DAGTopologyOptimizer.validate_dag_integrity() enforces acyclic + valid refs |
| LAW 15 | ✅ Cost budgets | CostOptimizer.estimate_execution_cost(), CostBudget soft/hard limits |
| LAW 16 | ✅ Fairness | ResourceBalancer.validate_fairness(), detect_hotspots() |
| RULE 1 | ✅ Determinism | compute_determinism_hash SHA-256, cached review via determinism_cache |
| RULE 3 | ✅ Safe Patch Guards | evaluate_safe_patch_guards() enforces 3 preconditions |
| RULE 5 | ✅ Defer/Retry | guard_defer (confidence < 0.6), guard_retry (10s cooldown) |

## Files

| File | Laws/Rules |
|------|-----------|
| core/runtime/optimizer/optimizer_agent.py | LAW 14, 15, 16, RULE 1, 3, 5 |
| core/runtime/optimizer/dag_topology_optimizer.py | LAW 14, RULE 1 |
| core/runtime/optimizer/cost_optimizer.py | LAW 15 |
| core/runtime/optimizer/resource_balancer.py | LAW 16 |
| core/runtime/optimizer/optimization_state_machine.py | LAW 14, 15, RULE 1, 3, 5 |
| core/runtime/optimizer/trace_correlator.py | LAW 12 |
| core/runtime/models/optimizer_models.py | LAW 11, 14, 15, 16 |
| core/composition/root.py | LAW 13 |
