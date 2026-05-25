# Phase F4 — Telemetry Aggregation State Machine

**File:** `03_telemetry_aggregation_machine.md`  
**Ref:** Canon LAW 5 (Observability), LAW 12 (Traceability), RULE 1-5  
**Ref:** DEVELOPER.md §15.8, §15.13  

---

## 1. Purpose

The Telemetry Aggregation State Machine governs the lifecycle of a single telemetry event — from raw ingestion through buffering, windowed aggregation, and eventual persistence. It enforces:

- **Zero loss of CRITICAL spans** under backpressure (§15.13)
- **Deterministic aggregation** within each window (RULE 1)
- **Reversible buffering** — buffer preserved on flush failure (RULE 3)
- **Idempotent ingestion** — duplicate events within a window are merged (RULE 5)

---

## 2. State Machine Overview

```
                        ┌──────────────┐
                        │  RAW_EVENT   │
                        └──────┬───────┘
                               │ ingest_event()
                               ▼
                        ┌──────────────┐
                   ┌───▶│  VALIDATED   │◀────────────┐
                   │    └──────┬───────┘             │
                   │           │                     │
                   │           ▼                     │
                   │    ┌──────────────┐             │
                   │    │   BUFFERED   │             │
                   │    └──────┬───────┘             │
                   │           │ window boundary     │
                   │           ▼                     │
                   │    ┌──────────────┐             │
                   │    │ AGGREGATING  │             │
                   │    └──────┬───────┘             │
                   │           │ compute_metrics()   │
                   │           ▼                     │
                   │    ┌──────────────┐             │
                   │    │  COMPUTED    │─────────────┤─── publish_summary()
                   │    └──────┬───────┘             │
                   │           │ flush_window()       │
                   │           ▼                     │
                   │    ┌──────────────┐             │
                   │    │   FLUSHING   │─────────────┤─── on_failure → BUFFERED
                   │    └──────┬───────┘             │
                   │           │ on_success          │
                   │           ▼                     │
                   │    ┌──────────────┐             │
                   │    │  PERSISTED   │             │
                   │    └──────────────┘             │
                   │                                 │
                   └─────────────────────────────────┘
                         (next window starts here)
```

### States

| State | Meaning | Guards |
|-------|---------|--------|
| `RAW_EVENT` | Event received but not inspected | — |
| `VALIDATED` | Schema & mandatory fields checked | `validate_fields()` |
| `BUFFERED` | Stored in in-memory ring buffer | `buffer_capacity_check()` |
| `AGGREGATING` | Windowed aggregation in progress | `window_boundary_check()` |
| `COMPUTED` | Metrics computed, summary ready | — |
| `FLUSHING` | Emitting to persistent store | `flush_retry_guard()` |
| `PERSISTED` | Successfully written to store | — |

### Transitions

| From | To | Guard | Action |
|------|----|-------|--------|
| `RAW_EVENT` | `VALIDATED` | `validate_fields()` | Assign trace_id/span_id |
| `VALIDATED` | `BUFFERED` | `buffer_capacity_check()` | Append to ring buffer |
| `BUFFERED` | `AGGREGATING` | `window_boundary_check()` | Slice buffer slice |
| `AGGREGATING` | `COMPUTED` | — | `compute_metrics()` |
| `COMPUTED` | `FLUSHING` | — | `flush_window()` |
| `FLUSHING` | `PERSISTED` | — | Evict from buffer |
| `FLUSHING` | `BUFFERED` | `flush_retry_guard()` | Preserve buffer, schedule retry |
| `PERSISTED` | `BUFFERED` | — | Begin next window |

---

## 3. Field Validation Rules

Every event entering VALIDATED MUST pass these checks:

| Field | Rule | Violation Action |
|-------|------|------------------|
| `trace_id` | Non-empty, ≤ 64 chars | Drop event, log warning |
| `span_id` | Non-empty, ≤ 64 chars | Drop event, log warning |
| `event_type` | Member of `TelemetryEventType` | Reject, error counter |
| `payload` | Non-empty dict | Reject, error counter |
| `correlation_id` | Format `{trace_id}:{span_id}` | Auto-generate if missing |

---

## 4. Correlation Rules

How `trace_id` flows between subsystems (LAW 12):

| From Domain | To Domain | Propagation Mechanism | Header / Envelope Field |
|-------------|-----------|----------------------|------------------------|
| F1 Unified API | D8 Service Mesh | EventBus envelope | `trace_id`, `span_id` |
| D8 Service Mesh | F3 Resource Scheduler | EventBus routing key | `trace_id`, `parent_span_id` |
| F3 Resource Scheduler | Worker | RPC header | `trace_id`, `span_id` |
| Worker | F4 TraceCollector | Span end event | `trace_id`, `parent_id` |
| F4 TraceCollector | EventBus | Telemetry event | `trace_id`, `span_id` |
| EventBus | F4 TelemetryAggregator | Subscription | `trace_id`, `correlation_id` |
| EventBus | F4 Dashboard Provider | Query API | `execution_id` ↔ `trace_id` lookup |

### Correlation Key Resolution

1. **Inbound event** arrives with `trace_id` and `span_id` in envelope.
2. `ITraceCollector.start_span()` creates child with `parent_id = incoming span_id`.
3. `ITraceCollector.propagate_context()` serialises `(trace_id, span_id)` for next hop.
4. `ITelemetryAggregator.ingest_event()` indexes by `trace_id` for session-window partitioning.

### Cross-Domain Span Hierarchy

```
F1 API Span
 └─ D8 Mesh Span (parent = F1 span_id)
     └─ F3 Scheduler Span (parent = D8 span_id)
         ├─ Worker Span A (parent = F3 span_id)
         └─ Worker Span B (parent = F3 span_id)
```

---

## 5. Windowing Strategy

| Strategy | Key | Interval | Partition | Eviction |
|----------|-----|----------|-----------|----------|
| **Sliding Window (5s)** | `sliding:{timestamp_5s_bucket}` | 5 seconds | time-based | After compute + flush |
| **Tumbling Window (1m)** | `tumbling:{YYYYMMDDHHMM}` | 60 seconds | time-based | After compute + flush |
| **Session Window** | `session:{execution_id}` | Per execution | trace_id-based | After execution COMPLETED/FAILED |

### Adaptive Sampling

Under backpressure (buffer > 80% capacity):

| Span Priority | Action |
|--------------|--------|
| CRITICAL | Always ingested |
| WARNING | Ingested, latency-budget increased |
| INFO | 50% sample rate |
| DEBUG | Dropped with counter increment |

**Backpressure recovery:** When buffer drops below 40%, restore full sampling within 2 window cycles.

---

## 6. Validation & Acceptance Criteria

| Criterion | Standard | Verification |
|-----------|----------|------------|
| CRITICAL span loss | 0 (absolute) | Dedicated counter in AggregationSummary.dropped_count |
| Aggregation lag | ≤ 500ms per window | AggregationSummary.lag_ms |
| Duplicate ingestion | Merged, not double-counted | Metric count idempotency test |
| Flush retry | 3 attempts with exponential backoff | Retry counter in FLUSHING state |
| Session window eviction | After COMPLETED/FAILED | ExecutionTimelineEvent sequence must be complete |
