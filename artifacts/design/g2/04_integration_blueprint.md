# Phase G2 — Integration Blueprint: Critic × G1 × D9 × F4
Date: 2026-05-22
Status: DESIGN ONLY
Ref: Canon LAW 2 (Interface Authority), LAW 7, LAW 8, LAW 12, LAW 20-22
Ref: DEVELOPER.md §15.2, §15.9, §15.13

---

## 1. Flow Map

```
  F4 Observability                  Critic Agent                    G1 Planner
  ═══════════════                  ══════════════                  ══════════
  TraceCollector ──Trace──►  ICriticAgent.diagnose_failure()
                               │
                               ▼
                          IFailureDiagnoser
                               │
                               ▼
                          IPlanCorrectionEngine ──CorrectionPayload──► G1.adapt_plan()
                               │
                               ▼
                          IRuntimeReviewer ──ReviewSignal──► G1.evaluate()
                               │
                               ▼
                          ICriticAgent.publish_assessment()
                               │
                               ├──► D9 FeedbackLoop.record_signal()
                               ├──► EventBus (critic.* topics)
                               └──► F4 TelemetryAggregator (record span)
```

## 2. Correlation ID Strategy

A single `critic_trace_id` propagates across all layers:

| Layer | Generated At | Format | Propagation |
|-------|-------------|--------|-------------|
| Critic Agent | `ICriticAgent.diagnose_failure()` | `critic_{plan_id}_{sha256(trace)[:12]}` | Included in every DiagnosisReport, CorrectionPayload, RuntimeReviewSnapshot |
| G1 Planner | Critic → G1 via `adapt_plan()` | Passed as `metadata["critic_trace_id"]` | Stored in ExecutionPlan.metadata |
| D9 Feedback | Critic → D9 via `record_signal()` | Passed as `signal.metadata["critic_trace_id"]` | Recorded in ArchitectureAlert metadata |
| F4 Observability | Critic → F4 via `publish_assessment()` | Passed as span attribute | Recorded in TraceSpan.metadata |

### Back-Tracing

```python
# F4 TraceCollector → locate all spans with critic_trace_id
f4_query: trace_collector.query_traces(critic_trace_id="critic_p1_a1b2c3")

# G1 PlannerAgent → locate plan + adaptation history
g1_query: planner_agent.plans["p1"].metadata.get("critic_trace_id")

# D9 FeedbackLoop → locate feedback signals
d9_query: feedback_loop.signals.filter(lambda s: s.metadata.get("critic_trace_id") == id)
```

---

## 3. Hook Points for EventBus Emissions

### `critic.diagnosis.completed`
Emitted when state machine reaches CORRECT / REJECT / NO_OP.

```python
payload = {
    "plan_id": report.plan_id,
    "critic_trace_id": report.critic_trace_id,
    "severity": report.severity_level,
    "confidence": report.confidence_score,
    "state": "correct" | "reject" | "no_op",
}
event_bus.publish("critic.diagnosis.completed", payload)
```

### `critic.correction.rejected`
Emitted when any correction guard fails.

```python
payload = {
    "plan_id": plan_id,
    "critic_trace_id": critic_trace_id,
    "reason": guard_result.reason,
    "failed_guard": guard_result.failed_guard,
}
event_bus.publish("critic.correction.rejected", payload)
```

### `critic.drift.detected`
Emitted when Deterministic Review Guard detects hash mismatch.

```python
payload = {
    "plan_id": plan_id,
    "critic_trace_id": critic_trace_id,
    "expected_hash": expected_hash,
    "actual_hash": actual_hash,
    "context_snapshot": context,
}
event_bus.publish("critic.drift.detected", payload)
```

### `critic.review.timeout`
Emitted when runtime review exceeds latency budget.

```python
payload = {
    "plan_ids": plan_ids,
    "critic_trace_id": critic_trace_id,
    "max_latency_ms": observed_ms,
    "threshold_ms": threshold_ms,
}
event_bus.publish("critic.review.timeout", payload)
```

### `critic.escalation.triggered`
Emitted when ESCALATE state is entered.

```python
payload = {
    "plan_id": plan_id,
    "critic_trace_id": critic_trace_id,
    "reason": "confidence < 0.5 AND severity == CRITICAL",
    "diagnosis": report,
}
event_bus.publish("critic.escalation.triggered", payload)
```

---

## 4. LAW 20-22 Failure Propagation Integration

| Law | Integration Point |
|-----|-------------------|
| LAW 20 (EventBus) | All critic events emit to EventBus topics. FailureMatrix subscribes to `critic.diagnosis.completed` and `critic.escalation.triggered` for circuit-breaker logic. |
| LAW 21 (Error Types) | Critic diagnoses map to F4 error types. `DiagnosisReport.severity_level` maps to `TraceSpan.status` for F4 ingestion. |
| LAW 22 (Failure Recovery) | Critic correction proposals are the recovery path. `CorrectionPayload.rollback_safe` determines if recovery is reversible. |

---

## 5. Acceptance Criteria for Integration

| Criterion | Threshold | Verification |
|-----------|-----------|--------------|
| Latency budget (diagnose → publish) | ≤ 500ms per diagnosis | F4 trace span duration |
| Idempotency | Same trace + plan + context → same diagnosis | Deterministic replay test × 10 runs |
| Determinism | 100% identical diagnosis across 10 runs | review_cache_key match |
| Backpressure | ≥ 100 diagnoses/sec without data loss | F4 BackpressureSampler ensures CRITICAL spans never dropped |
| EventBus delivery | At-least-once per topic | D8 FailureMatrix confirms receipt |
| Rollback safety | 100% of corrections with risk > 0.5 must be rollback_safe | CorrectionPayload assertion |
