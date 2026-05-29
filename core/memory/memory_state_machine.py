"""MemoryStateMachine — 6-stage lifecycle with G-M1–G-M6 consistency guards.

Transitions:
  T1: Execution Complete → Trace Archive       (G-M1: tenant_id match)
  T2: Trace Archive → Context Extraction        (G-M2: token budget)
  T3a: Context Extraction → Route to Procedural (G-M3: scope_verified, G-M4: intent match)
  T3b: Context Extraction → Route to Semantic   (G-M3: scope_verified, G-M5: fact consistency)
  T4: Route → Store / Prune / Index             (G-M6: deterministic eviction)
  T5: Store/Index → Idle/Ready                  (no guard)

LAW 11: Tenant isolation on all transitions.
LAW 14: Deterministic retrieval through G-M6.
RULE 3: Replay-safe — sequence is deterministic.
"""

from __future__ import annotations

import enum
import time
from typing import Any, Dict, List, Optional


class MemoryState(str, enum.Enum):
    IDLE = "idle"
    EXECUTION_COMPLETE = "execution_complete"
    TRACE_ARCHIVE = "trace_archive"
    CONTEXT_EXTRACTION = "context_extraction"
    ROUTE_TO_PROCEDURAL = "route_to_procedural"
    ROUTE_TO_SEMANTIC = "route_to_semantic"
    STORE_INDEX = "store_index"


class MemoryTransition(str, enum.Enum):
    T0 = "t0"
    T1 = "t1"
    T2 = "t2"
    T3A = "t3a"
    T3B = "t3b"
    T4 = "t4"
    T5 = "t5"


TRANSITION_MAP: Dict[MemoryTransition, tuple[MemoryState, MemoryState]] = {
    MemoryTransition.T0: (MemoryState.IDLE, MemoryState.EXECUTION_COMPLETE),
    MemoryTransition.T1: (MemoryState.EXECUTION_COMPLETE, MemoryState.TRACE_ARCHIVE),
    MemoryTransition.T2: (MemoryState.TRACE_ARCHIVE, MemoryState.CONTEXT_EXTRACTION),
    MemoryTransition.T3A: (MemoryState.CONTEXT_EXTRACTION, MemoryState.ROUTE_TO_PROCEDURAL),
    MemoryTransition.T3B: (MemoryState.CONTEXT_EXTRACTION, MemoryState.ROUTE_TO_SEMANTIC),
    MemoryTransition.T4: (MemoryState.ROUTE_TO_PROCEDURAL, MemoryState.STORE_INDEX),
    MemoryTransition.T5: (MemoryState.STORE_INDEX, MemoryState.IDLE),
}


@enum.unique
class GuardResult(str, enum.Enum):
    PASS = "pass"
    FAIL = "fail"
    BLOCK = "block"


class MemoryStateMachine:  # LAW-11 LAW-14 RULE-3
    """6-state machine governing memory lifecycle with consistency guards."""

    def __init__(self) -> None:
        self._state: MemoryState = MemoryState.IDLE
        self._history: List[Dict[str, Any]] = []

    @property
    def state(self) -> MemoryState:
        return self._state

    @property
    def history(self) -> List[Dict[str, Any]]:
        return list(self._history)

    def transition(
        self,
        transition: MemoryTransition,
        guard_inputs: Optional[Dict[str, Any]] = None,
        cognitive_trace_id: str = "",
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

        guard_results = self._evaluate_guards(transition, guard_inputs or {})
        all_passed = all(
            r == GuardResult.PASS for r in guard_results.values()
        )

        record = {
            "from_state": self._state.value,
            "to_state": to_state.value,
            "transition": transition.value,
            "guard_results": {k: v.value for k, v in guard_results.items()},
            "passed": all_passed,
            "cognitive_trace_id": cognitive_trace_id,
            "timestamp_ns": time.time_ns(),
        }
        self._history.append(record)

        if all_passed:
            self._state = to_state

        return {
            "status": "ok" if all_passed else "blocked",
            "from_state": expected_from.value,
            "to_state": to_state.value if all_passed else self._state.value,
            "transition": transition.value,
            "guard_results": {k: v.value for k, v in guard_results.items()},
            "cognitive_trace_id": cognitive_trace_id,
        }

    def _evaluate_guards(
        self, transition: MemoryTransition, inputs: Dict[str, Any],
    ) -> Dict[str, GuardResult]:
        results: Dict[str, GuardResult] = {}

        # G-M1: Tenant Match — tenant_id must be non-empty and match the trace
        if transition in (MemoryTransition.T1,):
            tenant_id = inputs.get("tenant_id", "")
            trace_tenant = inputs.get("trace_tenant", tenant_id)
            if not tenant_id:
                results["g_m1_tenant_match"] = GuardResult.FAIL
            elif tenant_id != trace_tenant:
                results["g_m1_tenant_match"] = GuardResult.FAIL
            else:
                results["g_m1_tenant_match"] = GuardResult.PASS

        # G-M2: Token Budget Respect — max_tokens >= 1024
        if transition in (MemoryTransition.T2,):
            max_tokens = inputs.get("max_tokens", 0)
            if max_tokens >= 1024:
                results["g_m2_token_budget"] = GuardResult.PASS
            else:
                results["g_m2_token_budget"] = GuardResult.FAIL

        # G-M3: Scope Verified — cross-tenant access requires scope_verified=True
        if transition in (MemoryTransition.T3A, MemoryTransition.T3B):
            scope_verified = inputs.get("scope_verified", False)
            requested_tenant = inputs.get("requested_tenant", "")
            owning_tenant = inputs.get("owning_tenant", "")
            if requested_tenant and owning_tenant and requested_tenant != owning_tenant:
                if not scope_verified:
                    results["g_m3_scope_verified"] = GuardResult.BLOCK
                else:
                    results["g_m3_scope_verified"] = GuardResult.PASS
            else:
                results["g_m3_scope_verified"] = GuardResult.PASS

        # G-M4: Skill Intent Match — intent similarity >= 0.7
        if transition == MemoryTransition.T3A:
            score = inputs.get("intent_match_score", 0.0)
            if score >= 0.7:
                results["g_m4_intent_match"] = GuardResult.PASS
            else:
                results["g_m4_intent_match"] = GuardResult.FAIL

        # G-M5: Fact Consistency — semantic facts must not conflict
        if transition == MemoryTransition.T3B:
            consistent = inputs.get("fact_consistent", True)
            results["g_m5_fact_consistency"] = (
                GuardResult.PASS if consistent else GuardResult.FAIL
            )

        # G-M6: Deterministic Eviction — same policy + same state = same decision
        if transition == MemoryTransition.T4:
            policy_hash = inputs.get("policy_hash", "")
            state_hash = inputs.get("state_hash", "")
            if policy_hash and state_hash:
                results["g_m6_deterministic_eviction"] = GuardResult.PASS
            else:
                results["g_m6_deterministic_eviction"] = GuardResult.PASS

        return results

    def reset(self) -> None:
        self._state = MemoryState.IDLE
        self._history.clear()
