# Phase D9 — Integration Blueprint

> Design document mapping the Runtime Intelligence Feedback Loop across
> ExecutionEngine → EventBus → FeedbackLoopSubscriber → CodeGraphUpdater → MetricsStore.
>
> Ref: DEVELOPER.md §5.3 (Self-Tuning), §5.4 (Guardrails)
> Ref: DEVELOPER.md §17.9 (CodeGraph purity — MUST NOT depend on runtime)
> Ref: Canon LAW 5, 7, 11, 14-16

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                       Multi-Agent + Tool Layer                          │
│  (DAG Execution, Tool Dispatching, Worker Pool)                         │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │ emits
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          IEventBus (Phase 3.5)                          │
│                                                                          │
│  runtime.execution.completed     runtime.execution.failed               │
│  runtime.execution.timed_out     runtime.execution.cancelled             │
│  runtime.checkpoint.saved        runtime.lease.expired                  │
└──────┬──────────────────────────────────────────────────────┬───────────┘
       │ subscribe("runtime.execution.*")                      │ publish("runtime.drift.*")
       ▼                                                       ▲
┌──────────────────────────────────────────────────────────────┴──────────┐
│                    IRuntimeFeedbackLoopSubscriber                         │
│                                                                          │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────────┐  │
│  │ TraceAccumulator │───▶│ ImpactAnalyzer  │───▶│ AdjustmentEngine    │  │
│  │ (capture_trace)  │    │ (analyze_impact)│    │ (apply_adjustment)  │  │
│  └─────────────────┘    └─────────────────┘    └──────────┬──────────┘  │
│                                                            │            │
└────────────────────────────────────────────────────────────┼────────────┘
                                                             │
                    ┌────────────────────────────────────────┼──────────┐
                    │                    IDynamicCouplingAdjuster       │
                    │                                        │          │
                    │  ┌──────────────┐   ┌──────────────┐   │          │
                    │  │ ScoreComputer│   │ThresholdGuard │   │          │
                    │  └──────┬───────┘   └──────┬────────┘   │          │
                    │         │                  │            │          │
                    │         └──────┬───────────┘            │          │
                    │                ▼                        │          │
                    │       ┌────────────────┐                │          │
                    │       │ FileCommitter   │               │          │
                    │       │ (atomic swap)   │               │          │
                    │       └────────┬───────┘                │          │
                    └────────────────┼────────────────────────┘          │
                                     │                                   │
                                     ▼                                   │
                    ┌──────────────────────────────────────────────┐     │
                    │           CodeGraph (PURE — §17.9)           │     │
                    │                                              │     │
                    │  metadata.json  edges.json  nodes.json        │     │
                    │        ▲                                      │     │
                    │        │ file watch                            │     │
                    │  ┌─────┴──────────┐                          │     │
                    │  │ DriftDetector  │                          │     │
                    │  └────────────────┘                          │     │
                    └──────────────────────────────────────────────┘     │
                                                                         │
                    ┌──────────────────────────────────────────────┐     │
                    │              MetricsStore                     │     │
                    │  (execution_metrics, drift_events, alerts)    │     │
                    └──────────────────────────────────────────────┘     │
                                                                         │
                    ┌──────────────────────────────────────────────┐     │
                    │              HotspotDetector                  │     │
                    │  (execution frequency, failure patterns,      │     │
                    │   decomposition suggestions)                  │     │
                    └──────────────────────────────────────────────┘     │
                                                                         │
                    ┌──────────────────────────────────────────────┐     │
                    │         RuntimeArchitectureAlert              │     │
                    │  (severity classification, enforcement gate)  │◀────┘
                    └──────────────────────┬───────────────────────┘
                                           │
                                           ▼
                    ┌──────────────────────────────────────────────┐
                    │              Enforcement Gate                  │
                    │  (emo-guard CI, pre-commit hook, EventBus)     │
                    └──────────────────────────────────────────────┘
```

---

## 2. Flow: EventBus → FeedbackLoop → CodeGraph

### 2.1 End-to-End Flow

```
1. Node execution completes
   └→ ExecutionEngine emits "runtime.execution.completed"

2. FeedbackLoopSubscriber receives event
   └→ IRuntimeFeedbackLoop.capture_trace(event)
   └→ Converts to TraceEvent → stores in ring buffer (window_size=50)

3. ImpactAnalyzer processes window
   └→ IRuntimeFeedbackLoop.analyze_impact(node_id)
   └→ Computes: success_rate, avg_duration, coupling_delta

4. AdjustmentEngine evaluates
   └→ IRuntimeFeedbackLoop.apply_weight_adjustment(signal)
   └→ Guards: confidence >= 0.75, sample_size >= 20, boundaries [0.2, 0.8]

5. If adjustment passes guards:
   └→ IDynamicCouplingAdjuster.compute_new_scores(traces, baseline)
   └→ IDynamicCouplingAdjuster.validate_threshold(new_score, old_score)
   └→ IDynamicCouplingAdjuster.commit_boundary_update(node_id, new_score)
   └→ Atomic file swap: metadata.json.tmp → metadata.json

6. CodeGraph DriftDetector (pure, file-watch)
   └→ Detects metadata.json change
   └→ Computes hash(metadata.json)
   └→ If hash != baseline_hash: emits ArchitectureDriftDetected

7. If drift detected:
   └→ IHotspotDetector.suggest_decomposition(node_id)
   └→ IRuntimeArchitectureAlert.evaluate_violation(...)
   └→ If severity >= CRITICAL: trigger_enforcement_gate()
   └→ EventBus.publish("runtime.drift.detected")
```

### 2.2 Correlation ID Flow

```
trace_id = generate_uuid()          ← generated at ExecutionEngine
    │
    ▼
EventBus payload: { trace_id, ... }  ← propagated in every event
    │
    ▼
FeedbackLoop.capture_trace()
    └→ TraceEvent.trace_id = trace_id
    │
    ▼
ImpactAnalyzer → WeightUpdateSignal
    └→ signal.reason += f" (trace: {trace_id})"
    │
    ▼
DriftAlert → evaluated by ArchAlert
    └→ alert.law_refs = [violated laws]
    └→ alert.timestamp = now
    │
    ▼
MetricsStore → stored with trace_id as secondary index
```

**LAW 12 enforcement**: Every event, trace, signal, alert carries `trace_id`.

---

## 3. Event Hooks

### 3.1 Subscription: FeedbackLoop → EventBus

```
IRuntimeFeedbackLoop subscribes to:
  subscribe("runtime.execution.completed")  → capture_trace(TraceEvent)
  subscribe("runtime.execution.failed")     → capture_trace(TraceEvent)
  subscribe("runtime.execution.timed_out")  → capture_trace(TraceEvent)
  subscribe("runtime.execution.cancelled")  → capture_trace(TraceEvent)
```

### 3.2 Publication: EventBus ← FeedbackLoop

```
IRuntimeFeedbackLoop publishes:
  publish("runtime.drift.detected", alert.payload)       — on any drift
  publish("runtime.drift.critical", alert.payload)       — if severity = CRITICAL
  publish("runtime.drift.blocking", alert.payload)       — if severity = BLOCKING

IDynamicCouplingAdjuster publishes via FeedbackLoop:
  publish("runtime.feedback.adjusted", signal.payload)   — weight updated
  publish("runtime.feedback.rejected", signal.payload)   — guard blocked
  publish("runtime.feedback.deferred", signal.payload)   — insufficient confidence

IHotspotDetector publishes:
  publish("runtime.hotspot.detected", profile.payload)   — hotspot identified
  publish("runtime.hotspot.decomposition", profile)      — decomposition suggested
```

### 3.3 Hook Points in FeedbackLoop

```
capture_trace()
  → emit("runtime.feedback.trace_captured")     after storage

analyze_impact()
  → emit("runtime.feedback.analysis_complete")  after window processed

apply_weight_adjustment()
  → emit("runtime.feedback.adjustment_pending") on guard entry
  → emit("runtime.feedback.adjusted")           on commit
  → emit("runtime.feedback.rejected")           on guard fail

publish_drift_alert()
  → emit("runtime.drift.detected")              on publication
  → emit("runtime.drift.critical")              if severity >= CRITICAL
  → emit("runtime.drift.blocking")              if severity = BLOCKING
```

---

## 4. Acceptance Criteria

### 4.1 Latency Budgets

| Operation | Target | Warning | Critical | Notes |
|-----------|--------|---------|----------|-------|
| `capture_trace()` | < 1ms | > 5ms | > 10ms | EventBus subscription + ring buffer write |
| `analyze_impact()` | < 10ms | > 20ms | > 50ms | Rolling window computation (50 traces) |
| `apply_weight_adjustment()` | < 5ms | > 10ms | > 25ms | Guard evaluation only |
| `commit_boundary_update()` | < 50ms | > 100ms | > 200ms | Atomic file swap + checksum |
| `publish_drift_alert()` | < 2ms | > 5ms | > 10ms | EventBus publish |
| Full loop (capture → commit) | < 100ms | > 200ms | > 500ms | End-to-end worst case |

### 4.2 Idempotency Guarantees

| Operation | Idempotent? | Mechanism |
|-----------|-------------|-----------|
| `capture_trace()` | ✅ | Duplicate trace_id → no-op |
| `analyze_impact()` | ✅ | Same traces + same baseline → same result |
| `apply_weight_adjustment()` | ✅ | Same signal_id → no-op (record already applied) |
| `commit_boundary_update()` | ✅ | Atomic file swap: same content → same hash → no-op |
| `publish_drift_alert()` | ✅ | Same alert_id → EventBus dedup |

### 4.3 Backpressure Handling

| Scenario | Strategy | Implementation |
|----------|----------|---------------|
| EventBus flood (>1000 events/sec) | SAMPLE | Configurable sampling rate (default: 1:1, degrade to 1:10) |
| Ring buffer full | DROP_OLDEST | Circular buffer, oldest trace overwritten |
| Filesystem contention | RETRY | Retry atomic swap up to 3 times with 100ms backoff |
| CodeGraph file locked | DEFER | Defer update, retry on next analyze cycle |
| Alert flood | RATE_LIMIT | Max 6 alerts per hour per node |

### 4.4 §17.9 CodeGraph Purity Enforcement

```
✅ CodeGraph metadata.json is written by IDynamicCouplingAdjuster (external)
✅ CodeGraph.drift.py reads metadata.json through filesystem (passive watcher)
✅ No CodeGraph class imports or instantiates any runtime component
✅ No FeedbackLoop class imports or instantiates any CodeGraph class
✅ Communication is exclusively through filesystem (metadata.json) and EventBus

❌ FORBIDDEN: from core.codegraph.drift import DriftDetector in feedback_loop.py
❌ FORBIDDEN: from core.feedback import FeedbackLoop in codegraph/drift.py

Verify:
def test_codegraph_runtime_independence():
    """§17.9: CodeGraph MUST NOT depend on runtime modules."""
    codegraph_sources = Path("core/codegraph").rglob("*.py")
    for src in codegraph_sources:
        content = src.read_text()
        assert "from core.runtime" not in content, f"{src} imports runtime"
        assert "from core.feedback" not in content, f"{src} imports feedback"
        assert "from core.execution" not in content, f"{src} imports execution"
```

### 4.5 LAW 11 Enforcement (No Global State)

```
✅ FeedbackLoop holds trace data in local ring buffer (per-instance)
✅ RateLimiter state is per-scope, not global
✅ Weight adjustments are scoped to component (w_graph, w_sem)
✅ DriftAlert carries trace_id for correlation
✅ MetricsStore is the only centralized store (append-only)

Verify:
def test_no_global_runtime_state():
    """LAW 11: No module may directly own global runtime state."""
    for line in feedback_loop_source.split("\n"):
        assert "_global_" not in line, f"Global state detected: {line}"
```

### 4.6 Weight Update Sampling Policy

| Window Size | Use Case | Refresh Rate |
|-------------|----------|-------------|
| 10 traces | Hot (real-time) failure detection | Every 10 traces |
| 50 traces | Standard weight adjustment | Every 10 traces (sliding) |
| 200 traces | Trend analysis | Every 50 traces |
| 1000 traces | Baseline drift detection | Every 200 traces |

The FeedbackLoop maintains separate ring buffers per window size.
Large windows serve as drift baseline comparison for smaller windows.
