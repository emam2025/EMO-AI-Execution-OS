# R4 Cognitive OS — Architecture Manifest

**Directive**: EXEC-DIRECTIVE-R4-PREP-001
**Stage**: R4 — Cognitive OS Foundation & Strategic Protocol Design
**Isolation**: ZERO R1/R2/R3 MUTATIONS | PROTOCOL-ONLY | ISOLATION-BOUND
**Date**: 2026-05-30

---

## 1. Architecture Overview

R4 Cognitive OS is a protocol-only layer that defines **how strategic plans are created**, **how failures are reflected upon**, and **how plans are self-evaluated** before execution. It has zero runtime, zero storage, and zero execution logic.

```
User Goal ──► IStrategicPlanner ──► PlanHypothesis (DAG Blueprint)
                                          │
                                    ┌─────┴──────┐
                                    ▼            ▼
                            ISelfEvaluator   IReflectionEngine
                            (validate +      (analyse failures
                             assess risk)     from R2/R3)
                                    │            │
                                    └─────┬──────┘
                                          ▼
                                  Corrected Plan
                                          │
                                          ▼
                                   R1 Runtime
                                  (execution)
```

## 2. Isolation Matrix

| Layer | Accessible from R4? | Direction | Constraint |
|-------|---------------------|-----------|------------|
| R1 Runtime OS | ❌ | — | No access; completely sealed |
| R2 Memory OS | ⏳ Read-only (future) | R4 → R2 | Via bridge contract only |
| R3 Skill OS | ⏳ Read-only (future) | R4 → R3 | Skill failure data for reflection |
| Core ExecutionEngine | ❌ | — | Never imported or referenced |
| R4 Cognitive Store | ⏳ Future | — | Reserved for implementation phase |

## 3. Cognitive Data Flow

```
             ┌──────────────────────┐
             │   Strategic Goal     │
             │  (user-defined)      │
             └──────────┬───────────┘
                        │
                        ▼
             ┌──────────────────────┐
             │  IStrategicPlanner   │
             │  decompose_goal()    │
             └──────────┬───────────┘
                        │
                        ▼
             ┌──────────────────────┐
             │   PlanHypothesis     │
             │  (DAG blueprint)     │
             └──────────┬───────────┘
                        │
              ┌─────────┴─────────┐
              ▼                   ▼
   ┌──────────────────┐  ┌──────────────────┐
   │  ISelfEvaluator  │  │ IReflectionEngine│
   │ validate_plan()  │  │ analyze_failure() │
   │ assess_risk()    │  │ generate_corr()   │
   └────────┬─────────┘  └────────┬─────────┘
            │                     │
            └─────────┬───────────┘
                      ▼
           ┌──────────────────┐
           │  Validated Plan  │
           │  + Risk Score    │
           └──────────────────┘
```

## 4. Guard OS Boundaries

| Boundary | Rule | Enforcement |
|----------|------|-------------|
| **Cognition plans, does not execute** | R4 never calls ExecutionEngine or any runtime | Protocol-only design; zero import of runtime modules |
| **Evaluation is deterministic** | `validate_plan_integrity()` must return same result for same input | Protocol contract ensures purity |
| **Correction requires validator_signature** | `PlanHypothesis.validator_signature` for audit trail | Model-level field |
| **No direct R2/R3 access** | R4 reads R2/R3 only through future bridge contracts | Interface contract; no direct imports |
| **Tenant isolation** | Every model enforces tenant_id | `StrategicGoal.__post_init__()` raises on empty tenant_id |
| **Risk score mandatory** | Every RiskAssessment must have overall_score in [0,1] | `RiskAssessment.__post_init__()` enforces |

## 5. Protocol Contracts

### IStrategicPlanner

```python
decompose_goal(goal, tenant_id, constraints)    → PlanHypothesis
evaluate_feasibility(plan, tenant_id)            → bool
list_active_plans(tenant_id, project_id, limit)  → List[str]
```

### IReflectionEngine

```python
analyze_failure(trace_id, outcome, tenant_id)    → ReflectionEntry
generate_correction(reflection, tenant_id)        → Dict[str, Any]
list_reflections(tenant_id, source_skill_id, limit) → List[str]
```

### ISelfEvaluator

```python
validate_plan_integrity(plan, tenant_id)          → ValidationResult
assess_risk(plan, tenant_id)                      → RiskScore
list_evaluations(tenant_id, plan_id, limit)       → List[str]
```

## 6. Data Models

| Model | Key Fields | Invariants |
|-------|-----------|------------|
| `StrategicGoal` | goal_id, tenant_id, description, priority, status | tenant_id mandatory, status enum |
| `PlanHypothesis` | hypothesis_id, tenant_id, goal_id, dag_blueprint, confidence_score, validator_signature | tenant_id mandatory, confidence ∈ [0,1] |
| `ReflectionEntry` | reflection_id, tenant_id, source_trace_id, analysis, severity, strategy_update | tenant_id mandatory, severity enum |
| `RiskAssessment` | assessment_id, tenant_id, plan_id, risk_factors[], overall_score | tenant_id mandatory, score ∈ [0,1] |

## 7. Canon Compliance

| Law | Requirement | R4 Implementation |
|-----|-------------|-------------------|
| LAW-6 | tenant_id mandatory at every public method | All 3 protocols and all 4 models enforce tenant_id |
| LAW-8 | No cross-tenant data leakage | Every model scopes by tenant_id |
| LAW-11 | Tenant isolation at query layer | `list_*` methods filter by tenant_id |
| LAW-14 | Protocol boundaries | R4 is protocol-only; no execution or storage logic |

## 8. Plan Propagation Chain

```
Cognitive Planner (goal) ──► PlanHypothesis (DAG blueprint)
                                    │
                                    ▼
                         ISelfEvaluator.assess_risk()
                                    │
                                    ▼
                         RiskAssessment (score + mitigation)
                                    │
                                    ▼
                         R1 Runtime (future — execution)
```

## 9. File Map

```
/releases/cognitive-os/
├── core/
│   ├── interfaces/cognitive/
│   │   ├── IStrategicPlanner.py
│   │   ├── IReflectionEngine.py
│   │   └── ISelfEvaluator.py
│   ├── models/
│   │   └── cognitive.py
│   └── cognitive/                # Empty (reserved)
├── desktop/
│   └── emo-cognitive-dashboard/src/App.tsx
├── docs/
│   └── R4_COGNITIVE_ARCHITECTURE_MANIFEST.md
├── tests/
│   └── test_r4_isolation_and_contracts.py
├── artifacts/
│   ├── RELEASE_MANIFEST_R4_DRAFT.json
│   └── execution_log.txt
└── certificates/
    └── R4_PREP_CERTIFICATE.json
```

## 10. Stop Conditions

| Condition | Action |
|-----------|--------|
| Import from `releases.runtime_os`, `releases.memory_os`, or `releases.skill_os` | 🛑 STOP + REVERT |
| Any execution/storage logic in protocol files | 🛑 STOP + REVERT |
| tenant_id or risk_score not mandatory | 🛑 STOP + ADD GUARD |
| Any mutation to R1/R2/R3 archives | 🛑 STOP + AUDIT |
