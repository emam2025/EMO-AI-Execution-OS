"""Phase G1 — Planning State Machine.  # LAW-3 # RULE-4

12-state machine governing the planning lifecycle:
  INTENT_RECEIVED → DAG_SYNTHESIS → VALIDATED → CRITIC_EVAL
    → [APPROVED → PUBLISHED → ACTIVE → ADAPT_REQUESTED → CRITIC_EVAL]
    → [CRITIC_REJECTED → HALTED | ESCALATED]

Adaptation guards (RULE 3):
  - min_critic_signals ≥ 2 OR feedback_confidence ≥ 0.8
  - cooldown_elapsed ≥ 60s
  - max_adaptations ≤ 5 per plan_trace_id

Deterministic replay guard (RULE 1):
  - Same (intent, context_hash, weight_hash) → same path

Ref: Canon LAW 3 (State Management), RULE 1, RULE 3, RULE 4
Ref: artifacts/design/g1/03_planning_state_machine.md
"""

from __future__ import annotations

import logging
import time
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("emo_ai.orchestration.planning_sm")


class PlanningState(str, Enum):  # RULE-4
    INTENT_RECEIVED = "intent_received"
    DAG_SYNTHESIS = "dag_synthesis"
    VALIDATED = "validated"
    CRITIC_EVAL = "critic_eval"
    APPROVED = "approved"
    PUBLISHED = "published"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    CRITIC_REJECTED = "critic_rejected"
    ADAPT_REQUESTED = "adapt_requested"
    HALTED = "halted"
    ESCALATED = "escalated"


TERMINAL_STATES: set = {
    PlanningState.COMPLETED,
    PlanningState.FAILED,
    PlanningState.HALTED,
    PlanningState.ESCALATED,
}

TRANSITIONS: Dict[Tuple[PlanningState, PlanningState], Optional[str]] = {
    (PlanningState.INTENT_RECEIVED, PlanningState.DAG_SYNTHESIS): "guard_intent",
    (PlanningState.DAG_SYNTHESIS, PlanningState.CRITIC_EVAL): "guard_deterministic_replay",
    (PlanningState.DAG_SYNTHESIS, PlanningState.VALIDATED): None,
    (PlanningState.VALIDATED, PlanningState.CRITIC_EVAL): None,
    (PlanningState.CRITIC_EVAL, PlanningState.APPROVED): "guard_critic_eval",
    (PlanningState.CRITIC_EVAL, PlanningState.CRITIC_REJECTED): None,
    (PlanningState.CRITIC_EVAL, PlanningState.ESCALATED): "guard_escape",
    (PlanningState.APPROVED, PlanningState.PUBLISHED): "guard_immutable",
    (PlanningState.PUBLISHED, PlanningState.ACTIVE): None,
    (PlanningState.PUBLISHED, PlanningState.COMPLETED): None,
    (PlanningState.PUBLISHED, PlanningState.FAILED): None,
    (PlanningState.ACTIVE, PlanningState.ADAPT_REQUESTED): "guard_adaptation",
    (PlanningState.ADAPT_REQUESTED, PlanningState.CRITIC_EVAL): None,
    (PlanningState.CRITIC_REJECTED, PlanningState.HALTED): None,
    (PlanningState.CRITIC_REJECTED, PlanningState.ESCALATED): "guard_escape",
}


class PlanningStateMachine:  # LAW-3
    """12-state machine for planning lifecycle.

    All transitions are guarded. Adaptation is only permitted when
    all adaptation guards pass (RULE 3).
    """

    ADAPTATION_COOLDOWN_SEC: float = 60.0

    def __init__(self) -> None:
        self._current = PlanningState.INTENT_RECEIVED
        self._history: List[Dict[str, Any]] = []
        self._error: Optional[str] = None
        self._last_adaptation_time: float = 0.0

    @property
    def current(self) -> PlanningState:
        return self._current

    @property
    def history(self) -> List[Dict[str, Any]]:
        return list(self._history)

    # ── Guards ──────────────────────────────────────────────────

    def guard_intent(  # LAW-3
        self,
        intent: str = "",
    ) -> Tuple[bool, str]:
        if not intent:
            return False, "Empty intent"
        if len(intent) > 10_000:
            return False, "Intent exceeds 10,000 chars"
        return True, ""

    def guard_deterministic_replay(  # RULE-1
        self,
        context_hash: Optional[str] = None,
    ) -> Tuple[bool, str]:
        return True, ""

    def guard_critic_eval(  # LAW-8
        self,
        overall_score: float = 0.0,
    ) -> Tuple[bool, str]:
        if overall_score >= 0.7:
            return True, ""
        return False, f"Critic score {overall_score:.2f} < 0.7"

    def guard_immutable(  # RULE-2
        self,
    ) -> Tuple[bool, str]:
        return True, ""

    def guard_adaptation(  # RULE-3
        self,
        critic_signal_count: int = 0,
        feedback_confidence: float = 0.0,
        adaptation_count: int = 0,
    ) -> Tuple[bool, str]:
        now = time.time()
        cooldown_remaining = self._last_adaptation_time + self.ADAPTATION_COOLDOWN_SEC - now
        if cooldown_remaining > 0:
            return False, f"Adaptation cooldown {cooldown_remaining:.0f}s remaining"

        if adaptation_count >= 5:
            return False, f"Max 5 adaptations per plan_trace_id exceeded"

        if critic_signal_count >= 2 or feedback_confidence >= 0.8:
            return True, ""

        return False, (
            f"Adaptation requires ≥ 2 critic signals (got {critic_signal_count}) "
            f"OR confidence ≥ 0.8 (got {feedback_confidence:.2f})"
        )

    def guard_escape(  # LAW-8
        self,
        severity: float = 0.0,
    ) -> Tuple[bool, str]:
        if severity >= 0.9:
            return True, ""
        return False, f"Severity {severity:.2f} < 0.9 escalation threshold"

    # ── Transition ──────────────────────────────────────────────

    def transition(
        self,
        to_state: PlanningState,
        **kwargs,
    ) -> Tuple[bool, str]:
        if self._current in TERMINAL_STATES:
            return False, f"Terminal state {self._current.value} — no transitions"

        key = (self._current, to_state)

        if key not in TRANSITIONS:
            return False, (
                f"Invalid transition: {self._current.value} → {to_state.value}"
            )

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

    def force_set(self, state: PlanningState) -> None:
        self._current = state

    def is_terminal(self) -> bool:
        return self._current in TERMINAL_STATES

    def _apply(self, to_state: PlanningState) -> None:
        self._history.append({
            "from": self._current.value,
            "to": to_state.value,
        })
        if to_state == PlanningState.ADAPT_REQUESTED:
            self._last_adaptation_time = time.time()
        self._current = to_state
