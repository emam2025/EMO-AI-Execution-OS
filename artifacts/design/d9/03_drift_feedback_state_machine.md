# Phase D9 — Drift Feedback State Machine

> Design document for the Runtime Intelligence Feedback Loop's weight update
> and drift detection state machine.
>
> Ref: DEVELOPER.md §5.3 (Self-Tuning), §5.4 (Guardrails)
> Ref: DEVELOPER.md §17.9 (CodeGraph purity)
> Ref: Canon LAW 5, 7, 11, 14-16

---

## 1. State Machine Overview

```
                        ┌──────────────────────────────────┐
                        │                                  │
                        ▼                                  │
                    ┌───────┐                              │
        EventBus    │ IDLE  │                              │
      ────────────▶│       │                              │
                    └───┬───┘                              │
                        │ capture_trace()                   │
                        ▼                                  │
                    ┌──────────────┐                       │
                    │TRACE_CAPTURED│                       │
                    └──────┬───────┘                       │
                           │ analyze_impact()              │
                           ▼                               │
                    ┌──────────────────┐                   │
                    │METRIC_AGGREGATED │                   │
                    └──────┬───────────┘                   │
                           │ threshold_check()             │
                           ▼                               │
                    ┌──────────────────┐                   │
              ┌────│ THRESHOLD_CHECKED │────┐              │
              │    └──────────────────┘    │              │
              │                           │              │
     within_threshold              exceeds_threshold
              │                           │              │
              ▼                           ▼              │
        ┌──────────┐             ┌───────────────┐       │
        │  NO_OP   │             │ALERT_TRIGGERED│       │
        └────┬─────┘             └───────┬───────┘       │
             │                          │                │
             │                          │ (if severity    │
             │                          │  >= CRITICAL)  │
             │                          ▼                │
             │                   ┌────────────┐          │
             │                   │ENFORCEMENT │          │
             │                   │   GATE     │          │
             │                   └───────┬────┘          │
             │                           │               │
             └───────────┬───────────────┘               │
                         ▼                               │
                   ┌──────────┐                          │
                   │ COOLDOWN │  (rate limit: 3/hr)      │
                   └────┬─────┘                          │
                        │ cooldown expires               │
                        ▼                               │
                    ┌───────┐                            │
                    │ IDLE  │────────────────────────────┘
                    └───────┘
```

### Weight Adjustment Sub-Machine

```
                   ┌──────────────────┐
                   │THRESHOLD_CHECKED │
                   └────────┬─────────┘
                            │
                   ┌────────┴────────┐
                   │                 │
            guard passes       guard fails
                   │                 │
                   ▼                 ▼
            ┌──────────┐    ┌──────────┐
            │WEIGHT    │    │ REJECTED │
            │ADJUSTED  │    └────┬─────┘
            └────┬─────┘        │
                 │              │
                 ▼              │
           ┌──────────┐        │
           │COMMITTED │        │
           └────┬─────┘        │
                │              │
                ▼              ▼
           ┌──────────┐  ┌──────────┐
           │ COOLDOWN │  │ COOLDOWN │
           └──────────┘  └──────────┘
```

---

## 2. State Transition Table

| From | To | Trigger | Guard Condition |
|------|----|---------|-----------------|
| IDLE | TRACE_CAPTURED | `capture_trace()` called | Event source is `runtime.execution.*` |
| TRACE_CAPTURED | METRIC_AGGREGATED | `analyze_impact()` completes | Window contains ≥1 valid trace |
| TRACE_CAPTURED | ERROR | analyze_impact() fails | Unparseable trace or missing fields |
| METRIC_AGGREGATED | THRESHOLD_CHECKED | `apply_weight_adjustment()` called | Metrics computed successfully |
| THRESHOLD_CHECKED | NO_OP | delta within threshold | `abs(delta) < 0.01` |
| THRESHOLD_CHECKED | WEIGHT_ADJUSTED | Guard conditions pass | confidence ≥ 0.75 AND sample_size ≥ 20 |
| THRESHOLD_CHECKED | REJECTED | Guard conditions fail | confidence < 0.75 OR sample_size < 20 |
| THRESHOLD_CHECKED | ALERT_TRIGGERED | delta > drift_warning_threshold | deviation_score > 0.05 |
| WEIGHT_ADJUSTED | COMMITTED | `commit_boundary_update()` succeeds | Atomic file swap succeeds |
| WEIGHT_ADJUSTED | ERROR | commit_boundary_update() fails | Filesystem error or checksum mismatch |
| COMMITTED | COOLDOWN | Cooldown timer starts | `max_adjustments_per_hour` = 3 |
| REJECTED | COOLDOWN | Cooldown timer starts | — |
| ALERT_TRIGGERED | ENFORCEMENT_GATE | severity ≥ CRITICAL | deviation > 0.1 OR risk > 0.8 |
| ALERT_TRIGGERED | COOLDOWN | severity < CRITICAL | deviation ≤ 0.1 |
| ENFORCEMENT_GATE | COOLDOWN | Enforcement action dispatched | EventBus event published |
| NO_OP | COOLDOWN | No action needed | — |
| COOLDOWN | IDLE | Cooldown expires | Time since last adjustment > 20 min |

---

## 3. Update Guards

### 3.1 Weight Adjustment Guards

| Guard | Condition | Rationale |
|-------|-----------|-----------|
| **Min Confidence** | `signal.confidence >= 0.75` | Prevent adjustments from noisy single samples |
| **Min Sample Size** | `signal.sample_size >= 20` | Statistical significance (LAW 7 — deterministic) |
| **SafeBoundary Min** | `new_weight >= 0.2` | Prevent w_graph/w_sem collapse (§5.4) |
| **SafeBoundary Max** | `new_weight <= 0.8` | Prevent w_graph/w_sem saturation (§5.4) |
| **Rate Limit** | `adjustments_last_hour < 3` | Prevent oscillation (LAW 11 — no global state) |
| **Coupling Threshold** | `new_coupling <= old_coupling + 0.1` | Prevent rapid coupling increase (LAW 14) |
| **Risk Threshold** | `new_risk <= old_risk + 10` | Prevent sudden risk spikes (LAW 16) |

### 3.2 Guard Implementation Contracts

```python
def guard_weight_adjustment(
    signal: WeightUpdateSignal,
    policy: FeedbackPolicy,
    current_weights: Dict[str, float],
    adjustment_count_last_hour: int,
) -> Tuple[bool, str]:
    """Evaluate all guard conditions for a weight adjustment.

    Returns (allowed: bool, reason: str).
    """
    if signal.confidence < policy.min_confidence:
        return False, f"confidence {signal.confidence:.2f} < {policy.min_confidence}"
    if signal.sample_size < policy.min_sample_size:
        return False, f"sample_size {signal.sample_size} < {policy.min_sample_size}"

    target = signal.target_component.value
    current = current_weights.get(target, 0.5)
    new_val = current + signal.delta

    if new_val < policy.weight_min or new_val > policy.weight_max:
        return False, f"new {target} = {new_val:.2f} outside [{policy.weight_min}, {policy.weight_max}]"

    if adjustment_count_last_hour >= policy.max_adjustments_per_hour:
        return False, f"rate limit: {adjustment_count_last_hour}/hr >= {policy.max_adjustments_per_hour}"

    return True, "all guards passed"


def guard_drift_alert(
    alert: DriftAlert,
    policy: FeedbackPolicy,
) -> DriftSeverity:
    """Classify drift severity based on deviation score."""
    if alert.deviation_score > policy.drift_block_threshold:
        return DriftSeverity.BLOCKING
    if alert.deviation_score > policy.drift_warning_threshold:
        return DriftSeverity.CRITICAL
    if alert.deviation_score > policy.drift_warning_threshold / 2:
        return DriftSeverity.WARNING
    return DriftSeverity.INFO
```

---

## 4. Feedback → CodeGraph Sync

### 4.1 Constraint: §17.9 — CodeGraph MUST NOT Depend on Runtime

```
✅ ALLOWED: FeedbackLoop writes to CodeGraph metadata.json via atomic file swap
✅ ALLOWED: FeedbackLoop reads CodeGraph metadata.json for baseline comparison
❌ FORBIDDEN: FeedbackLoop imports or instantiates any CodeGraph class
❌ FORBIDDEN: FeedbackLoop calls CodeGraphQueryEngine methods directly
❌ FORBIDDEN: CodeGraph reads from EventBus or runtime events
```

### 4.2 Sync Protocol

The `IDynamicCouplingAdjuster.commit_boundary_update()` follows a strict file protocol to avoid breaking §17.9:

```
1. FeedbackLoop accumulates TraceEvents over window
2. FeedbackLoop computes new coupling/risk scores  [in-memory only]
3. FeedbackLoop calls commit_boundary_update(metadata_path)
4. commit_boundary_update:
   a. Reads current metadata.json (baseline)
   b. Computes new scores dict
   c. Validates thresholds (guard)
   d. Writes to metadata.json.tmp
   e. Computes sha256(content) → checksum
   f. os.rename(.tmp → metadata.json)  [atomic swap]
   g. Returns success/failure
5. CodeGraph drift detector (core/codegraph/drift.py):
   a. Watches metadata.json for file changes (inotify/poll)
   b. Reads updated scores
   c. Fires ArchitectureDriftDetected event if thresholds exceeded
```

### 4.3 Determinism Guarantee (§17.6)

The sync protocol preserves CodeGraph's determinism guarantee:

| Operation | Deterministic? | Mechanism |
|-----------|---------------|-----------|
| Write metadata.json | ✅ | Atomic file swap prevents torn reads |
| Read metadata.json | ✅ | Checksum verifies integrity |
| Hash comparison | ✅ | SHA-256 on full content |
| Score computation | ✅ | Pure function of (baseline, traces) |
| File watch | ❌ (non-deterministic) | But read-only — no side effects |

### 4.4 Sync Matrix

| Step | Component | What Changes | How | Determinism |
|------|-----------|-------------|-----|-------------|
| 1 | EventBus | — | emits `runtime.execution.*` | Eventual |
| 2 | FeedbackLoop | in-memory aggregation | `analyze_impact()` | ✅ |
| 3 | CouplingAdjuster | in-memory scores | `compute_new_scores()` | ✅ |
| 4 | CouplingAdjuster | `metadata.json` fields | atomic file swap | ✅ |
| 5 | CodeGraph.drift | (reads metadata.json) | file poll + hash compare | ✅ |
| 6 | CodeGraph.drift | — | emits `ArchitectureDriftDetected` | Eventual |

---

## 5. Cooldown & Rate Limiting

| Policy | Value | Rationale |
|--------|-------|-----------|
| Max adjustments per hour | 3 | Prevent oscillation (LAW 11) |
| Cooldown period | 20 minutes | Stability window |
| Min time between alerts | 5 minutes | Reduce alert fatigue |
| Max alerts per hour per node | 6 | Proportional to adjustment rate |
| Cooldown reset on ERROR | Immediate | Allow recovery from transient errors |

### Rate Limit Enforcement

```python
class RateLimiter:
    """Tracks adjustment/alert frequency per scope per hour."""
    _adjustments: Dict[str, List[float]] = {}  # scope → [timestamps]
    _alerts: Dict[str, List[float]] = {}

    def can_adjust(self, scope: str, max_per_hour: int = 3) -> bool:
        now = time.time()
        recent = [t for t in self._adjustments.get(scope, []) if t > now - 3600]
        return len(recent) < max_per_hour

    def record_adjustment(self, scope: str) -> None:
        self._adjustments.setdefault(scope, []).append(time.time())

    def can_alert(self, node_id: str, max_per_hour: int = 6) -> bool:
        now = time.time()
        recent = [t for t in self._alerts.get(node_id, []) if t > now - 3600]
        return len(recent) < max_per_hour
```
