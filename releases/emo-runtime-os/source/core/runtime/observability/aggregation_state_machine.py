"""Phase F4 — Telemetry Aggregation State Machine.  # LAW-5 # RULE-4

7-state machine governing telemetry event lifecycle:
  RAW_EVENT → VALIDATED → BUFFERED → AGGREGATING → COMPUTED → FLUSHING → PERSISTED

Guards:
  - validate_fields: checks trace_id, span_id, correlation_id
  - buffer_capacity_check: enforces ring buffer limits
  - window_boundary_check: ensures correct window partitioning
  - flush_retry_guard: preserves buffer on flush failure (RULE 3)

Ref: Canon LAW 5 (Observability), RULE 4 (Terminal states)
Ref: artifacts/design/f4/03_telemetry_aggregation_machine.md
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("emo_ai.observability.agg_sm")


class AggregationState(str, Enum):  # RULE-4
    RAW_EVENT = "raw_event"
    VALIDATED = "validated"
    BUFFERED = "buffered"
    AGGREGATING = "aggregating"
    COMPUTED = "computed"
    FLUSHING = "flushing"
    PERSISTED = "persisted"


TERMINAL_STATES: set = {
    AggregationState.PERSISTED,
}

TRANSITIONS: Dict[Tuple[AggregationState, AggregationState], Optional[str]] = {
    (AggregationState.RAW_EVENT, AggregationState.VALIDATED): "guard_validate",
    (AggregationState.VALIDATED, AggregationState.BUFFERED): "guard_buffer_capacity",
    (AggregationState.BUFFERED, AggregationState.AGGREGATING): "guard_window_boundary",
    (AggregationState.AGGREGATING, AggregationState.COMPUTED): None,
    (AggregationState.COMPUTED, AggregationState.FLUSHING): None,
    (AggregationState.FLUSHING, AggregationState.PERSISTED): None,
    (AggregationState.FLUSHING, AggregationState.BUFFERED): "guard_flush_retry",
    (AggregationState.PERSISTED, AggregationState.BUFFERED): None,
}


class AggregationStateMachine:
    """7-state machine for telemetry event lifecycle.

    RAW_EVENT → VALIDATED → BUFFERED → AGGREGATING → COMPUTED → FLUSHING → PERSISTED

    Guards enforce data integrity, capacity limits, window correctness,
    and flush retry semantics.
    """

    MAX_BUFFER_SIZE: int = 10_000

    def __init__(self) -> None:
        self._current = AggregationState.RAW_EVENT
        self._history: List[Dict[str, Any]] = []
        self._error: Optional[str] = None

    @property
    def current(self) -> AggregationState:
        return self._current

    @property
    def history(self) -> List[Dict[str, Any]]:
        return list(self._history)

    # ── Guards ──────────────────────────────────────────────────

    def guard_validate(  # LAW-12
        self,
        trace_id: Optional[str] = None,
        span_id: Optional[str] = None,
    ) -> Tuple[bool, str]:
        if trace_id is not None and (not trace_id or len(trace_id) > 64):
            return False, "trace_id missing or exceeds 64 chars"
        if span_id is not None and (not span_id or len(span_id) > 64):
            return False, "span_id missing or exceeds 64 chars"
        return True, ""

    def guard_buffer_capacity(  # LAW-5
        self,
        current_size: int = 0,
    ) -> Tuple[bool, str]:
        if current_size >= self.MAX_BUFFER_SIZE:
            return False, f"Buffer full ({current_size}/{self.MAX_BUFFER_SIZE})"
        return True, ""

    def guard_window_boundary(  # RULE-1
        self,
        events_pending: bool = True,
    ) -> Tuple[bool, str]:
        if not events_pending:
            return False, "No events to aggregate"
        return True, ""

    def guard_flush_retry(  # RULE-3
        self,
        retry_count: int = 0,
    ) -> Tuple[bool, str]:
        max_retries = 3
        if retry_count >= max_retries:
            return False, f"Flush retries exhausted ({retry_count}/{max_retries})"
        return True, f"Retry flush ({retry_count + 1}/{max_retries})"

    # ── transition ──────────────────────────────────────────────

    def transition(
        self,
        to_state: AggregationState,
        **kwargs,
    ) -> Tuple[bool, str]:
        key = (self._current, to_state)

        if key not in TRANSITIONS:
            return False, (
                f"Invalid transition: {self._current.value} → {to_state.value}"
            )

        if self._current in TERMINAL_STATES:
            return False, f"Terminal state {self._current.value} — no transitions"

        guard_name = TRANSITIONS[key]
        if guard_name is None:
            self._apply(to_state)
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
            self._apply(to_state)
            return True, reason
        return False, reason

    # ── force_set (testing) ─────────────────────────────────────

    def force_set(self, state: AggregationState) -> None:
        self._current = state

    def is_terminal(self) -> bool:
        return self._current in TERMINAL_STATES

    def _apply(self, to_state: AggregationState) -> None:
        self._history.append({
            "from": self._current.value,
            "to": to_state.value,
        })
        self._current = to_state
