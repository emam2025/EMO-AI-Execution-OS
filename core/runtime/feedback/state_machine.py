"""D9 — Feedback Loop State Machine.

8-state machine governing the feedback loop lifecycle:
IDLE → TRACE_CAPTURED → METRIC_AGGREGATED → THRESHOLD_CHECKED
  → WEIGHT_ADJUSTED → COMMITTED → COOLDOWN → IDLE
  with branches: ERROR, ALERT_TRIGGERED, ENFORCEMENT_GATE, REJECTED, NO_OP

Every transition has a guard condition preventing invalid state changes.

Ref: DEVELOPER.md §5.3, §5.4
Ref: artifacts/design/d9/03_drift_feedback_state_machine.md
Ref: Canon LAW 11 (No global state), LAW 14-16
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from core.runtime.models.feedback_models import (
    FeedbackPolicy,
    FeedbackState,
    UpdateOutcome,
    WeightUpdateSignal,
)

logger = logging.getLogger("emo_ai.feedback.state_machine")

# Transition table: (from, to) -> guard function name or None
TRANSITIONS: Dict[Tuple[FeedbackState, FeedbackState], Optional[str]] = {
    (FeedbackState.IDLE, FeedbackState.TRACE_CAPTURED): None,
    (FeedbackState.IDLE, FeedbackState.ERROR): None,
    (FeedbackState.TRACE_CAPTURED, FeedbackState.METRIC_AGGREGATED): "guard_trace_to_metric",
    (FeedbackState.TRACE_CAPTURED, FeedbackState.ERROR): "guard_to_error",
    (FeedbackState.METRIC_AGGREGATED, FeedbackState.THRESHOLD_CHECKED): None,
    (FeedbackState.THRESHOLD_CHECKED, FeedbackState.WEIGHT_ADJUSTED): "guard_weight_adjustment",
    (FeedbackState.THRESHOLD_CHECKED, FeedbackState.REJECTED): "guard_rejected",
    (FeedbackState.THRESHOLD_CHECKED, FeedbackState.NO_OP): "guard_no_op",
    (FeedbackState.THRESHOLD_CHECKED, FeedbackState.ALERT_TRIGGERED): "guard_alert_triggered",
    (FeedbackState.WEIGHT_ADJUSTED, FeedbackState.COMMITTED): "guard_committed",
    (FeedbackState.WEIGHT_ADJUSTED, FeedbackState.ERROR): "guard_commit_error",
    (FeedbackState.COMMITTED, FeedbackState.COOLDOWN): None,
    (FeedbackState.REJECTED, FeedbackState.COOLDOWN): None,
    (FeedbackState.NO_OP, FeedbackState.COOLDOWN): None,
    (FeedbackState.ALERT_TRIGGERED, FeedbackState.ENFORCEMENT_GATE): "guard_enforcement_gate",
    (FeedbackState.ALERT_TRIGGERED, FeedbackState.COOLDOWN): None,
    (FeedbackState.ENFORCEMENT_GATE, FeedbackState.COOLDOWN): None,
    (FeedbackState.COOLDOWN, FeedbackState.IDLE): "guard_cooldown_expired",
    (FeedbackState.ERROR, FeedbackState.COOLDOWN): None,
}

TERMINAL_STATES: set = set()

RECOVERY_STATES: set = {
    FeedbackState.ERROR,
}


class FeedbackStateMachine:
    """8-state machine for the feedback loop's weight update lifecycle.

    LAW 11: No global state — per-instance state machine.
    """

    def __init__(self, policy: Optional[FeedbackPolicy] = None) -> None:
        self._policy = policy or FeedbackPolicy()
        self._current = FeedbackState.IDLE
        self._history: List[Dict[str, Any]] = []
        self._error: Optional[str] = None
        self._trace_window: int = 0

    @property
    def current(self) -> FeedbackState:
        return self._current

    @property
    def history(self) -> List[Dict[str, Any]]:
        return list(self._history)

    @property
    def error(self) -> Optional[str]:
        return self._error

    def guard_trace_to_metric(self, trace_count: int = 0) -> Tuple[bool, str]:
        if trace_count < 1:
            return False, "No valid traces in window"
        return True, ""

    def guard_to_error(self, has_error: bool = True) -> Tuple[bool, str]:
        return has_error, ""

    def guard_weight_adjustment(
        self,
        signal: Optional[WeightUpdateSignal] = None,
        current_weights: Optional[Dict[str, float]] = None,
        adjustment_count: int = 0,
    ) -> Tuple[bool, str]:
        if signal is None:
            return False, "No signal provided"
        if signal.confidence < self._policy.min_confidence:
            return False, (
                f"confidence {signal.confidence:.2f} < {self._policy.min_confidence}"
            )
        if signal.sample_size < self._policy.min_sample_size:
            return False, (
                f"sample_size {signal.sample_size} < {self._policy.min_sample_size}"
            )
        target = signal.target_component.value
        current = (current_weights or {}).get(target, 0.5)
        new_val = current + signal.delta
        if new_val < self._policy.weight_min or new_val > self._policy.weight_max:
            return False, (
                f"new {target} = {new_val:.2f} outside "
                f"[{self._policy.weight_min}, {self._policy.weight_max}]"
            )
        if adjustment_count >= self._policy.max_adjustments_per_hour:
            return False, (
                f"rate limit: {adjustment_count}/hr >= {self._policy.max_adjustments_per_hour}"
            )
        return True, "all guards passed"

    def guard_rejected(
        self,
        signal: Optional[WeightUpdateSignal] = None,
        current_weights: Optional[Dict[str, float]] = None,
        adjustment_count: int = 0,
    ) -> Tuple[bool, str]:
        result, _ = self.guard_weight_adjustment(
            signal, current_weights, adjustment_count,
        )
        return (not result, "guard conditions failed")

    def guard_no_op(self, deviation: float = 0.0) -> Tuple[bool, str]:
        if abs(deviation) < 0.01:
            return True, "deviation within threshold"
        return False, f"deviation {deviation} >= 0.01"

    def guard_alert_triggered(self, deviation: float = 0.0) -> Tuple[bool, str]:
        if deviation > self._policy.drift_warning_threshold:
            return True, f"deviation {deviation} > warning threshold"
        return False, f"deviation {deviation} <= warning threshold"

    def guard_committed(self, committed: bool = True) -> Tuple[bool, str]:
        return committed, ""

    def guard_commit_error(self, committed: bool = True) -> Tuple[bool, str]:
        return (not committed, "commit failed")

    def guard_enforcement_gate(self, severity: str = "info") -> Tuple[bool, str]:
        if severity in ("critical", "blocking"):
            return True, f"severity {severity} >= critical"
        return False, f"severity {severity} < critical"

    def guard_cooldown_expired(self, cooldown_remaining: float = 0.0) -> Tuple[bool, str]:
        if cooldown_remaining <= 0:
            return True, "cooldown expired"
        return False, f"cooldown {cooldown_remaining:.0f}s remaining"

    def transition(self, to_state: FeedbackState, **kwargs) -> Tuple[bool, str]:
        """Attempt a guarded state transition.

        Args:
            to_state: Target state.
            **kwargs: Arguments for the guard function.

        Returns:
            Tuple of (allowed, reason).
        """
        key = (self._current, to_state)
        guard_name = TRANSITIONS.get(key)

        if guard_name is None and key not in TRANSITIONS:
            return False, (
                f"Invalid transition: {self._current.value} → {to_state.value}"
            )

        if guard_name is None:
            self._apply_transition(to_state)
            return True, ""

        guard_fn = getattr(self, guard_name, None)
        if guard_fn is None:
            return False, f"Guard {guard_name} not implemented"

        result = guard_fn(**kwargs)
        if isinstance(result, tuple):
            allowed, reason = result
        else:
            allowed, reason = bool(result), ""

        if allowed:
            self._apply_transition(to_state)
            return True, reason

        return False, reason

    def _apply_transition(self, to_state: FeedbackState) -> None:
        self._history.append({
            "from": self._current.value,
            "to": to_state.value,
        })
        self._current = to_state
        if to_state == FeedbackState.ERROR:
            self._error = "Transition to ERROR state"

    def force_set(self, state: FeedbackState, error: Optional[str] = None) -> None:
        """Force-set state for testing or recovery."""
        self._current = state
        if error:
            self._error = error

    def can_transition(self, to_state: FeedbackState) -> bool:
        """Check if a transition is registered."""
        return (self._current, to_state) in TRANSITIONS

    def is_error(self) -> bool:
        return self._current == FeedbackState.ERROR

    def is_cooldown(self) -> bool:
        return self._current == FeedbackState.COOLDOWN

    def is_idle(self) -> bool:
        return self._current == FeedbackState.IDLE
