# Phase F4 — Integration Blueprint: EventBus ↔ Telemetry Store

**File:** `04_integration_blueprint.md`  
**Ref:** Canon LAW 5 (Observability), LAW 12 (Traceability)  
**Ref:** DEVELOPER.md §15.8, §15.13  
**Ref:** `core/events/event_bus.py` (existing), `core/runtime/feedback/` (existing D9)

---

## 1. System Data Flow

```
  ┌─────────────────────────────────────────────────────────────────────┐
  │                        EventBus Topics                              │
  │  runtime.trace.span      runtime.telemetry.event                    │
  │  runtime.telemetry.alert runtime.telemetry.summary                  │
  │  runtime.worker.health    runtime.dag.execution                     │
  └──────┬──────────────────────┬───────────────────────────────────────┘
         │                      │
         ▼                      ▼
  ┌──────────────┐    ┌──────────────────────┐
  │TraceCollector │    │ TelemetryAggregator  │
  │ (span CRUD)   │    │ (windowed agg)       │
  └──────┬───────┘    └──────────┬───────────┘
         │                       │
         ▼                       ▼
  ┌──────────────────────────────────────────────────┐
  │              EventBus (internal)                   │
  │  Topics: runtime.telemetry.summary                 │
  │          runtime.telemetry.alert                    │
  └──────────────────────┬───────────────────────────┘
                         │
                         ▼
  ┌──────────────────────────────────────────────────┐
  │           Persistent Telemetry Store              │
  │  (spans, metrics, alerts, timelines)              │
  │  Read path: IDashboardDataProvider                │
  └──────────────────────┬───────────────────────────┘
                         │
                         ▼
  ┌──────────────────────────────────────────────────┐
  │           Runtime Dashboard / CLI                 │
  │  get_execution_timeline()                         │
  │  get_dag_visualization()                          │
  │  get_worker_topology()                            │
  │  get_failure_explorer()                           │
  └──────────────────────────────────────────────────┘
```

### Flow Steps

| Step | Source | Action | Destination | Protocol |
|------|--------|--------|-------------|----------|
| 1 | F1 / D8 / F3 | Emit span event | EventBus `runtime.trace.span` | `ITraceCollector.start_span()` |
| 2 | EventBus | Deliver to subscriber | TraceCollector | EventBus callback |
| 3 | F3 / Worker | Emit state transition | EventBus `runtime.telemetry.event` | `ITelemetryAggregator.ingest_event()` |
| 4 | TraceCollector | End span, publish | EventBus `runtime.trace.span` | `ITraceCollector.end_span()` |
| 5 | TelemetryAggregator | Window boundary → compute | — | `compute_metrics()` |
| 6 | TelemetryAggregator | Publish summary | EventBus `runtime.telemetry.summary` | `publish_summary()` |
| 7 | TelemetryAggregator | Persist aggregated data | Telemetry Store | `flush_window()` |
| 8 | Dashboard Provider | Query store | Telemetry Store | `get_execution_timeline()` etc. |

---

## 2. EventBus Topic Map

| Topic | Payload Schema | Publisher | Subscriber(s) | Retention |
|-------|---------------|-----------|---------------|-----------|
| `runtime.trace.span` | TraceSpan (JSON) | F1, D8, F3, Worker | TraceCollector | 5 min |
| `runtime.telemetry.event` | TelemetryEvent (JSON) | F3, D9, F2 | TelemetryAggregator | 5 min |
| `runtime.telemetry.summary` | AggregationSummary | TelemetryAggregator | Dashboard Provider, IAlertRouter | 1 hour |
| `runtime.telemetry.alert` | AlertPayload | IAlertRouter | Dashboard Provider, F2 (auto-scale) | 1 hour |
| `runtime.worker.health` | WorkerTopologySnapshot | F2 HealthSupervisor | Dashboard Provider | 5 min |
| `runtime.dag.execution` | ExecutionTimelineEvent | F1 Runtime | TelemetryAggregator | 5 min |

---

## 3. Backpressure & Adaptive Sampling

### 3.1 Trigger Conditions

The `ITelemetryAggregator` monitors its internal ring buffer:

| Condition | Action |
|-----------|--------|
| Buffer < 50% capacity | Full sampling, no throttling |
| Buffer ≥ 50% capacity | Enable DEBUG sampling at 50% |
| Buffer ≥ 75% capacity | Enable DEBUG + INFO sampling at 50% |
| Buffer ≥ 90% capacity | Drop DEBUG, sample INFO at 25%, preserve WARNING + CRITICAL |
| Buffer ≥ 95% capacity | Drop DEBUG + INFO, preserve WARNING + CRITICAL only |
| Buffer ≥ 100% capacity | **Fallback buffer** — spill to temp file, emit `TraceLoss` alert |

### 3.2 Fallback Buffer

```python
class FallbackBuffer:  # RULE-3
    """
    On-disk spillover when in-memory buffer is saturated.
    Only CRITICAL and WARNING spans are written to fallback.
    File format: JSONL, one event per line, gzip rotated at 10MB.
    Re-ingested when buffer drops below 50%.
    """
```

### 3.3 Adaptive Sampling Algorithm

```
adaptive_sampling(buffer_usage_pct: float) → SamplingConfig:
    if buffer_usage_pct < 0.50:
        return SamplingConfig(critical=1.0, warning=1.0, info=1.0, debug=0.50)
    if buffer_usage_pct < 0.75:
        return SamplingConfig(critical=1.0, warning=1.0, info=0.50, debug=0.25)
    if buffer_usage_pct < 0.90:
        return SamplingConfig(critical=1.0, warning=1.0, info=0.25, debug=0.0)
    if buffer_usage_pct < 0.95:
        return SamplingConfig(critical=1.0, warning=1.0, info=0.0, debug=0.0)
    # >= 0.95
    return SamplingConfig(critical=1.0, warning=0.0, info=0.0, debug=0.0)
```

---

## 4. Hook Points for Observability Events

| Hook | Trigger | Event Published | Consumer |
|------|---------|---------------|----------|
| `TraceLoss` | CRITICAL span dropped under backpressure | `runtime.telemetry.alert` with severity CRITICAL | IAlertRouter → log + dashboard |
| `AggregationLag` | `compute_metrics()` exceeds 500ms budget | `runtime.telemetry.alert` with severity WARNING | IAlertRouter → dashboard |
| `AlertStorm` | >10 alerts within 60s from same `suppression_key` | `runtime.telemetry.alert` with severity CRITICAL | IAlertRouter → cooldown escalation |
| `FlushFailure` | `flush_window()` fails after 3 retries | `runtime.telemetry.alert` with severity WARNING | IAlertRouter → fallback buffer |

### Alert Suppression Matrix

| Suppression Key | Cooldown | Scope |
|-----------------|----------|-------|
| `trace_loss:{domain}` | 300s | Per-domain trace loss |
| `agg_lag:{window_key}` | 60s | Per-window aggregation lag |
| `flush_failure:{store_id}` | 120s | Per-store flush failure |
| `alert_storm:{source_domain}` | 600s | Per-domain alert storm |

---

## 5. Acceptance Criteria for Integration

### 5.1 Latency Budgets

| Operation | Budget | Measured From |
|-----------|--------|--------------|
| `start_span()` | ≤ 1ms | Call to return |
| `end_span()` | ≤ 1ms | Call to return |
| `ingest_event()` | ≤ 5ms | EventBus receive → buffer append |
| `compute_metrics()` | ≤ 500ms | Window boundary → AggregationSummary ready |
| `flush_window()` | ≤ 200ms | Flush start → PERSISTED |
| `publish_summary()` | ≤ 50ms | Summary to EventBus published |
| Dashboard query (any) | ≤ 500ms | Request → response |

### 5.2 Idempotency Guarantees

| Operation | Idempotent? | Strategy |
|-----------|-------------|----------|
| `ingest_event()` | Yes | Same (event_type, trace_id, span_id) → merged |
| `flush_window()` | Yes | Same window_key → upsert aggregated data |
| `publish_summary()` | Yes | Same window_key → skip if already published |
| `route_alert()` | Yes | Same alert_id → return existing receipt |

### 5.3 Zero-Dropped Critical Spans

- **Design guarantee:** Backpressure algorithm never drops Severity.CRITICAL or SpanStatus.ERROR spans.
- **Safeguard:** Fallback buffer (file-based) activates at 100% buffer capacity.
- **Verification:** Dedicated counter `AggregationSummary.dropped_count` tracks all dropped spans. Any CRITICAL drop triggers `TraceLoss` alert.
- **Audit:** A continuous assertion (`span.status == CRITICAL → dropped_count[CRITICAL] == 0`) runs in test harness.

---

## 6. Interaction with Existing Subsystems

| Subsystem | Interaction | Contract |
|-----------|-------------|----------|
| **F1 Unified API** | `RuntimeStateMachine` emits state transitions as `ExecutionTimelineEvent` to EventBus | F1 publishes to `runtime.dag.execution` |
| **D8 Service Mesh** | Each D8 service propagates `trace_id` in outbound EventBus envelopes | D8 envelope header carries `trace_id`, `span_id` |
| **F2 Control Plane** | `HealthSupervisor` publishes `WorkerTopologySnapshot` to `runtime.worker.health` | F2 uses this for auto-scaling decisions |
| **F3 Resource Scheduler** | `SchedulingDecision` events include trace_id for correlation | F3 emits to `runtime.telemetry.event` |
| **D9 Feedback Loop** | `ArchitectureAlert` events feed into observability alerts | D9 publishes to `runtime.dag.execution` |
| **EventBus** | All F4 components subscribe to EventBus topics; no direct coupling | EventBus is the sole communication channel |
