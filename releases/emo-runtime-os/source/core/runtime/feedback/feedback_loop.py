"""D9 — IRuntimeFeedbackLoop implementation.

Core feedback loop that orchestrates:
  1. capture_trace()  — subscribe to EventBus for execution events
  2. analyze_impact() — compute coupling/risk drift from traces
  3. apply_weight_adjustment() — commit weight changes if guards pass
  4. publish_drift_alert() — emit architecture drift alerts via EventBus

LAW 11: No global state — feedback state is per-instance.
LAW 12: All events carry trace_id.
§17.9: CodeGraph communication is strictly via file protocol.

Ref: DEVELOPER.md §5.3 (Self-Tuning), §5.4 (Guardrails)
Ref: Canon LAW 5, LAW 11, LAW 12, LAW 14-16
Ref: artifacts/design/d9/protocols/01_feedback_loop_protocols.py
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from core.runtime.feedback.architecture_alert import ArchitectureAlert
from core.runtime.feedback.coupling_adjuster import DynamicCouplingAdjuster
from core.runtime.feedback.hotspot_detector import HotspotDetector
from core.runtime.feedback.rate_limiter import RateLimiter
from core.runtime.feedback.state_machine import FeedbackStateMachine
from core.runtime.models.feedback_models import (
    DriftAlert,
    DriftSeverity,
    ExecutionOutcome,
    FeedbackPolicy,
    FeedbackState,
    HotspotProfile,
    TraceEvent,
    UpdateOutcome,
    ViolationType,
    WeightTarget,
    WeightUpdateSignal,
)

logger = logging.getLogger("emo_ai.feedback.loop")


class FeedbackLoop:
    """Core feedback loop — captures traces, analyzes impact,
    applies weight adjustments, and publishes drift alerts.

    Orchestrates DynamicCouplingAdjuster, HotspotDetector,
    ArchitectureAlert, and RateLimiter.
    """

    def __init__(
        self,
        coupling_adjuster: Optional[DynamicCouplingAdjuster] = None,
        hotspot_detector: Optional[HotspotDetector] = None,
        architecture_alert: Optional[ArchitectureAlert] = None,
        rate_limiter: Optional[RateLimiter] = None,
        policy: Optional[FeedbackPolicy] = None,
        event_bus: Optional[Any] = None,
    ):
        self._coupling_adjuster = coupling_adjuster or DynamicCouplingAdjuster()
        self._hotspot_detector = hotspot_detector or HotspotDetector(policy)
        self._arch_alert = architecture_alert or ArchitectureAlert(policy)
        self._rate_limiter = rate_limiter or RateLimiter()
        self._policy = policy or FeedbackPolicy()
        self._event_bus = event_bus

        self._state_machine = FeedbackStateMachine(policy)
        self._traces: List[TraceEvent] = []
        self._current_weights: Dict[str, float] = {
            "w_graph": 0.5,
            "w_sem": 0.5,
            "coupling_threshold": 0.5,
            "risk_threshold": 0.5,
            "strategy_weight": 0.5,
        }
        self._baseline_scores: Dict[str, float] = {}
        self._adjustment_count: int = 0

    @property
    def state_machine(self) -> FeedbackStateMachine:
        return self._state_machine

    @property
    def current_weights(self) -> Dict[str, float]:
        return dict(self._current_weights)

    @property
    def traces(self) -> List[TraceEvent]:
        return list(self._traces)

    # ── 1. capture_trace() ───────────────────────────────────────

    def capture_trace(self, event: Any) -> None:
        """Capture an execution trace event.

        LAW 5: Every execution MUST be observable.
        LAW 12: All side effects carry trace_id.

        Converts raw event into a TraceEvent and stores it
        in the ring buffer for analysis.
        """
        trace = self._convert_event(event)
        if trace is None:
            self._state_machine.transition(FeedbackState.ERROR, has_error=True)
            return

        # Dedup by trace_id
        if any(t.trace_id == trace.trace_id for t in self._traces):
            return

        self._traces.append(trace)

        # Maintain ring buffer
        if len(self._traces) > self._policy.window_size * 2:
            self._traces = self._traces[-self._policy.window_size:]

        # Forward to hotspot detector
        self._hotspot_detector.record_trace(trace)

        # Transition state machine
        self._state_machine.transition(
            FeedbackState.TRACE_CAPTURED,
            trace_count=len(self._traces),
        )

        logger.debug(
            "capture_trace: %s/%s (%s trace=%s)",
            len(self._traces), self._policy.window_size,
            trace.outcome.value, trace.trace_id,
        )

    def _convert_event(self, event: Any) -> Optional[TraceEvent]:
        """Convert an EventBus event to a TraceEvent.

        Args:
            event: EventBus ExecutionEvent or compatible object.

        Returns:
            TraceEvent or None if conversion fails.
        """
        if event is None:
            logger.warning("Cannot convert None event")
            return None

        try:
            payload = getattr(event, "payload", {}) or {}
            if isinstance(event, dict):
                payload = event

            trace_id = (
                getattr(event, "trace_id", None)
                or payload.get("trace_id", "")
            )
            if not trace_id:
                return None

            execution_id = (
                getattr(event, "session_id", None)
                or payload.get("session_id", "")
                or payload.get("execution_id", "")
            )
            node_id = payload.get("node_id", "") or payload.get("ticket_id", "")
            tool_name = payload.get("tool", "") or payload.get("dag_id", "")

            outcome_str = payload.get("status", "success")
            outcome_map = {
                "success": ExecutionOutcome.SUCCESS,
                "completed": ExecutionOutcome.SUCCESS,
                "failed": ExecutionOutcome.FAILED,
                "timeout": ExecutionOutcome.TIMEOUT,
                "cancelled": ExecutionOutcome.CANCELLED,
                "blocked": ExecutionOutcome.BLOCKED,
            }
            outcome = outcome_map.get(outcome_str, ExecutionOutcome.SUCCESS)

            duration_ms = float(payload.get("duration_ms", 0))

            resource = payload.get("resource_consumed", {})
            if isinstance(resource, dict):
                resource_consumed = resource
            else:
                resource_consumed = {}

            return TraceEvent(
                trace_id=trace_id,
                execution_id=execution_id,
                node_id=node_id,
                tool_name=tool_name,
                outcome=outcome,
                duration_ms=duration_ms,
                resource_consumed=resource_consumed,
                feedback_signals=[],
                timestamp=time.time(),
            )
        except Exception as e:
            logger.warning("Failed to convert event: %s", e)
            return None

    # ── 2. analyze_impact() ──────────────────────────────────────

    def analyze_impact(
        self,
        node_id: str,
        window_size: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Analyze the execution impact of a node over a rolling window.

        LAW 7: Execution analysis SHOULD be deterministic (same traces → same result).

        Computes:
          - success_rate over window
          - avg duration and resource consumption
          - coupling delta (from baseline)
          - failure pattern classification

        Args:
            node_id: Node or tool ID to analyze.
            window_size: Rolling window size (defaults to policy).

        Returns:
            Impact analysis dict with metrics and recommendation.
        """
        ws = window_size or self._policy.window_size
        node_traces = [
            t for t in self._traces[-ws:]
            if t.node_id == node_id or t.tool_name == node_id
        ]

        if not node_traces:
            return {
                "node_id": node_id,
                "success_rate": 0.0,
                "avg_duration_ms": 0.0,
                "coupling_delta": 0.0,
                "failure_pattern": "none",
                "recommendation": "insufficient_data",
                "sample_size": 0,
            }

        successes = sum(1 for t in node_traces if t.outcome == ExecutionOutcome.SUCCESS)
        total = len(node_traces)
        success_rate = successes / max(total, 1)
        avg_duration = sum(t.duration_ms for t in node_traces) / max(total, 1)

        # Compute new coupling scores
        new_scores = self._coupling_adjuster.compute_new_scores(
            node_traces, self._baseline_scores,
        )
        new_score = new_scores.get(node_id, 0.5)
        old_score = self._baseline_scores.get(node_id, 0.5)
        coupling_delta = new_score - old_score

        # Failure pattern detection
        failures = [t for t in node_traces if t.outcome != ExecutionOutcome.SUCCESS]
        pattern_types: Dict[str, int] = {}
        for f in failures:
            pt = f.outcome.value
            pattern_types[pt] = pattern_types.get(pt, 0) + 1
        dominant_pattern = max(pattern_types, key=pattern_types.get) if pattern_types else "none"

        # Recommendation
        recommendation = "none"
        if coupling_delta > self._policy.drift_warning_threshold:
            recommendation = "monitor"
        if coupling_delta > self._policy.drift_block_threshold:
            recommendation = "review"
        if new_score > 0.8:
            recommendation = "decompose"

        self._state_machine.transition(
            FeedbackState.METRIC_AGGREGATED,
        )

        return {
            "node_id": node_id,
            "success_rate": round(success_rate, 4),
            "avg_duration_ms": round(avg_duration, 2),
            "coupling_delta": round(coupling_delta, 4),
            "failure_pattern": dominant_pattern,
            "recommendation": recommendation,
            "sample_size": total,
        }

    # ── 3. apply_weight_adjustment() ─────────────────────────────

    def apply_weight_adjustment(
        self,
        signal: WeightUpdateSignal,
    ) -> UpdateOutcome:
        """Apply a dynamic weight adjustment based on feedback analysis.

        Guards:
          - signal.confidence >= 0.75
          - signal.sample_size >= 20
          - w_graph/w_sem stay within [0.2, 0.8]
          - No more than 3 adjustments per hour

        Args:
            signal: WeightUpdateSignal with adjustment parameters.

        Returns:
            UpdateOutcome: ADJUSTED, NO_OP, DEFERRED, REJECTED, or ALERTED.
        """
        # Transition to THRESHOLD_CHECKED
        impact = self.analyze_impact(
            signal.source_metric,
            window_size=signal.sample_size,
        )

        deviation = abs(impact.get("coupling_delta", 0.0))

        # Check NO_OP
        if deviation < 0.01:
            self._state_machine.transition(
                FeedbackState.NO_OP, deviation=deviation,
            )
            self._state_machine.transition(FeedbackState.COOLDOWN)
            return UpdateOutcome.NO_OP

        # Check rate limit
        if not self._rate_limiter.can_adjust(signal.source_metric):
            logger.info("Rate limit exceeded for %s", signal.source_metric)
            self._state_machine.transition(
                FeedbackState.REJECTED, signal=signal,
                current_weights=self._current_weights,
                adjustment_count=self._adjustment_count,
            )
            self._state_machine.transition(FeedbackState.COOLDOWN)
            return UpdateOutcome.DEFERRED

        # Check guard conditions
        allowed, reason = self._state_machine.guard_weight_adjustment(
            signal=signal,
            current_weights=self._current_weights,
            adjustment_count=self._adjustment_count,
        )

        if not allowed:
            logger.info("Weight adjustment rejected: %s", reason)

            # Check if deviation warrants alert
            if deviation > self._policy.drift_warning_threshold:
                alert = self._arch_alert.evaluate_violation(
                    ViolationType.COUPLING_INCREASE,
                    source=signal.source_metric,
                    score=deviation,
                )
                self._publish_drift_alert(alert)
                self._state_machine.transition(
                    FeedbackState.ALERT_TRIGGERED, deviation=deviation,
                )
                return UpdateOutcome.ALERTED

            self._state_machine.transition(
                FeedbackState.REJECTED, signal=signal,
                current_weights=self._current_weights,
                adjustment_count=self._adjustment_count,
            )
            self._state_machine.transition(FeedbackState.COOLDOWN)
            return UpdateOutcome.REJECTED

        # Check alert threshold before applying
        if deviation > self._policy.drift_block_threshold:
            alert = self._arch_alert.evaluate_violation(
                ViolationType.COUPLING_INCREASE,
                source=signal.source_metric,
                score=deviation,
            )
            self._publish_drift_alert(alert)
            self._state_machine.transition(
                FeedbackState.ALERT_TRIGGERED, deviation=deviation,
            )
            return UpdateOutcome.ALERTED

        # Apply adjustment
        target = signal.target_component.value
        current = self._current_weights.get(target, 0.5)
        self._current_weights[target] = max(
            self._policy.weight_min,
            min(self._policy.weight_max, current + signal.delta),
        )

        self._adjustment_count += 1
        self._rate_limiter.record_adjustment(signal.source_metric)
        self._state_machine.transition(
            FeedbackState.WEIGHT_ADJUSTED, committed=True,
        )

        # Commit to CodeGraph (via coupling adjuster)
        commit_ok = self._coupling_adjuster.commit_boundary_update(
            signal.source_metric,
            self._current_weights[target],
        )
        if commit_ok:
            self._state_machine.transition(FeedbackState.COMMITTED)
        else:
            self._state_machine.transition(
                FeedbackState.ERROR, committed=False,
            )

        self._state_machine.transition(FeedbackState.COOLDOWN)
        logger.info(
            "Weight adjusted: %s %s→%.2f (delta=%.2f, reason=%s)",
            target, current, self._current_weights[target],
            signal.delta, signal.reason,
        )
        return UpdateOutcome.ADJUSTED

    # ── 4. publish_drift_alert() ─────────────────────────────────

    def publish_drift_alert(self, alert: DriftAlert) -> None:
        """Publish a drift alert to EventBus and trigger enforcement.

        LAW 14-16: Drift alerts enforce decomposition boundaries.

        Args:
            alert: DriftAlert with violation details.
        """
        self._publish_drift_alert(alert)

    def _publish_drift_alert(self, alert: DriftAlert) -> None:
        """Internal — publish alert and trigger enforcement gate."""
        # Trigger enforcement gate
        gate_triggered = self._arch_alert.trigger_enforcement_gate(
            alert, self._event_bus,
        )

        severity = DriftSeverity(alert.severity)
        if gate_triggered and severity in (DriftSeverity.CRITICAL, DriftSeverity.BLOCKING):
            self._state_machine.transition(
                FeedbackState.ENFORCEMENT_GATE, severity=alert.severity,
            )
        else:
            self._state_machine.transition(FeedbackState.COOLDOWN)

        # Log alert
        logger.warning(
            "Drift alert: %s (severity=%s, score=%.4f, action=%s)",
            alert.violation_type, alert.severity,
            alert.deviation_score, alert.action_required,
        )

    # ── Utility ────────────────────────────────────────────────

    def get_hotspot_profile(self, node_id: str) -> HotspotProfile:
        """Get hotspot profile for a node.

        Args:
            node_id: Node identifier.

        Returns:
            HotspotProfile from HotspotDetector.
        """
        return self._hotspot_detector.get_profile(node_id)

    def suggest_decomposition(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Suggest decomposition if a node is a hotspot.

        Args:
            node_id: Node identifier.

        Returns:
            Decomposition suggestion dict or None.
        """
        return self._hotspot_detector.suggest_decomposition(node_id)

    def get_current_state(self) -> str:
        """Get the current state machine state.

        Returns:
            Current FeedbackState value.
        """
        return self._state_machine.current.value

    def reset(self) -> None:
        """Reset feedback loop state (for testing)."""
        self._traces.clear()
        self._current_weights = {
            "w_graph": 0.5,
            "w_sem": 0.5,
            "coupling_threshold": 0.5,
            "risk_threshold": 0.5,
            "strategy_weight": 0.5,
        }
        self._baseline_scores.clear()
        self._adjustment_count = 0
        self._state_machine.force_set(FeedbackState.IDLE)
        self._rate_limiter.reset()
        self._hotspot_detector.reset()
