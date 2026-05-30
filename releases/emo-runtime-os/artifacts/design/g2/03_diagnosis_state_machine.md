# Phase G2 — Diagnosis State Machine & Correction Guards
Date: 2026-05-22
Status: DESIGN ONLY
Ref: Canon LAW 7 (Failure Propagation), LAW 8 (Governance), RULE 3 (Feedback-Adaptation)
Ref: DEVELOPER.md §15.2, §15.9

---

## 1. State Map

```
                        ┌──────────────────────────────────────┐
                        │         FAILURE_OBSERVED             │
                        │  (F4 trace arrives at ICriticAgent)  │
                        └────────────┬─────────────────────────┘
                                     │
                                     ▼
                        ┌──────────────────────────────┐
                        │      PATTERN_MATCH            │
                        │  (IFailureDiagnoser matches   │
                        │   against FailureSignatures)  │
                        └────────────┬──────────────────┘
                                     │
                                     ▼
                        ┌──────────────────────────────────┐
                        │      ROOT_CAUSE_ISOLATE          │
                        │  (isolate_root_cause +           │
                        │   rate_confidence)               │
                        └───┬──────────┬──────────┬────────┘
                            │          │          │
                   ┌────────┘    ┌─────┘    ┌────┘
                   ▼             ▼          ▼
          ┌────────────┐  ┌──────────┐  ┌────────┐
          │  CORRECT   │  │ REJECT   │  │ NO_OP  │
          │ (fix plan) │  │ (reject  │  │ (no    │
          │            │  │  plan)   │  │ action)│
          └────────────┘  └──────────┘  └────────┘
                   │
                   ▼
          ┌────────────────┐
          │   ESCALATE     │
          │ (if severity   │
          │  == CRITICAL)  │
          └────────────────┘
```

### Transition Table

| From | To | Guard | Description |
|------|----|-------|-------------|
| FAILURE_OBSERVED | PATTERN_MATCH | `guard_has_trace` | Trace must contain error_type + stack_pattern |
| PATTERN_MATCH | ROOT_CAUSE_ISOLATE | `guard_match_found` | match_confidence >= 0.3 |
| PATTERN_MATCH | NO_OP | `guard_no_match` | match_confidence < 0.3 |
| ROOT_CAUSE_ISOLATE | CORRECT | `guard_correction_allowed` | See §2 |
| ROOT_CAUSE_ISOLATE | REJECT | `guard_reject` | Plan has fatal flaw OR confidence < 0.5 |
| ROOT_CAUSE_ISOLATE | NO_OP | `guard_insufficient_evidence` | confidence < 0.75 AND severity < WARNING |
| CORRECT | ESCALATE | `guard_escalate` | severity == CRITICAL OR risk > 0.8 |
| CORRECT | FAILURE_OBSERVED | `guard_retry` | Correction applied; await next trace |
| REJECT | (terminal) | — | Plan rejected; notify G1 |
| NO_OP | FAILURE_OBSERVED | — | Return to monitoring |
| ESCALATE | (terminal) | — | Emit EscalationTriggered to EventBus |

---

## 2. Correction Guards (RULE 3)

A correction SHALL be allowed **only when all three** preconditions are met:

| Guard | Condition | Rationale |
|-------|-----------|-----------|
| `diagnosis_signal_count >= 1` | At least one diagnosis signal must exist | Prevents corrections without evidence (LAW 8) |
| `confidence >= 0.75` | Root cause confidence must be ≥ 0.75 | Prevents speculative corrections (RULE 3) |
| `rollback_safe == true` | Correction must be reversible | Ensures recovery safety (RULE 5) |

### Guard Violation Responses

| Failed Guard | Response |
|-------------|----------|
| signal_count < 1 | Set plan status to PENDING_REVIEW; escalate if severity >= ERROR |
| confidence < 0.75 | Increase diagnostic sampling; log DiagnosisLowConfidence event |
| rollback_safe == false | Reject correction; emit CorrectionRejected(safety_violation) |

### Guard Evaluation Flow (Pseudocode)

```
def evaluate_correction_guards(diagnosis: DiagnosisReport) -> CorrectionGuardResult:
    signals = len(diagnosis.evidence_chain)
    confidence = diagnosis.confidence_score
    rollback = correction_payload.rollback_safe

    if signals < 1:
        return CorrectionGuardResult(False, "No diagnosis signals", INSUFFICIENT_DIAGNOSIS_SIGNALS)
    if confidence < 0.75:
        return CorrectionGuardResult(False, f"Confidence {confidence} < 0.75", BELOW_CONFIDENCE_THRESHOLD)
    if not rollback:
        return CorrectionGuardResult(False, "Correction not rollback-safe", NOT_ROLLBACK_SAFE)

    return CorrectionGuardResult(True, "All guards passed")
```

---

## 3. Deterministic Review Guard (RULE 1)

The Critic Agent MUST produce the **same diagnosis** for the same
`(trace, plan, context)` input triple, regardless of execution time
or system load.

### Mechanism

```
review_cache_key = sha256(
    normalize(trace) +
    normalize(plan) +
    normalize(context)
).hexdigest()

# If cache_key exists and diagnosis confidence >= 0.75 → replay cached result
# If cache_key exists and confidence < 0.75 → re-diagnose with expanded context
# If cache_key does not exist → diagnose and store
```

### Determinism Guarantees

| Layer | Determinism Strategy |
|-------|---------------------|
| Error pattern matching | Regex-based; no random state |
| Root cause isolation | Evidence-chain sorted by timestamp; first-match wins |
| Confidence scoring | Pure function of evidence_chain length + severity weight |
| Correction proposal | Topology adjustment is deterministic function of (plan, correction_type) |
| Runtime review | Latency threshold comparison; no stochastic sampling |

### Non-Deterministic Drift Prevention

If the Deterministic Review Guard detects that:
- The same review_cache_key produces different ReviewSignal
- OR the same correction_cache_key produces different CorrectionPayload

Then:
1. Emit `DiagnosisDriftDetected(trace_id, plan_id, expected_hash, actual_hash)` to EventBus
2. Set review state to REJECT
3. Log determinism violation for F4 Observability

---

## 4. State Machine Parameter Summary

| Parameter | Default | Min | Max |
|-----------|---------|-----|-----|
| confidence_threshold | 0.75 | 0.5 | 1.0 |
| match_confidence_min | 0.3 | 0.0 | 1.0 |
| max_corrections_per_plan | 3 | 1 | 10 |
| escalation_severity | CRITICAL | — | — |
| retry_cooldown_ms | 5000 | 1000 | 30000 |
| determinism_cache_ttl_s | 3600 | 60 | 86400 |

---

## 5. EventBus Topics

| Topic | Emitted When |
|-------|-------------|
| `critic.diagnosis.started` | FAILURE_OBSERVED → PATTERN_MATCH |
| `critic.diagnosis.completed` | ROOT_CAUSE_ISOLATE → CORRECT/REJECT/NO_OP |
| `critic.correction.proposed` | CORRECT state entered |
| `critic.correction.rejected` | Correction guard fails |
| `critic.runtime.reviewed` | IRuntimeReviewer completes |
| `critic.drift.detected` | Determinism hash mismatch |
| `critic.escalation.triggered` | ESCALATE state entered |
