"""Phase D9 — Trace & Feedback Event Models.

DESIGN ONLY — Dataclass and Enum definitions for the runtime
intelligence feedback loop event system.

Models:
  TraceEvent            — Single execution trace record
  WeightUpdateSignal    — Signal to adjust adaptive weights
  DriftAlert             — Architecture drift detection alert
  HotspotProfile        — Runtime hotspot identification
  FeedbackPolicy         — Rules governing weight update decisions

Ref: DEVELOPER.md §5.3 (Self-Tuning — boost thresholds)
Ref: DEVELOPER.md §17.9 (CodeGraph MUST NOT depend on runtime)
Ref: Canon LAW 5 (Observable), LAW 7 (Deterministic), LAW 11 (No global state)
Ref: Canon LAW 14-16 (CodeGraph-Driven Decomposition Laws)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# ═════════════════════════════════════════════════════════════════════
# 1. TraceEvent — Execution Trace Record
# ═════════════════════════════════════════════════════════════════════

class ExecutionOutcome(str, Enum):
    """Outcome of a single execution trace.

    Ref: §5.5 — Execution Memory (session lifecycle)
    """
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"


@dataclass
class TraceEvent:
    """Single execution trace record captured from EventBus.

    Every execution produces one or more TraceEvents that feed
    into the feedback loop for analysis.

    Fields:
        trace_id: Correlation ID across all layers (LAW 12).
        execution_id: Execution session identifier.
        node_id: DAG node identifier.
        tool_name: Name of the executed tool.
        outcome: Execution outcome (success/failed/timeout/etc.).
        duration_ms: Wall-clock duration in milliseconds.
        resource_consumed: Resource usage snapshot.
        feedback_signals: List of feedback signals emitted.
        timestamp: Unix timestamp of the event.

    Ref: §5.5 — Execution Memory
    Ref: Canon LAW 12 — All side effects MUST be traceable
    """
    trace_id: str = ""
    execution_id: str = ""
    node_id: str = ""
    tool_name: str = ""
    outcome: ExecutionOutcome = ExecutionOutcome.SUCCESS
    duration_ms: float = 0.0
    resource_consumed: Dict[str, float] = field(default_factory=dict)
    feedback_signals: List[str] = field(default_factory=list)
    timestamp: float = 0.0


# ═════════════════════════════════════════════════════════════════════
# 2. WeightUpdateSignal — Adaptive Weight Adjustment
# ═════════════════════════════════════════════════════════════════════

class WeightTarget(str, Enum):
    """Components that can receive weight adjustments.

    Ref: §5.3 — Self-Tuning (w_graph, w_sem)
    """
    W_GRAPH = "w_graph"
    W_SEM = "w_sem"
    COUPLING_THRESHOLD = "coupling_threshold"
    RISK_THRESHOLD = "risk_threshold"
    STRATEGY_WEIGHT = "strategy_weight"


@dataclass
class WeightUpdateSignal:
    """Signal to apply a dynamic weight adjustment.

    Guards (from §5.3 + §5.4 DriftMonitor):
      - confidence >= 0.75
      - sample_size >= 20
      - target weight stays within SafeWeightBoundaries [0.2, 0.8]

    Boost thresholds from §5.3:
      - success_rate >= 0.75 → delta = +0.10
      - success_rate >= 0.60 → delta = +0.05
      - success_rate < 0.40  → delta = -0.10
      - success_rate < 0.25  → delta = -0.15

    Fields:
        signal_id: Unique signal identifier.
        source_metric: The metric that triggered this signal (e.g. "success_rate").
        target_component: The weight component to adjust.
        delta: Proposed delta value (positive or negative).
        confidence: Confidence in the adjustment (0.0–1.0).
        sample_size: Number of samples backing this signal.
        success_rate: Current success rate in the analysis window.
        applied_at: Timestamp when the adjustment was applied.
        reason: Human-readable reason for the signal.

    Ref: §5.3 — Boost thresholds
    Ref: §5.4 — DriftMonitor, SafeWeightBoundaries
    """
    signal_id: str = ""
    source_metric: str = ""
    target_component: WeightTarget = WeightTarget.W_GRAPH
    delta: float = 0.0
    confidence: float = 0.0
    sample_size: int = 0
    success_rate: float = 0.0
    applied_at: float = 0.0
    reason: str = ""


# ═════════════════════════════════════════════════════════════════════
# 3. DriftAlert — Architecture Drift Detection
# ═════════════════════════════════════════════════════════════════════

@dataclass
class DriftAlert:
    """Alert raised when architecture drift is detected.

    Thresholds (from §3.4.5 emo-guard):
      - coupling delta > 0.05 → WARNING
      - coupling delta > 0.1  → BLOCK
      - risk score ↑ > 5      → WARNING
      - risk score ↑ > 10     → BLOCK
      - new boundary violation → BLOCK (any)
      - infrastructure leakage → BLOCK (any)

    Fields:
        alert_id: Unique alert identifier.
        baseline_hash: SHA-256 of the baseline CodeGraph metadata.
        current_hash: SHA-256 of the current state.
        deviation_score: Normalized deviation (0.0–1.0).
        violation_type: Type of architectural violation.
        severity: Classified severity level.
        source_module: Module where the violation originates.
        target_module: Module affected by the violation.
        action_required: Human-readable remediation.
        law_refs: List of Canon Laws violated.
        timestamp: Unix timestamp.

    Ref: §3.4.5 — emo-guard thresholds
    Ref: Canon LAW 14-16 — CodeGraph-Driven Decomposition Laws
    """
    alert_id: str = ""
    baseline_hash: str = ""
    current_hash: str = ""
    deviation_score: float = 0.0
    violation_type: str = ""
    severity: str = "warning"
    source_module: str = ""
    target_module: str = ""
    action_required: str = ""
    law_refs: List[str] = field(default_factory=list)
    timestamp: float = 0.0


# ═════════════════════════════════════════════════════════════════════
# 4. HotspotProfile — Runtime Hotspot Identification
# ═════════════════════════════════════════════════════════════════════

@dataclass
class HotspotProfile:
    """Runtime hotspot profile for a node or tool.

    LAW 16 enforcement: risk_score > 0.8 → decomposition required.

    Fields:
        node_id: Node/tool identifier.
        execution_count: Total executions in analysis window.
        failure_count: Total failures in analysis window.
        failure_rate: failure_count / execution_count.
        failure_patterns: Classified failure types and frequencies.
        avg_duration_ms: Average execution duration.
        coupling_score: Current coupling score from CodeGraph.
        coupling_increase: Delta from baseline coupling.
        risk_score: Current risk score.
        is_hotspot: True if this node exceeds hotspot criteria.
        recommendation: Suggested action (decompose, refactor, monitor, none).

    Ref: Canon LAW 16 — risk_score > 0.8 must decompose
    Ref: §5.3 — Failure pattern detection
    """
    node_id: str = ""
    execution_count: int = 0
    failure_count: int = 0
    failure_rate: float = 0.0
    failure_patterns: List[Dict[str, Any]] = field(default_factory=list)
    avg_duration_ms: float = 0.0
    coupling_score: float = 0.0
    coupling_increase: float = 0.0
    risk_score: float = 0.0
    is_hotspot: bool = False
    recommendation: str = "none"


# ═════════════════════════════════════════════════════════════════════
# 5. FeedbackPolicy — Weight Update Governance
# ═════════════════════════════════════════════════════════════════════

@dataclass
class FeedbackPolicy:
    """Policy rules governing the feedback loop.

    These are the guard conditions that prevent arbitrary weight changes.

    Ref: §5.3 — Self-Tuning boost thresholds
    Ref: §5.4 — DriftMonitor, SafeWeightBoundaries
    """
    min_confidence: float = 0.75
    min_sample_size: int = 20
    weight_min: float = 0.2
    weight_max: float = 0.8
    max_adjustments_per_hour: int = 3
    drift_warning_threshold: float = 0.05
    drift_block_threshold: float = 0.1
    risk_warning_delta: float = 5.0
    risk_block_delta: float = 10.0
    hotspot_coupling_threshold: float = 0.7
    hotspot_failure_rate: float = 0.2
    hotspot_min_executions: int = 100


# ═════════════════════════════════════════════════════════════════════
# 6. FeedbackState — Weight Update State Machine State
# ═════════════════════════════════════════════════════════════════════

class FeedbackState(str, Enum):
    """States of the feedback loop's weight update state machine.

    Ref: 03_drift_feedback_state_machine.md
    """
    IDLE = "idle"
    TRACE_CAPTURED = "trace_captured"
    METRIC_AGGREGATED = "metric_aggregated"
    THRESHOLD_CHECKED = "threshold_checked"
    WEIGHT_ADJUSTED = "weight_adjusted"
    ALERT_TRIGGERED = "alert_triggered"
    COOLDOWN = "cooldown"
    ERROR = "error"


# ═════════════════════════════════════════════════════════════════════
# Verification
# ═════════════════════════════════════════════════════════════════════

def verify_models() -> Dict[str, str]:
    """Verify that all models are structurally complete."""
    results: Dict[str, str] = {}

    models = [
        ("TraceEvent", ["trace_id", "execution_id", "node_id", "outcome", "duration_ms"]),
        ("WeightUpdateSignal", ["source_metric", "target_component", "delta", "confidence", "sample_size"]),
        ("DriftAlert", ["baseline_hash", "current_hash", "deviation_score", "violation_type", "severity"]),
        ("HotspotProfile", ["node_id", "execution_count", "failure_rate", "coupling_score", "risk_score"]),
        ("FeedbackPolicy", ["min_confidence", "min_sample_size", "weight_min", "weight_max"]),
    ]

    for name, required_fields in models:
        cls = globals().get(name)
        if cls is None:
            results[f"{name}"] = "FAIL — missing"
            continue
        fields = {f.name for f in cls.__dataclass_fields__.values()}
        missing = [f for f in required_fields if f not in fields]
        results[f"{name} ({len(fields)} fields)"] = "PASS" if not missing else f"FAIL — missing: {missing}"

    results[f"ExecutionOutcome ({len(ExecutionOutcome)} values)"] = "PASS"
    results[f"WeightTarget ({len(WeightTarget)} values)"] = "PASS"
    results[f"FeedbackState ({len(FeedbackState)} states)"] = "PASS"

    return results


if __name__ == "__main__":
    import json
    import pathlib

    results = verify_models()
    print("=" * 60)
    print("D9 — Trace & Feedback Model Verification")
    print("=" * 60)
    for key, value in results.items():
        status = "✅" if value == "PASS" else "❌"
        print(f"  {status}  {key}")
    print()
    total = len(results)
    passed = sum(1 for v in results.values() if v == "PASS")
    print(f"Result: {passed}/{total} passed")

    output_path = pathlib.Path(__file__).parent / "02_model_verification.json"
    output_path.write_text(json.dumps(results, indent=2))
    print(f"\nReport → {output_path}")
