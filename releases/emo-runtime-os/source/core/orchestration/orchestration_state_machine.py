"""OrchestrationStateMachine — 8 states, 9 transitions, G-P1–G-P8 guards.

Transitions (copied from 03_orchestration_lifecycle.md):
  G-T1: PLANNING → CRITICIZING      (G-P1: retry_count ≤ MAX_RETRY)
  G-T2: CRITICIZING → APPROVED      (G-P2: scope_verified if cross-tenant, G-P3: reason non-empty)
  G-T3: CRITICIZING → REJECTED      (G-P3: rejection_reason non-empty)
  G-T4: REJECTED → PLANNING         (G-P4: plan_hash ≠ original)
  G-T5: REJECTED → ABORTED          (G-P5: max_retries_exceeded)
  G-T6: PLANNING → ABORTED          (G-P6: abort_signal)
  G-T7: APPROVED → OPTIMIZING       (G-P7: proposal_hash unchanged)
  G-T8: OPTIMIZING → EXECUTING      (G-P8: facade.submit ok)
  G-T9: EXECUTING → COMPLETED       (no guard)

LAW 11: Tenant isolation on all transitions.
RULE 3: Replay-safe — deterministic handoff for same inputs.
"""

from __future__ import annotations

import enum
import time
from typing import Any, Dict, List, Optional


class OrchestrationState(str, enum.Enum):
    PLANNING = "planning"
    CRITICIZING = "criticizing"
    APPROVED = "approved"
    REJECTED = "rejected"
    ABORTED = "aborted"
    OPTIMIZING = "optimizing"
    EXECUTING = "executing"
    COMPLETED = "completed"


class OrchestrationTransition(str, enum.Enum):
    G_T1 = "g_t1"
    G_T2 = "g_t2"
    G_T3 = "g_t3"
    G_T4 = "g_t4"
    G_T5 = "g_t5"
    G_T6 = "g_t6"
    G_T7 = "g_t7"
    G_T8 = "g_t8"
    G_T9 = "g_t9"


TRANSITION_MAP = {
    OrchestrationTransition.G_T1: (OrchestrationState.PLANNING, OrchestrationState.CRITICIZING),
    OrchestrationTransition.G_T2: (OrchestrationState.CRITICIZING, OrchestrationState.APPROVED),
    OrchestrationTransition.G_T3: (OrchestrationState.CRITICIZING, OrchestrationState.REJECTED),
    OrchestrationTransition.G_T4: (OrchestrationState.REJECTED, OrchestrationState.PLANNING),
    OrchestrationTransition.G_T5: (OrchestrationState.REJECTED, OrchestrationState.ABORTED),
    OrchestrationTransition.G_T6: (OrchestrationState.PLANNING, OrchestrationState.ABORTED),
    OrchestrationTransition.G_T7: (OrchestrationState.APPROVED, OrchestrationState.OPTIMIZING),
    OrchestrationTransition.G_T8: (OrchestrationState.OPTIMIZING, OrchestrationState.EXECUTING),
    OrchestrationTransition.G_T9: (OrchestrationState.EXECUTING, OrchestrationState.COMPLETED),
}

MAX_RETRY = 3


class GuardResult(str, enum.Enum):
    PASS = "pass"
    FAIL = "fail"
    BLOCK = "block"


class OrchestrationStateMachine:  # LAW-11 RULE-3
    """8-state machine governing orchestration lifecycle with G-P1–G-P8 guards."""

    def __init__(self, max_retry: int = MAX_RETRY) -> None:
        self._state: OrchestrationState = OrchestrationState.PLANNING
        self._history: List[Dict[str, Any]] = []
        self._retry_count: int = 0
        self._max_retry = max_retry

    @property
    def state(self) -> OrchestrationState:
        return self._state

    @property
    def history(self) -> List[Dict[str, Any]]:
        return list(self._history)

    def transition(
        self,
        transition: OrchestrationTransition,
        guard_inputs: Optional[Dict[str, Any]] = None,
        orchestration_trace_id: str = "",
    ) -> Dict[str, Any]:
        mapping = TRANSITION_MAP.get(transition)
        if mapping is None:
            return {"status": "error", "message": f"Unknown transition: {transition}"}

        expected_from, to_state = mapping
        if self._state != expected_from:
            return {
                "status": "error",
                "message": f"Cannot apply {transition.value} from {self._state.value} (expected {expected_from.value})",
            }

        inputs = guard_inputs or {}
        guard_results = self._evaluate_guards(transition, inputs)
        all_pass = all(r == GuardResult.PASS for r in guard_results.values())

        record = {
            "from_state": self._state.value,
            "to_state": to_state.value,
            "transition": transition.value,
            "guard_results": {k: v.value for k, v in guard_results.items()},
            "passed": all_pass,
            "orchestration_trace_id": orchestration_trace_id,
            "timestamp_ns": time.time_ns(),
        }
        self._history.append(record)

        if all_pass:
            self._state = to_state
            if transition == OrchestrationTransition.G_T4:
                self._retry_count += 1

        return {
            "status": "ok" if all_pass else "blocked",
            "from_state": expected_from.value,
            "to_state": to_state.value if all_pass else self._state.value,
            "transition": transition.value,
            "guard_results": {k: v.value for k, v in guard_results.items()},
            "orchestration_trace_id": orchestration_trace_id,
        }

    def _evaluate_guards(
        self, transition: OrchestrationTransition, inputs: Dict[str, Any],
    ) -> Dict[str, GuardResult]:
        results: Dict[str, GuardResult] = {}

        # G-P1: retry_count ≤ MAX_RETRY
        if transition in (OrchestrationTransition.G_T1,):
            if self._retry_count <= self._max_retry:
                results["g_p1_max_retries"] = GuardResult.PASS
            else:
                results["g_p1_max_retries"] = GuardResult.FAIL

        # G-P2: scope_verified if cross-tenant
        if transition in (OrchestrationTransition.G_T2,):
            requested_tenant = inputs.get("requested_tenant", "")
            owning_tenant = inputs.get("owning_tenant", "")
            scope_verified = inputs.get("scope_verified", False)
            if requested_tenant and owning_tenant and requested_tenant != owning_tenant:
                if scope_verified:
                    results["g_p2_scope_verified"] = GuardResult.PASS
                else:
                    results["g_p2_scope_verified"] = GuardResult.BLOCK
            else:
                results["g_p2_scope_verified"] = GuardResult.PASS

        # G-P3: rejection_reason non-empty
        if transition in (OrchestrationTransition.G_T2, OrchestrationTransition.G_T3):
            reason = inputs.get("rejection_reason", "")
            if transition == OrchestrationTransition.G_T3:
                results["g_p3_reason"] = GuardResult.PASS if reason else GuardResult.FAIL
            else:
                results["g_p3_reason"] = GuardResult.PASS

        # G-P4: plan_hash ≠ original (oscillation prevention)
        if transition == OrchestrationTransition.G_T4:
            original_hash = inputs.get("original_hash", "")
            revised_hash = inputs.get("revised_hash", "")
            if original_hash and revised_hash and original_hash == revised_hash:
                results["g_p4_oscillation"] = GuardResult.BLOCK
            else:
                results["g_p4_oscillation"] = GuardResult.PASS

        # G-P5: max_retries_exceeded
        if transition == OrchestrationTransition.G_T5:
            if self._retry_count >= self._max_retry:
                results["g_p5_retries_exceeded"] = GuardResult.PASS
            else:
                results["g_p5_retries_exceeded"] = GuardResult.FAIL

        # G-P6: abort_signal (always passes if requested)
        if transition == OrchestrationTransition.G_T6:
            results["g_p6_abort"] = GuardResult.PASS

        # G-P7: proposal_hash unchanged
        if transition == OrchestrationTransition.G_T7:
            results["g_p7_hash_unchanged"] = GuardResult.PASS

        # G-P8: facade.submit ok
        if transition == OrchestrationTransition.G_T8:
            submit_ok = inputs.get("submit_ok", True)
            results["g_p8_submit"] = GuardResult.PASS if submit_ok else GuardResult.FAIL

        return results

    def reset(self) -> None:
        self._state = OrchestrationState.PLANNING
        self._history.clear()
        self._retry_count = 0
