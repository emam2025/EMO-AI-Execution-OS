"""Release Certification State Machine.  # LAW-1 LAW-3 LAW-5 LAW-8 LAW-11 LAW-12 RULE-1 RULE-3 RULE-4

Release Freeze state machine governing the final release certification lifecycle:
Collect Reports → Validate Metrics → Check Guards → Freeze Baseline → [Approve / Block / Archive].

Enforces hard guards: canon_compliance == 100%, regressions == 0,
all_critical_guards_passed, architecture_drift == 0, baseline_locked.

Ref: Canon LAW 1-27, RULE 1-5
Ref: DEVELOPER.md §16 (Architecture Canon)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ReleaseState(str, Enum):  # LAW-1 LAW-3
    IDLE = "idle"
    COLLECTING_REPORTS = "collecting_reports"
    VALIDATING_METRICS = "validating_metrics"
    CHECKING_GUARDS = "checking_guards"
    FREEZING_BASELINE = "freezing_baseline"
    APPROVED = "approved"
    BLOCKED = "blocked"
    ARCHIVED = "archived"


class ReleaseTransition(str, Enum):  # LAW-3
    R_T1 = "r_t1"  # IDLE -> COLLECTING_REPORTS
    R_T2 = "r_t2"  # COLLECTING_REPORTS -> VALIDATING_METRICS
    R_T3 = "r_t3"  # VALIDATING_METRICS -> CHECKING_GUARDS
    R_T4 = "r_t4"  # CHECKING_GUARDS -> FREEZING_BASELINE
    R_T5 = "r_t5"  # FREEZING_BASELINE -> APPROVED
    R_T6 = "r_t6"  # CHECKING_GUARDS -> BLOCKED
    R_T7 = "r_t7"  # FREEZING_BASELINE -> BLOCKED
    R_T8 = "r_t8"  # APPROVED -> ARCHIVED
    R_T9 = "r_t9"  # BLOCKED -> IDLE (retry)


VALID_TRANSITIONS: Dict[ReleaseState, Dict[ReleaseTransition, ReleaseState]] = {
    ReleaseState.IDLE: {
        ReleaseTransition.R_T1: ReleaseState.COLLECTING_REPORTS,
    },
    ReleaseState.COLLECTING_REPORTS: {
        ReleaseTransition.R_T2: ReleaseState.VALIDATING_METRICS,
    },
    ReleaseState.VALIDATING_METRICS: {
        ReleaseTransition.R_T3: ReleaseState.CHECKING_GUARDS,
    },
    ReleaseState.CHECKING_GUARDS: {
        ReleaseTransition.R_T4: ReleaseState.FREEZING_BASELINE,
        ReleaseTransition.R_T6: ReleaseState.BLOCKED,
    },
    ReleaseState.FREEZING_BASELINE: {
        ReleaseTransition.R_T5: ReleaseState.APPROVED,
        ReleaseTransition.R_T7: ReleaseState.BLOCKED,
    },
    ReleaseState.APPROVED: {
        ReleaseTransition.R_T8: ReleaseState.ARCHIVED,
    },
    ReleaseState.BLOCKED: {
        ReleaseTransition.R_T9: ReleaseState.IDLE,
    },
}


@dataclass
class FreezeGuardResult:  # LAW-3 RULE-3
    guard_name: str
    passed: bool
    detail: str = ""
    law_refs: List[str] = field(default_factory=list)


@dataclass
class ReleaseTransitionRecord:  # LAW-3 LAW-5
    from_state: ReleaseState
    to_state: ReleaseState
    transition: ReleaseTransition
    guard_results: Dict[str, FreezeGuardResult] = field(default_factory=dict)
    release_trace_id: str = ""
    timestamp_ns: int = field(default_factory=lambda: __import__("time").time_ns())


# ── Guard Evaluators ─────────────────────────────────────────

def evaluate_freeze_guard_canon_compliance(  # RULE-3
    canon_compliance_pct: float = 0.0,
) -> FreezeGuardResult:
    passed = canon_compliance_pct == 100.0
    return FreezeGuardResult(
        guard_name="G-R1_canon_compliance",
        passed=passed,
        detail=f"Canon compliance: {canon_compliance_pct}% (need 100%)",
        law_refs=["LAW-1", "LAW-3", "RULE-1"],
    )


def evaluate_freeze_guard_zero_regressions(  # RULE-3
    regression_count: int = 1,
) -> FreezeGuardResult:
    passed = regression_count == 0
    return FreezeGuardResult(
        guard_name="G-R2_zero_regressions",
        passed=passed,
        detail=f"Regressions: {regression_count} (need 0)",
        law_refs=["LAW-8", "RULE-5"],
    )


def evaluate_freeze_guard_critical_guards(  # RULE-3
    all_guards_passed: bool = False,
) -> FreezeGuardResult:
    return FreezeGuardResult(
        guard_name="G-R3_all_critical_guards",
        passed=all_guards_passed,
        detail=f"All critical guards passed: {all_guards_passed}",
        law_refs=["LAW-20", "LAW-22", "RULE-3"],
    )


def evaluate_freeze_guard_architecture_drift(  # RULE-3
    drift_count: int = 1,
) -> FreezeGuardResult:
    passed = drift_count == 0
    return FreezeGuardResult(
        guard_name="G-R4_architecture_drift",
        passed=passed,
        detail=f"Architecture drifts: {drift_count} (need 0)",
        law_refs=["LAW-3", "§16.10"],
    )


def evaluate_freeze_guard_baseline_locked(  # RULE-3
    baseline_locked: bool = False,
) -> FreezeGuardResult:
    return FreezeGuardResult(
        guard_name="G-R5_baseline_locked",
        passed=baseline_locked,
        detail=f"Baseline locked: {baseline_locked}",
        law_refs=["LAW-5", "RULE-1"],
    )


class ReleaseStateMachine:  # LAW-1 LAW-3 LAW-5 LAW-11 RULE-1 RULE-3
    """Release certification state machine with freeze guards.

    LAW 11: All state is instance-scoped — no globals.
    LAW 3: Same guard inputs -> same transition (deterministic).
    RULE 3: All transitions gated by freeze guards.
    """

    def __init__(self, strict_release_mode: bool = False) -> None:
        self._state: ReleaseState = ReleaseState.IDLE
        self._strict_release_mode = strict_release_mode
        self._transition_history: List[ReleaseTransitionRecord] = []

    @property
    def state(self) -> ReleaseState:
        return self._state

    def transition(  # LAW-3 RULE-3
        self,
        transition: ReleaseTransition,
        guard_inputs: Optional[Dict[str, Any]] = None,
        release_trace_id: str = "",
    ) -> Dict[str, Any]:
        allowed = VALID_TRANSITIONS.get(self._state, {})
        if transition not in allowed:
            return {
                "success": False,
                "from_state": self._state.value,
                "to_state": self._state.value,
                "transition": transition.value,
                "guard_results": {},
                "blocked_by": ["invalid_transition"],
                "trace_id": release_trace_id,
            }

        target = allowed[transition]
        guard_inputs = guard_inputs or {}
        guard_results: Dict[str, FreezeGuardResult] = {}
        blocked_by: List[str] = []

        if transition == ReleaseTransition.R_T4:
            self._evaluate_all_guards(guard_inputs, guard_results, blocked_by)
            if blocked_by:
                target = ReleaseState.BLOCKED

        elif transition == ReleaseTransition.R_T5:
            self._evaluate_all_guards(guard_inputs, guard_results, blocked_by)
            if blocked_by:
                target = ReleaseState.BLOCKED

        record = ReleaseTransitionRecord(
            from_state=self._state,
            to_state=target,
            transition=transition,
            guard_results=guard_results,
            release_trace_id=release_trace_id,
        )
        self._transition_history.append(record)
        self._state = target

        return {
            "success": True,
            "from_state": record.from_state.value,
            "to_state": target.value,
            "transition": transition.value,
            "guard_results": {k: {"passed": v.passed, "detail": v.detail}
                              for k, v in guard_results.items()},
            "blocked_by": blocked_by,
            "trace_id": release_trace_id,
        }

    def _evaluate_all_guards(
        self,
        inputs: Dict[str, Any],
        results: Dict[str, FreezeGuardResult],
        blocked: List[str],
    ) -> None:
        gr1 = evaluate_freeze_guard_canon_compliance(inputs.get("canon_compliance_pct", 0.0))
        results["G-R1"] = gr1
        if not gr1.passed:
            blocked.append("G-R1")

        gr2 = evaluate_freeze_guard_zero_regressions(inputs.get("regression_count", 1))
        results["G-R2"] = gr2
        if not gr2.passed:
            blocked.append("G-R2")

        gr3 = evaluate_freeze_guard_critical_guards(inputs.get("all_critical_guards_passed", False))
        results["G-R3"] = gr3
        if not gr3.passed:
            blocked.append("G-R3")

        gr4 = evaluate_freeze_guard_architecture_drift(inputs.get("drift_count", 1))
        results["G-R4"] = gr4
        if not gr4.passed:
            blocked.append("G-R4")

        gr5 = evaluate_freeze_guard_baseline_locked(inputs.get("baseline_locked", False))
        results["G-R5"] = gr5
        if not gr5.passed:
            blocked.append("G-R5")

    def reset(self) -> None:
        self._state = ReleaseState.IDLE
        self._transition_history.clear()

    @property
    def transition_history(self) -> List[ReleaseTransitionRecord]:
        return list(self._transition_history)
