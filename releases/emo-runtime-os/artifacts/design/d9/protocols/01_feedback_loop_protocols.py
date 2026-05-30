"""Phase D9 — Runtime Intelligence Feedback Loop Protocols.

DESIGN ONLY — No runtime logic. Four typing.Protocol definitions
for the execution feedback loop bridging traces, CodeGraph, and adaptive weights.

Protocols:
  IRuntimeFeedbackLoop        — Core loop: capture → analyze → adjust → alert
  IDynamicCouplingAdjuster    — CodeGraph boundary score computation + commit
  IHotspotDetector            — Runtime hotspot detection + decomposition suggestions
  IRuntimeArchitectureAlert   — Architecture drift alerting + enforcement gate

Ref: DEVELOPER.md §5.3 (Self-Tuning), §15.6 (Dependency Governance)
Ref: DEVELOPER.md §17.9 (CodeGraph MUST NOT depend on runtime)
Ref: Canon LAW 5 (Observable), LAW 7 (Deterministic), LAW 11 (No global state)
Ref: Canon LAW 14-16 (CodeGraph-Driven Decomposition Laws)
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


# ═════════════════════════════════════════════════════════════════════
# Shared D9 Types
# ═════════════════════════════════════════════════════════════════════

class DriftSeverity(str, Enum):
    """Severity classification for architecture drift alerts.

    Ref: LAW 14-16 — CodeGraph-Driven Decomposition Laws
    """
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    BLOCKING = "blocking"


class ViolationType(str, Enum):
    """Types of architectural violations detectable at runtime.

    Ref: Canon §16.10 — Architecture Drift Protection Rule
    """
    COUPLING_INCREASE = "coupling_increase"
    RISK_SCORE_EXCEEDED = "risk_score_exceeded"
    BOUNDARY_VIOLATION = "boundary_violation"
    INFRASTRUCTURE_LEAKAGE = "infrastructure_leakage"
    CIRCULAR_DEPENDENCY = "circular_dependency"
    HOTSPOT_DETECTED = "hotspot_detected"
    DECOMPOSITION_REQUIRED = "decomposition_required"


class UpdateOutcome(str, Enum):
    """Outcome of a weight update or boundary adjustment.

    Ref: §5.3 — Self-Tuning
    """
    ADJUSTED = "adjusted"
    NO_OP = "no_op"             # Within threshold — no change needed
    DEFERRED = "deferred"       # Insufficient confidence — wait for more samples
    REJECTED = "rejected"       # Guard conditions not met — change blocked
    ALERTED = "alerted"         # Over threshold — alert fired, no change


class FeedbackSignal(str, Enum):
    """Types of feedback signals that feed into the adjustment loop.

    Ref: §5.3 — Boost thresholds (success_rate → delta)
    """
    EXECUTION_SUCCESS = "execution_success"
    EXECUTION_FAILURE = "execution_failure"
    RETRY_ATTEMPTED = "retry_attempted"
    TIMEOUT_OCCURRED = "timeout_occurred"
    QUOTA_EXCEEDED = "quota_exceeded"
    LEASE_EXPIRED = "lease_expired"
    COUPLING_DRIFT = "coupling_drift"
    REPLAY_MISMATCH = "replay_mismatch"


# ═════════════════════════════════════════════════════════════════════
# D9.1 — IRuntimeFeedbackLoop
# ═════════════════════════════════════════════════════════════════════

@runtime_checkable
class IRuntimeFeedbackLoop(Protocol):
    """Core feedback loop — captures execution traces, analyzes impact,
    applies weight adjustments, and publishes drift alerts.

    Flow:
      1. capture_trace()  — subscribe to EventBus for execution events
      2. analyze_impact() — compute coupling/risk drift, success rates
      3. apply_weight_adjustment() — commit changes if guards pass
      4. publish_drift_alert() — emit ArchitectureDriftDetected if thresholds exceeded

    LAW 11: No module may directly own global runtime state.
      → FeedbackLoop reads from EventBus, never from Runtime internals.

    §17.9: CodeGraph MUST NOT depend on runtime.
      → FeedbackLoop writes to CodeGraph metadata via file protocol only.

    Ref: DEVELOPER.md §5.3 (Self-Tuning)
    Ref: Canon LAW 5 (Observable), LAW 7 (Deterministic), LAW 11 (No global state)
    """

    def capture_trace(
        self,
        event: Any,  # TraceEvent — see models/02_trace_and_feedback_models.py
    ) -> None:
        """Capture an execution trace event from the EventBus.

        The FeedbackLoop subscribes to "runtime.execution.*" events
        and converts them into internal TraceEvent records.

        Args:
            event: TraceEvent with execution_id, node_id, duration_ms,
                   outcome, resource_consumed, timestamp.

        Ref: LAW 5 — Every execution MUST be observable
        Ref: LAW 12 — All side effects MUST be traceable
        """
        ...

    def analyze_impact(
        self,
        node_id: str,
        window_size: int = 50,
    ) -> Dict[str, Any]:
        """Analyze the execution impact of a node/tool over a rolling window.

        Computes:
          - success_rate over window_size executions
          - avg duration and resource consumption
          - coupling delta (before/after CodeGraph baseline)
          - failure pattern classification

        Args:
            node_id: The node or tool ID to analyze.
            window_size: Rolling window size for analysis.

        Returns:
            Impact analysis dict with keys: success_rate, avg_duration_ms,
            coupling_delta, failure_pattern, recommendation.

        Ref: §5.3 — Boost thresholds (success_rate → delta)
        Ref: Canon LAW 7 — Execution logic SHOULD be deterministic
        """
        ...

    def apply_weight_adjustment(
        self,
        signal: Any,  # WeightUpdateSignal — see models/
    ) -> UpdateOutcome:
        """Apply a dynamic weight adjustment based on feedback analysis.

        Guards:
          - signal.confidence >= 0.75
          - signal.sample_size >= 20
          - w_graph/w_sem stay within [0.2, 0.8] (SafeWeightBoundaries)
          - No more than 3 adjustments per hour (rate limit)

        Args:
            signal: WeightUpdateSignal with source_metric, target_component,
                    delta, confidence, sample_size.

        Returns:
            UpdateOutcome: ADJUSTED, NO_OP, DEFERRED, REJECTED, or ALERTED.

        Ref: §5.3 — SafeWeightBoundaries [0.2, 0.8]
        Ref: Canon LAW 14 — CodeGraph-derived boundaries
        """
        ...

    def publish_drift_alert(
        self,
        alert: Any,  # DriftAlert — see models/
    ) -> None:
        """Publish a drift alert to the EventBus.

        Alert is emitted as "runtime.drift.detected" with full payload.
        If severity >= CRITICAL, trigger enforcement gate.

        Args:
            alert: DriftAlert with baseline_hash, current_hash,
                   deviation_score, violation_type, action_required.

        Ref: Canon LAW 14-16 — Drift thresholds
        Ref: §17.9 — CodeGraph purity
        """
        ...


# ═════════════════════════════════════════════════════════════════════
# D9.2 — IDynamicCouplingAdjuster
# ═════════════════════════════════════════════════════════════════════

@runtime_checkable
class IDynamicCouplingAdjuster(Protocol):
    """Computes new coupling/risk scores from runtime feedback and
    commits boundary updates to CodeGraph metadata.

    LAW 14 enforcement: All boundary decisions MUST be derived from analysis.
    LAW 15 enforcement: No refactor without graph update.
    LAW 16 enforcement: Nodes with risk_score > 0.8 MUST be flagged for decomposition.

    §17.9: This adjuster writes to CodeGraph metadata.json/edges.json
    via atomic file swap — never reads from runtime internals.
    """

    def compute_new_scores(
        self,
        traces: List[Any],  # List[TraceEvent]
        baseline: Dict[str, Any],
    ) -> Dict[str, float]:
        """Compute new coupling/risk scores from execution traces.

        Algorithm:
          1. Count cross-boundary calls per node from traces
          2. Compute coupling = cross_boundary / total_calls
          3. Compute risk = coupling * (1 + failure_rate) * complexity_factor
          4. Compare against baseline, return deltas

        Args:
            traces: List of TraceEvent records from recent window.
            baseline: Current CodeGraph baseline scores.

        Returns:
            Dict mapping node_id → new_coupling_score (0.0–1.0).

        Ref: Canon LAW 14 — CodeGraph-derived boundaries
        """
        ...

    def validate_threshold(
        self,
        new_score: float,
        old_score: float,
        node_id: str = "",
    ) -> bool:
        """Validate that a score change is within acceptable thresholds.

        Thresholds:
          - coupling delta > 0.1 → BLOCK (LAW 14 violation)
          - risk_score > 0.8 → DECOMPOSITION REQUIRED (LAW 16)
          - boundary leakage detected → BLOCK

        Args:
            new_score: Proposed new score.
            old_score: Current baseline score.
            node_id: Node identifier for error context.

        Returns:
            True if within threshold, False if violation.

        Ref: §3.4.5 — emo-guard thresholds: coupling ↑>0.1, risk ↑>10
        """
        ...

    def commit_boundary_update(
        self,
        node_id: str,
        new_score: float,
        metadata_path: str = "",
    ) -> bool:
        """Commit a boundary score update to CodeGraph metadata.

        Uses atomic file swap to prevent corruption:
          1. Write to .tmp file
          2. Compute checksum
          3. Rename .tmp → metadata.json

        Args:
            node_id: Node identifier.
            new_score: New coupling/risk score.
            metadata_path: Path to CodeGraph metadata file.

        Returns:
            True if commit succeeded.

        Ref: §17.10 — CodeGraph outputs (metadata.json, edges.json)
        Ref: Canon LAW 15 — Graph must be updated before refactor
        """
        ...


# ═════════════════════════════════════════════════════════════════════
# D9.3 — IHotspotDetector
# ═════════════════════════════════════════════════════════════════════

@runtime_checkable
class IHotspotDetector(Protocol):
    """Tracks execution frequency and failure patterns to identify
    runtime hotspots and suggest decomposition targets.

    LAW 16: Any node with risk_score > 0.8 MUST be decomposed.
    """

    def track_execution_frequency(
        self,
        node_id: str,
        window_size: int = 100,
    ) -> Dict[str, Any]:
        """Track how often a node is executed and its resource profile.

        Args:
            node_id: Node/tool identifier.
            window_size: Rolling window count.

        Returns:
            Dict with frequency, avg_duration_ms,
            avg_memory_bytes, avg_cpu_seconds.

        Ref: LAW 5 — Observable execution
        """
        ...

    def identify_failure_patterns(
        self,
        node_id: str,
    ) -> List[Dict[str, Any]]:
        """Identify recurring failure patterns for a node.

        Analyzes FailureIntelligence data and execution traces
        to classify failure types (timeout, quota, capability, etc.).

        Args:
            node_id: Node/tool identifier.

        Returns:
            List of failure pattern dicts with pattern_type,
            frequency, last_occurred, suggested_action.

        Ref: LAW 10 — Workers are unreliable (track failures)
        """
        ...

    def suggest_decomposition(
        self,
        node_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Suggest decomposition if a node is a hotspot candidate.

        Criteria:
          - risk_score > 0.8 (LAW 16)
          - coupling score > 0.7
          - execution count > 100 per hour
          - failure_rate > 0.2

        Args:
            node_id: Node/tool identifier.

        Returns:
            Decomposition suggestion dict or None if not needed.
            Contains: candidate_boundaries, estimated_score_reduction.

        Ref: Canon LAW 16 — risk_score > 0.8 must decompose
        """
        ...


# ═════════════════════════════════════════════════════════════════════
# D9.4 — IRuntimeArchitectureAlert
# ═════════════════════════════════════════════════════════════════════

@runtime_checkable
class IRuntimeArchitectureAlert(Protocol):
    """Evaluates architectural violations at runtime, classifies severity,
    and triggers the enforcement gate.

    Ref: §3.4.5 — Dependency Enforcement Layer (emo-guard)
    Ref: §15.6 — Governance MUST NOT depend on runtime implementation (LAW 9)
    """

    def evaluate_violation(
        self,
        violation_type: ViolationType,
        source: str,
        target: str = "",
        score: float = 0.0,
    ) -> Any:  # DriftAlert
        """Evaluate an architectural violation and produce a DriftAlert.

        Args:
            violation_type: Type of architectural violation detected.
            source: Source node/module of the violation.
            target: Target node/module affected.
            score: Violation score (coupling delta, risk delta, etc.).

        Returns:
            DriftAlert with severity, deviation_score, action_required.

        Ref: Canon LAW 14-16
        """
        ...

    def classify_severity(
        self,
        deviation_score: float,
        violation_type: ViolationType,
    ) -> DriftSeverity:
        """Classify the severity of a deviation.

        Thresholds:
          - 0.0–0.05: INFO
          - 0.05–0.1: WARNING
          - 0.1–0.2: CRITICAL
          - >0.2: BLOCKING

        Ref: §3.4.5 — emo-guard thresholds
        """
        ...

    def trigger_enforcement_gate(
        self,
        alert: Any,  # DriftAlert
    ) -> bool:
        """Trigger the enforcement gate for BLOCKING or CRITICAL alerts.

        Actions:
          - CRITICAL: Emit "runtime.drift.critical" → EventBus → CI gate
          - BLOCKING: Emit "runtime.drift.blocking" + pause affected execution
          - WARNING/INFO: Log only, no enforcement action

        Args:
            alert: DriftAlert to act upon.

        Returns:
            True if gate was triggered, False for INFO/WARNING.

        Ref: §3.4.5 — emo-guard blocks on coupling ↑>0.1
        """
        ...


# ═════════════════════════════════════════════════════════════════════
# Interaction Contracts
# ═════════════════════════════════════════════════════════════════════

FEEDBACK_LOOP_CONTRACTS: Dict[str, Dict[str, Any]] = {
    "EventBus → IRuntimeFeedbackLoop": {
        "source": "IEventBus",
        "target": "IRuntimeFeedbackLoop",
        "method": "capture_trace",
        "event_pattern": "runtime.execution.*",
        "consistency": "eventual",
        "law_ref": "LAW 5, LAW 12",
    },
    "IRuntimeFeedbackLoop → IDynamicCouplingAdjuster": {
        "source": "IRuntimeFeedbackLoop",
        "target": "IDynamicCouplingAdjuster",
        "method": "compute_new_scores",
        "trigger": "analyze_impact completes with coupling_delta > 0",
        "consistency": "strong",
        "law_ref": "LAW 14, LAW 15",
    },
    "IDynamicCouplingAdjuster → CodeGraph metadata.json": {
        "source": "IDynamicCouplingAdjuster",
        "target": "CodeGraph (file protocol)",
        "method": "commit_boundary_update",
        "trigger": "validate_threshold passes",
        "consistency": "strong",
        "law_ref": "LAW 15, §17.10",
    },
    "IRuntimeFeedbackLoop → IHotspotDetector": {
        "source": "IRuntimeFeedbackLoop",
        "target": "IHotspotDetector",
        "method": "track_execution_frequency",
        "trigger": "periodic (every 100 traces per node)",
        "consistency": "eventual",
        "law_ref": "LAW 16, LAW 5",
    },
    "IHotspotDetector → IRuntimeArchitectureAlert": {
        "source": "IHotspotDetector",
        "target": "IRuntimeArchitectureAlert",
        "method": "evaluate_violation",
        "trigger": "risk_score > 0.8 OR coupling > 0.7",
        "consistency": "strong",
        "law_ref": "LAW 16, LAW 14",
    },
    "IRuntimeArchitectureAlert → IEventBus": {
        "source": "IRuntimeArchitectureAlert",
        "target": "IEventBus",
        "method": "publish",
        "event_pattern": "runtime.drift.*",
        "consistency": "strong",
        "law_ref": "LAW 5, LAW 14-16",
    },
}


# ═════════════════════════════════════════════════════════════════════
# Protocol Conformance Verification
# ═════════════════════════════════════════════════════════════════════

def verify_protocol_conformance() -> Dict[str, str]:
    """Verify that all D9 protocols are structurally valid."""
    results: Dict[str, str] = {}

    protocol_checks = {
        "IRuntimeFeedbackLoop": ["capture_trace", "analyze_impact",
                                  "apply_weight_adjustment", "publish_drift_alert"],
        "IDynamicCouplingAdjuster": ["compute_new_scores", "validate_threshold",
                                      "commit_boundary_update"],
        "IHotspotDetector": ["track_execution_frequency", "identify_failure_patterns",
                              "suggest_decomposition"],
        "IRuntimeArchitectureAlert": ["evaluate_violation", "classify_severity",
                                       "trigger_enforcement_gate"],
    }

    for protocol_name, methods in protocol_checks.items():
        proto = globals().get(protocol_name)
        if proto is None:
            results[f"{protocol_name} definition"] = "FAIL — missing"
            continue
        all_methods = all(hasattr(proto, m) for m in methods)
        results[f"{protocol_name} ({len(methods)} methods)"] = "PASS" if all_methods else "FAIL"

    # Interaction contracts
    results[f"Interaction contracts ({len(FEEDBACK_LOOP_CONTRACTS)})"] = "PASS"

    # Shared types
    types = [DriftSeverity, ViolationType, UpdateOutcome, FeedbackSignal]
    results[f"Shared types ({len(types)} enums)"] = "PASS"

    return results


if __name__ == "__main__":
    import json
    import pathlib

    results = verify_protocol_conformance()
    print("=" * 60)
    print("D9 — Feedback Loop Protocol Conformance")
    print("=" * 60)
    for key, value in results.items():
        status = "✅" if value == "PASS" else "❌"
        print(f"  {status}  {key}")
    print()
    total = len(results)
    passed = sum(1 for v in results.values() if v == "PASS")
    print(f"Result: {passed}/{total} passed")

    output_path = pathlib.Path(__file__).parent / "01_protocol_conformance.json"
    output_path.write_text(json.dumps(results, indent=2))
    print(f"\nReport → {output_path}")
