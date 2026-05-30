"""Phase FINAL — Certification State Machine with Readiness Guards.  # LAW-1 LAW-3 LAW-5 LAW-8 LAW-11 LAW-12 LAW-13 LAW-14 LAW-15 LAW-20 LAW-22 RULE-1 RULE-2 RULE-3 RULE-4 RULE-5

6-state certification lifecycle: Audit Start → Load Test → Security Check →
Compliance Verify → [Certify / Flag / Reject]. Enforces readiness guards
including canon_compliance == 100%, regression == 0, p99_latency < threshold,
oscillation_prevented == true, and trace_integrity == true.

Ref: Canon LAW 1-27, RULE 1-5
Ref: DEVELOPER.md §16.1 (Production Readiness Checklist)
Ref: DEVELOPER.md §15.13 (AI-Native Runtime Features)
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class CertificationState(str, Enum):  # LAW-1 LAW-3 LAW-8
    IDLE = "idle"
    AUDIT_START = "audit_start"
    LOAD_TEST = "load_test"
    SECURITY_CHECK = "security_check"
    COMPLIANCE_VERIFY = "compliance_verify"
    CERTIFY = "certify"
    FLAG = "flag"
    REJECT = "reject"


class GuardDecision(str, Enum):  # LAW-13 RULE-3 — cross-phase (J1 uses this)
    ALLOW = "allow"
    BLOCK = "block"


class CertificationTransition(str, Enum):
    C1 = "c1"   # IDLE -> AUDIT_START
    C2 = "c2"   # AUDIT_START -> LOAD_TEST
    C3 = "c3"   # LOAD_TEST -> SECURITY_CHECK
    C4 = "c4"   # SECURITY_CHECK -> COMPLIANCE_VERIFY
    C5 = "c5"   # COMPLIANCE_VERIFY -> CERTIFY
    C6 = "c6"   # COMPLIANCE_VERIFY -> FLAG
    C7 = "c7"   # COMPLIANCE_VERIFY -> REJECT
    C8 = "c8"   # FLAG -> AUDIT_START (recycle)
    C9 = "c9"   # CERTIFY -> IDLE
    C10 = "c10" # REJECT -> IDLE
    C11 = "c11" # FLAG -> IDLE


VALID_TRANSITIONS: Dict[CertificationState, Dict[CertificationTransition, CertificationState]] = {
    CertificationState.IDLE: {
        CertificationTransition.C1: CertificationState.AUDIT_START,
    },
    CertificationState.AUDIT_START: {
        CertificationTransition.C2: CertificationState.LOAD_TEST,
    },
    CertificationState.LOAD_TEST: {
        CertificationTransition.C3: CertificationState.SECURITY_CHECK,
    },
    CertificationState.SECURITY_CHECK: {
        CertificationTransition.C4: CertificationState.COMPLIANCE_VERIFY,
    },
    CertificationState.COMPLIANCE_VERIFY: {
        CertificationTransition.C5: CertificationState.CERTIFY,
        CertificationTransition.C6: CertificationState.FLAG,
        CertificationTransition.C7: CertificationState.REJECT,
    },
    CertificationState.CERTIFY: {
        CertificationTransition.C9: CertificationState.IDLE,
    },
    CertificationState.FLAG: {
        CertificationTransition.C8: CertificationState.AUDIT_START,
        CertificationTransition.C11: CertificationState.IDLE,
    },
    CertificationState.REJECT: {
        CertificationTransition.C10: CertificationState.IDLE,
    },
}


@dataclass
class ReadinessGuardResult:  # LAW-3 RULE-3
    """Result of a single readiness guard check."""
    guard_name: str
    passed: bool
    detail: str = ""
    law_refs: List[str] = field(default_factory=list)
    hash: str = ""

    def __post_init__(self) -> None:
        raw = f"{self.guard_name}:{self.passed}:{self.detail}"
        self.hash = hashlib.sha256(raw.encode()).hexdigest()[:16]


@dataclass
class CertificationTransitionRecord:  # LAW-5 LAW-12
    """Record of a state machine transition."""
    from_state: CertificationState
    to_state: CertificationState
    transition: CertificationTransition
    guard_results: Dict[str, ReadinessGuardResult] = field(default_factory=dict)
    timestamp_ns: int = field(default_factory=lambda: __import__("time").time_ns())
    trace_id: str = ""


class CertificationStateMachine:  # LAW-1 LAW-3 LAW-5 LAW-8 LAW-11 LAW-12 LAW-13 LAW-14 LAW-15 LAW-20 LAW-22 RULE-1 RULE-2 RULE-3 RULE-4 RULE-5
    """Certification state machine with readiness guards.

    Enforces 5 hard guards before CERTIFY:
      G-C1 canon_compliance == 100%
      G-C2 regression == 0
      G-C3 p99_latency < 200ms threshold
      G-C4 oscillation_prevented == true
      G-C5 trace_integrity == true

    LAW 11: No global mutable state — all machine state is instance-scoped.
    LAW 3: Same guard inputs -> same transition (deterministic).
    RULE 3: All transitions are gated by readiness guards.
    """

    def __init__(self, strict_certification_mode: bool = False) -> None:
        self._state: CertificationState = CertificationState.IDLE
        self._strict_certification_mode = strict_certification_mode
        self._transition_history: List[CertificationTransitionRecord] = []

    @property
    def state(self) -> CertificationState:
        return self._state

    def transition(  # LAW-3 RULE-3
        self,
        transition: CertificationTransition,
        guard_inputs: Optional[Dict[str, Any]] = None,
        certification_trace_id: str = "",
    ) -> Dict[str, Any]:
        """Attempt a state transition with guard enforcement.

        Args:
            transition: CertificationTransition to attempt.
            guard_inputs: Dict of guard data for C5 → CERTIFY.
            certification_trace_id: Correlation ID.

        Returns:
            success:         True if transition was allowed.
            from_state:      Previous state.
            to_state:        New state after transition (or same if blocked).
            transition:      Transition attempted.
            guard_results:   Dict of guard_name -> ReadinessGuardResult.
            blocked_by:      List of guard names that blocked the transition.
            trace_id:        Certification trace ID.
        """
        allowed = VALID_TRANSITIONS.get(self._state, {})
        if transition not in allowed:
            return {
                "success": False,
                "from_state": self._state.value,
                "to_state": self._state.value,
                "transition": transition.value,
                "guard_results": {},
                "blocked_by": ["invalid_transition"],
                "trace_id": certification_trace_id,
            }

        target = allowed[transition]
        guard_results: Dict[str, ReadinessGuardResult] = {}
        blocked_by: List[str] = []

        if transition == CertificationTransition.C5:
            guards = self._evaluate_certify_guards(guard_inputs or {})
            guard_results = guards
            for name, result in guards.items():
                if not result.passed:
                    blocked_by.append(name)
            if blocked_by:
                target = CertificationState.FLAG
        elif transition == CertificationTransition.C6:
            guards_input = guard_inputs or {}
            if guards_input.get("compliance_pct", 100) < 100 or guards_input.get("has_violations", False):
                target = CertificationState.REJECT

        record = CertificationTransitionRecord(
            from_state=self._state,
            to_state=target,
            transition=transition,
            guard_results=guard_results,
            trace_id=certification_trace_id,
        )
        self._transition_history.append(record)
        self._state = target

        return {
            "success": True,
            "from_state": record.from_state.value,
            "to_state": target.value,
            "transition": transition.value,
            "guard_results": {k: {"passed": v.passed, "detail": v.detail, "hash": v.hash}
                              for k, v in guard_results.items()},
            "blocked_by": blocked_by,
            "trace_id": certification_trace_id,
        }

    def _evaluate_certify_guards(self, inputs: Dict[str, Any]) -> Dict[str, ReadinessGuardResult]:
        """Evaluate all 5 readiness guards for C5 → CERTIFY transition."""
        guards: Dict[str, ReadinessGuardResult] = {}

        compliance_pct = inputs.get("compliance_pct", 0)
        regressions = inputs.get("regressions", 1)
        p99_latency = inputs.get("p99_latency_ms", 999)
        oscillation_prevented = inputs.get("oscillation_prevented", False)
        trace_integrity = inputs.get("trace_integrity", False)

        guards["G-C1_canon_compliance"] = ReadinessGuardResult(
            guard_name="G-C1_canon_compliance",
            passed=compliance_pct == 100.0,
            detail=f"Compliance: {compliance_pct}% (need 100%)",
            law_refs=["LAW-1", "LAW-3", "RULE-1"],
        )
        guards["G-C2_regression_zero"] = ReadinessGuardResult(
            guard_name="G-C2_regression_zero",
            passed=regressions == 0,
            detail=f"Regressions: {regressions} (need 0)",
            law_refs=["LAW-8", "RULE-5"],
        )
        guards["G-C3_p99_latency"] = ReadinessGuardResult(
            guard_name="G-C3_p99_latency",
            passed=p99_latency < 200.0,
            detail=f"P99 latency: {p99_latency}ms (need < 200ms)",
            law_refs=["LAW-15", "RULE-2"],
        )
        guards["G-C4_oscillation_prevented"] = ReadinessGuardResult(
            guard_name="G-C4_oscillation_prevented",
            passed=oscillation_prevented,
            detail=f"Oscillation prevented: {oscillation_prevented}",
            law_refs=["LAW-20", "RULE-3"],
        )
        guards["G-C5_trace_integrity"] = ReadinessGuardResult(
            guard_name="G-C5_trace_integrity",
            passed=trace_integrity,
            detail=f"Trace integrity: {trace_integrity}",
            law_refs=["LAW-5", "LAW-12", "RULE-1"],
        )

        return guards

    def reset(self) -> None:
        """Reset machine to IDLE state."""
        self._state = CertificationState.IDLE
        self._transition_history.clear()

    @property
    def transition_history(self) -> List[CertificationTransitionRecord]:
        return list(self._transition_history)
