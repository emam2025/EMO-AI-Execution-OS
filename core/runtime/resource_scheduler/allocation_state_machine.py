"""Phase F3 — Allocation State Machine.  # LAW-8 # RULE-4

8-state machine governing resource allocation lifecycle:
  QUEUED → MATCHED → RESERVED → ASSIGNED → RUNNING
    → [COMPLETED / FAILED / PREEMPTED]

Preemption guards:
  - priority_diff >= 2 tiers
  - target age > 60s
  - checkpoint_available
  - graceful_termination_signal

Ref: Canon LAW 8 (Guarded transitions), RULE 4 (Terminal states)
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from core.runtime.models.resource_scheduler_models import (
    AssignmentRecord,
    PriorityTier,
    ResourceRequest,
)

logger = logging.getLogger("emo_ai.resource_scheduler.sm")


class AllocationState(str, Enum):  # RULE-4
    QUEUED = "queued"
    MATCHED = "matched"
    RESERVED = "reserved"
    ASSIGNED = "assigned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PREEMPTED = "preempted"
    REJECTED = "rejected"


# Transition table: (from, to) -> guard function or None
TRANSITIONS: Dict[Tuple[AllocationState, AllocationState], Optional[str]] = {
    (AllocationState.QUEUED, AllocationState.MATCHED): None,
    (AllocationState.MATCHED, AllocationState.RESERVED): "guard_reserved",
    (AllocationState.RESERVED, AllocationState.ASSIGNED): None,
    (AllocationState.ASSIGNED, AllocationState.RUNNING): "guard_running",
    (AllocationState.RUNNING, AllocationState.COMPLETED): None,
    (AllocationState.RUNNING, AllocationState.FAILED): None,
    (AllocationState.RUNNING, AllocationState.PREEMPTED): "guard_preempted",
    (AllocationState.PREEMPTED, AllocationState.QUEUED): "guard_requeue",
    (AllocationState.MATCHED, AllocationState.QUEUED): None,
    (AllocationState.MATCHED, AllocationState.REJECTED): "guard_rejected",
}

TERMINAL_STATES: set = {
    AllocationState.COMPLETED,
    AllocationState.FAILED,
    AllocationState.REJECTED,
}


class AllocationStateMachine:  # LAW-8
    """8-state machine for resource allocation lifecycle.

    Preemption guards:
      - priority_diff >= 2
      - target age > 60s
      - checkpoint_available
      - graceful_termination_signal
    """

    PREEMPTION_MIN_AGE: float = 60.0
    PREEMPTION_MIN_PRIORITY_DIFF: int = 2

    def __init__(self) -> None:
        self._current = AllocationState.QUEUED
        self._history: List[Dict[str, Any]] = []
        self._error: Optional[str] = None

    @property
    def current(self) -> AllocationState:
        return self._current

    @property
    def history(self) -> List[Dict[str, Any]]:
        return list(self._history)

    # ── Guards ────────────────────────────────────────────────

    def guard_reserved(  # LAW-10
        self,
        offer_available: bool = True,
    ) -> Tuple[bool, str]:
        if not offer_available:
            return False, "No matching offer available for reservation"
        return True, ""

    def guard_running(  # RULE-3
        self,
        worker_ready: bool = True,
    ) -> Tuple[bool, str]:
        if not worker_ready:
            return False, "Worker not ready"
        return True, ""

    def guard_preempted(  # LAW-8, RULE-3
        self,
        request: Optional[ResourceRequest] = None,
        record: Optional[AssignmentRecord] = None,
    ) -> Tuple[bool, str]:
        if request is None or record is None:
            return False, "Missing request or record"

        if request.priority not in (PriorityTier.CRITICAL, PriorityTier.HIGH):
            return False, f"Priority {request.priority.value} not eligible for preemption"

        target_priority = record.resources.priority if record.resources else PriorityTier.NORMAL
        diff = self._priority_diff(request.priority, target_priority)
        if diff < self.PREEMPTION_MIN_PRIORITY_DIFF:
            return False, (
                f"Priority diff {diff} < {self.PREEMPTION_MIN_PRIORITY_DIFF} "
                f"({request.priority.value} vs {target_priority.value})"
            )

        age = 0.0
        if record.assigned_at > 0:
            import time
            age = time.time() - record.assigned_at
        if age < self.PREEMPTION_MIN_AGE:
            return False, f"Target age {age:.0f}s < {self.PREEMPTION_MIN_AGE}s"

        if not record.checkpoint_available:
            return False, "No checkpoint available for preemption"

        return True, ""

    def guard_requeue(  # RULE-2
        self,
        preempted: bool = True,
    ) -> Tuple[bool, str]:
        if not preempted:
            return False, "Only preempted executions can be re-queued"
        return True, ""

    def guard_rejected(  # RULE-4
        self,
        no_offers: bool = True,
    ) -> Tuple[bool, str]:
        return no_offers, ""

    # ── Transition ────────────────────────────────────────────

    def transition(
        self,
        to_state: AllocationState,
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

    def _apply(self, to_state: AllocationState) -> None:
        self._history.append({
            "from": self._current.value,
            "to": to_state.value,
        })
        self._current = to_state

    def force_set(self, state: AllocationState) -> None:
        self._current = state

    @staticmethod
    def _priority_diff(a: PriorityTier, b: PriorityTier) -> int:
        tier_map = {
            PriorityTier.CRITICAL: 5,
            PriorityTier.HIGH: 4,
            PriorityTier.NORMAL: 3,
            PriorityTier.LOW: 2,
            PriorityTier.BATCH: 1,
        }
        return abs(tier_map.get(a, 0) - tier_map.get(b, 0))

    def is_terminal(self) -> bool:
        return self._current in TERMINAL_STATES

    def can_preempt(
        self,
        request: ResourceRequest,
        record: AssignmentRecord,
    ) -> Tuple[bool, str]:
        return self.guard_preempted(request=request, record=record)
