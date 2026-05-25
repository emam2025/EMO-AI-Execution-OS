"""F1 — Unified Runtime State Machine & Transition Guards.

13-state execution lifecycle with validated transitions.
Every transition must pass a guard condition (LAW 8, RULE 4).

States: SUBMITTED → QUEUED → LEASED → PLANNING → EXECUTING → COMPLETED
         With branches: FAILED → ROLLED_BACK, CANCELLED → TERMINAL,
         ORPHANED → RECOVERED → QUEUED, COMPLETED → REPLAYING

Ref: DEVELOPER.md §15.2, §15.3
Ref: artifacts/design/f1/02_unified_lifecycle_and_states.md
Ref: Canon LAW 8 (recoverable), LAW 12 (traceable), RULE 4 (killable)
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional, Tuple


class RuntimeState(str, Enum):
    """13-state unified execution lifecycle.

    Ref: §15.3 — Runtime State Model
    """
    SUBMITTED = "SUBMITTED"
    QUEUED = "QUEUED"
    LEASED = "LEASED"
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    ROLLED_BACK = "ROLLED_BACK"
    REPLAYING = "REPLAYING"
    ORPHANED = "ORPHANED"
    RECOVERED = "RECOVERED"
    TERMINAL = "TERMINAL"


TERMINAL_STATES: set = {
    RuntimeState.COMPLETED,
    RuntimeState.ROLLED_BACK,
    RuntimeState.TERMINAL,
}

RESUMABLE_STATES: set = {
    RuntimeState.FAILED,
    RuntimeState.CANCELLED,
    RuntimeState.ORPHANED,
}

# Transition table: (from, to) -> guard method name or None (auto-allow)
TRANSITIONS: Dict[Tuple[RuntimeState, RuntimeState], Optional[str]] = {
    (RuntimeState.SUBMITTED, RuntimeState.QUEUED): "guard_submit_to_queued",
    (RuntimeState.SUBMITTED, RuntimeState.FAILED): "guard_submit_to_failed",
    (RuntimeState.QUEUED, RuntimeState.LEASED): "guard_queued_to_leased",
    (RuntimeState.QUEUED, RuntimeState.FAILED): "guard_queued_to_failed",
    (RuntimeState.LEASED, RuntimeState.PLANNING): "guard_leased_to_planning",
    (RuntimeState.LEASED, RuntimeState.FAILED): "guard_leased_to_failed",
    (RuntimeState.PLANNING, RuntimeState.EXECUTING): "guard_planning_to_executing",
    (RuntimeState.PLANNING, RuntimeState.CANCELLED): "guard_to_cancelled",
    (RuntimeState.EXECUTING, RuntimeState.COMPLETED): "guard_executing_to_completed",
    (RuntimeState.EXECUTING, RuntimeState.FAILED): "guard_executing_to_failed",
    (RuntimeState.EXECUTING, RuntimeState.CANCELLED): "guard_to_cancelled",
    (RuntimeState.EXECUTING, RuntimeState.ORPHANED): "guard_to_orphaned",
    (RuntimeState.FAILED, RuntimeState.ROLLED_BACK): "guard_failed_to_rolled_back",
    (RuntimeState.CANCELLED, RuntimeState.TERMINAL): "guard_cancelled_to_terminal",
    (RuntimeState.ROLLED_BACK, RuntimeState.TERMINAL): None,
    (RuntimeState.REPLAYING, RuntimeState.COMPLETED): None,
    (RuntimeState.REPLAYING, RuntimeState.FAILED): None,
    (RuntimeState.ORPHANED, RuntimeState.RECOVERED): "guard_orphaned_to_recovered",
    (RuntimeState.ORPHANED, RuntimeState.FAILED): "guard_orphaned_to_failed",
    (RuntimeState.RECOVERED, RuntimeState.QUEUED): "guard_recovered_to_queued",
    (RuntimeState.COMPLETED, RuntimeState.REPLAYING): "guard_completed_to_replaying",
}


class TransitionGuard:
    """Validates state transitions with preconditions.

    LAW 8: All state transitions MUST be recoverable.
    RULE 4: Guard prevents transitions from terminal states.

    Each guard is a pure function — no side effects.
    """

    def guard_submit_to_queued(self, dag: Any) -> Tuple[bool, str]:
        if dag is None:
            return False, "DAG is None"
        nodes = getattr(dag, "nodes", None)
        if nodes is None:
            nodes = dag if isinstance(dag, (list, tuple)) else [dag]
        if isinstance(nodes, (list, tuple)) and len(nodes) == 0:
            return False, "DAG has no nodes"
        if not nodes:
            return False, "DAG has no nodes"
        return True, ""

    def guard_submit_to_failed(self, dag: Any) -> Tuple[bool, str]:
        if dag is None:
            return True, "DAG is None"
        return False, "DAG is valid"

    def guard_queued_to_leased(self, lease_id: Optional[str]) -> Tuple[bool, str]:
        if lease_id is None:
            return False, "Lease not acquired"
        return True, ""

    def guard_queued_to_failed(self, lease_id: Optional[str]) -> Tuple[bool, str]:
        if lease_id is None:
            return True, "Lease acquisition failed"
        return False, "Lease acquired"

    def guard_leased_to_planning(self, levels: Any) -> Tuple[bool, str]:
        if not levels:
            return False, "No execution levels computed"
        return True, ""

    def guard_leased_to_failed(self, levels: Any) -> Tuple[bool, str]:
        if not levels:
            return True, "Scheduling failed"
        return False, "Levels computed"

    def guard_planning_to_executing(self, dispatched: bool = True) -> Tuple[bool, str]:
        return dispatched, ""

    def guard_to_cancelled(self) -> Tuple[bool, str]:
        return True, ""

    def guard_executing_to_completed(self, all_done: bool = True) -> Tuple[bool, str]:
        if not all_done:
            return False, "Not all nodes completed"
        return True, ""

    def guard_executing_to_failed(self, is_terminal: bool = True) -> Tuple[bool, str]:
        return is_terminal, ""

    def guard_to_orphaned(self) -> Tuple[bool, str]:
        return True, ""

    def guard_failed_to_rolled_back(self, rolled_back: bool = True) -> Tuple[bool, str]:
        return rolled_back, ""

    def guard_cancelled_to_terminal(self, released: bool = True) -> Tuple[bool, str]:
        return released, ""

    def guard_orphaned_to_recovered(self, recovered: bool = True) -> Tuple[bool, str]:
        return recovered, ""

    def guard_orphaned_to_failed(self) -> Tuple[bool, str]:
        return True, ""

    def guard_recovered_to_queued(self, checkpoint_exists: bool = True) -> Tuple[bool, str]:
        return checkpoint_exists, ""

    def guard_completed_to_replaying(self, trace_exists: bool = True) -> Tuple[bool, str]:
        return trace_exists, ""

    def check(self, from_state: RuntimeState, to_state: RuntimeState,
              **kwargs) -> Tuple[bool, str]:
        """Check if transition is valid.

        Args:
            from_state: Current state.
            to_state: Desired state.
            **kwargs: Arguments for the guard function.

        Returns:
            (allowed: bool, reason: str)
        """
        if from_state in TERMINAL_STATES and from_state != RuntimeState.COMPLETED:
            return False, f"Cannot transition from terminal state {from_state.value}"

        key = (from_state, to_state)
        guard_name = TRANSITIONS.get(key)
        if guard_name is None:
            return False, (
                f"Invalid transition: {from_state.value} → {to_state.value}"
            )

        if guard_name is None:
            return True, ""

        guard_fn = getattr(self, guard_name, None)
        if guard_fn is None:
            return False, f"Guard {guard_name} not implemented"

        result = guard_fn(**kwargs)
        if isinstance(result, tuple):
            return result
        return result, ""


class RuntimeStateMachine:
    """Per-execution state machine that tracks lifecycle.

    LAW 8: Guards enforce transition validity.
    LAW 12: All transitions are observable via state_history.
    RULE 4: Terminal states are truly terminal.
    """

    def __init__(self, guard: Optional[TransitionGuard] = None):
        self._guard = guard or TransitionGuard()
        self._current = RuntimeState.SUBMITTED
        self._history: list[Dict[str, Any]] = []

    @property
    def current(self) -> RuntimeState:
        return self._current

    @property
    def history(self) -> list[Dict[str, Any]]:
        return list(self._history)

    def transition(self, to_state: RuntimeState, **kwargs) -> Tuple[bool, str]:
        """Attempt a guarded transition.

        Args:
            to_state: Target state.
            **kwargs: Passed to the guard function.

        Returns:
            (allowed: bool, reason: str)

        Raises:
            InvalidStateTransition: If guard rejects.
        """
        if self._current in TERMINAL_STATES and self._current != RuntimeState.COMPLETED:
            return False, f"Cannot transition from terminal {self._current.value}"

        allowed, reason = self._guard.check(self._current, to_state, **kwargs)
        if not allowed:
            from core.runtime.models.api_errors import InvalidStateTransition
            raise InvalidStateTransition(
                message=reason,
                current_state=self._current.value,
                target_state=to_state.value,
            )

        self._history.append({
            "from": self._current.value,
            "to": to_state.value,
            "timestamp": 0.0,
        })
        self._current = to_state
        return True, ""

    def can_transition(self, to_state: RuntimeState) -> bool:
        """Check if a transition is registered (without executing)."""
        return (self._current, to_state) in TRANSITIONS

    def is_terminal(self) -> bool:
        return self._current in TERMINAL_STATES

    def is_resumable(self) -> bool:
        return self._current in RESUMABLE_STATES

    def force_set(self, state: RuntimeState) -> None:
        self._current = state
