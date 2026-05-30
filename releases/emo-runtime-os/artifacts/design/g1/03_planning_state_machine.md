# Phase G1 — Planning State Machine & Adaptation Guards

**File:** `03_planning_state_machine.md`  
**Ref:** Canon LAW 1-8 (Core Determinism & Fairness), RULE 1-5  
**Ref:** DEVELOPER.md §15.2, §15.9  

---

## 1. Purpose

The Planning State Machine governs the lifecycle of a single `ExecutionPlan` — from intent ingestion through DAG synthesis, critic evaluation, approval, execution, and optional adaptation. It enforces:

- **Deterministic DAG synthesis** (RULE 1) — same intent + context → same topology
- **Guarded adaptation** (RULE 3) — no plan mutation without critic signal
- **Immutability of published plans** (RULE 2) — once published, plan is immutable
- **Idempotent validation** (RULE 5) — same plan_id → same validation result

---

## 2. State Machine Overview

```
                        ┌──────────────────┐
                        │  INTENT_RECEIVED │
                        └────────┬─────────┘
                                 │ synthesize_plan()
                                 ▼
                        ┌──────────────────┐
                        │  DAG_SYNTHESIS   │
                        └────────┬─────────┘
                                 │ IDAGSynthesizer
                                 ▼
                        ┌──────────────────┐
                        │  CRITIC_EVAL     │◀─────────────────────────────┐
                        └───┬──────┬───────┘                              │
                            │      │                                      │
                 ┌──────────┘      └──────────┐                           │
                 ▼                             ▼                           │
        ┌─────────────────┐        ┌─────────────────────┐                │
        │   APPROVED       │        │  CRITIC_REJECTED    │                │
        └────────┬─────────┘        └──────────┬──────────┘                │
                 │                             │                          │
                 ▼                             ▼                          │
        ┌─────────────────┐        ┌─────────────────────┐                │
        │   PUBLISHED      │        │  ESCALATED /        │                │
        │ (→ F1 Runtime)   │        │    HALTED           │                │
        └────────┬─────────┘        └─────────────────────┘                │
                 │                                                         │
         execution feedback                                                │
                 │                                                         │
                 ▼                                                         │
        ┌─────────────────┐                                               │
        │  COMPLETED /     │                                               │
        │    FAILED        │                                               │
        └──────────────────┘                                               │
                                                                           │
              ADAPT PATH (guarded):                                        │
        ┌──────────────────┐                                               │
        │  ACTIVE (in exec)│                                               │
        └────────┬─────────┘                                               │
                 │ D9 feedback arrives                                     │
                 ▼                                                         │
        ┌──────────────────┐   adaptation_guards_pass()                    │
        │  ADAPT_REQUESTED │───────────────────────────────────────────────┘
        └──────────────────┘   (re-enters CRITIC_EVAL → new plan version)
```

### States

| State | Meaning | Guards |
|-------|---------|--------|
| `INTENT_RECEIVED` | Raw intent accepted from user/agent | validate_intent() |
| `DAG_SYNTHESIS` | DAG being constructed from intent | deterministic_synthesis_guard() |
| `CRITIC_EVAL` | Critic evaluating plan quality | critic_eval_guard() |
| `APPROVED` | Plan passed critic, ready to publish | — |
| `CRITIC_REJECTED` | Plan failed critic threshold | — |
| `PUBLISHED` | Plan submitted to F1 Runtime | plan_immutable_guard() |
| `COMPLETED` | Execution finished successfully | — |
| `FAILED` | Execution finished with errors | — |
| `ACTIVE` | Plan is being executed | — |
| `ADAPT_REQUESTED` | D9 feedback triggered adaptation | adaptation_guards() |
| `ESCALATED` | Critical flaw — escalated to human/admin | — |
| `HALTED` | Plan halted by operator or critic | — |

### Transitions

| From | To | Guard | Action |
|------|----|-------|--------|
| `INTENT_RECEIVED` | `DAG_SYNTHESIS` | `validate_intent()` | Create plan_id, plan_trace_id |
| `DAG_SYNTHESIS` | `CRITIC_EVAL` | `deterministic_synthesis_guard()` | Store dag_topology |
| `CRITIC_EVAL` | `APPROVED` | `critic_eval_guard(threshold=0.7)` | Set confidence_score |
| `CRITIC_EVAL` | `CRITIC_REJECTED` | — | Log flaw_patterns |
| `CRITIC_EVAL` | `ESCALATED` | `escaped_guard(severity ≥ 0.9)` | Alert human operator |
| `APPROVED` | `PUBLISHED` | `plan_immutable_guard()` | Submit to F1, get execution_id |
| `PUBLISHED` | `COMPLETED` | — | Archive plan |
| `PUBLISHED` | `FAILED` | — | Trigger D9 feedback |
| `PUBLISHED` | `ACTIVE` | — | Execution in progress |
| `ACTIVE` | `ADAPT_REQUESTED` | `adaptation_guards()` | Freeze current plan |
| `ADAPT_REQUESTED` | `CRITIC_EVAL` | — | Create new plan version |
| `CRITIC_REJECTED` | `HALTED` | — | Notify operator |
| `CRITIC_REJECTED` | `DAG_SYNTHESIS` | `retry_guard(retry_count ≤ 3)` | Re-synthesise with feedback |

---

## 3. Guard Functions

### 3.1 validate_intent()

| Condition | Action |
|-----------|--------|
| Intent string is empty | Reject with "empty intent" |
| Intent exceeds 10,000 chars | Reject with "intent too long" |
| Context contains disallowed keys | Reject with "invalid context" |
| Otherwise | Allow transition |

### 3.2 deterministic_synthesis_guard()  (RULE 1)

| Condition | Action |
|-----------|--------|
| Same (intent, context_hash, weight_hash) as previous plan | Return cached topology |
| New (intent, context) | Synthesise deterministically |
| Context missing required fields (tool_registry, capability_map) | Reject with "incomplete context" |

### 3.3 critic_eval_guard()  (RULE 3)

| Condition | Action |
|-----------|--------|
| Overall score ≥ 0.7 | Allow → APPROVED |
| Overall score < 0.7 && severity < 0.9 | Allow → CRITIC_REJECTED |
| Overall score < 0.7 && severity ≥ 0.9 | Allow → ESCALATED |
| No critic assessments yet | Block — wait for ICriticFeedbackLoop.evaluate_plan_quality() |

### 3.4 plan_immutable_guard()  (RULE 2)

| Condition | Action |
|-----------|--------|
| Plan has been published before | Block — already immutable |
| Plan status is not APPROVED | Block — must be APPROVED first |
| All conditions pass | Allow, mark plan as immutable |

### 3.5 adaptation_guards()  (RULE 3, LAW 8)

**Adaptation is only permitted when ALL of the following pass:**

| Guard | Condition | Threshold |
|-------|-----------|-----------|
| `min_critic_signals` | Number of distinct CriticAssessments since last approval | ≥ 2 |
| `feedback_confidence` | D9 FeedbackLoop confidence score | ≥ 0.8 |
| `cooldown_elapsed` | Time since last adaptation | ≥ 60s |
| `not_halted` | Plan is not in HALTED or ESCALATED state | Must be ACTIVE |
| `max_adaptations` | Total adaptations for this plan_trace_id | ≤ 5 (RULE 3 bound) |

### 3.6 escape_guard()

| Condition | Action |
|-----------|--------|
| Any CriticAssessment.severity ≥ 0.9 | Allow → ESCALATED |
| More than 3 consecutive rejections | Allow → ESCALATED |
| Otherwise | Block |

### 3.7 retry_guard()

| Condition | Action |
|-----------|--------|
| retry_count < 3 | Allow → DAG_SYNTHESIS (with critic feedback) |
| retry_count ≥ 3 | Block → HALTED |

---

## 4. Deterministic Replay Guard

**Goal:** Same `(intent, context, weight_vector)` → same `ExecutionPlan` every time.

| Mechanism | Implementation |
|-----------|---------------|
| **Context hashing** | `hash(context) % 2^64` stored as `context_hash` in plan metadata |
| **Weight pinning** | F1 and D9 weights serialised as `weight_hash = hash(json.dumps(weights, sort_keys=True))` |
| **Topology cache** | `cache[(intent, context_hash, weight_hash)] = dag_topology` — deterministic lookup |
| **Seed locking** | For any stochastic steps, seed = `int(context_hash[:8], 16)` |
| **Version freeze** | Previously published plan versions are immutable — no retroactive changes |

**Violation detection:**

If a re-run with same `(intent, context_hash, weight_hash)` produces a different plan, the `IDAGSynthesizer` MUST raise a `DeterminismViolation` error and halt execution.

---

## 5. Validation & Acceptance Criteria

| Criterion | Standard | Verification |
|-----------|----------|------------|
| Deterministic synthesis | Same intent+context → same DAG | Topology cache hit test |
| Adaptation guards | ≥ 2 critic signals OR confidence ≥ 0.8 | Guard evaluation test |
| Max adaptations | ≤ 5 per plan_trace_id | Counter check in ADAPT_REQUESTED |
| Published plan immutability | No modification after PUBLISHED | State machine block test |
| Critic threshold | Score ≥ 0.7 for APPROVED | critic_eval_guard test |
| Escalation threshold | Severity ≥ 0.9 → ESCALATED | escape_guard test |
