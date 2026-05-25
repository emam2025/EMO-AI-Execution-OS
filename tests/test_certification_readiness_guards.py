"""Phase FINAL — Certification State Machine & Readiness Guard Tests.  # LAW-1 LAW-3 LAW-5 LAW-8 LAW-11 RULE-1 RULE-3

Tests all 11 transitions (C1-C11) and all 5 readiness guards (G-C1 through G-C5)
including the split-branch logic at COMPLIANCE_VERIFY → CERTIFY/FLAG/REJECT.

Ref: Canon LAW 1, LAW 3, LAW 5, LAW 8, LAW 11
Ref: Canon RULE 1 (Determinism), RULE 3 (Safety Guards)
"""

from __future__ import annotations

import pytest

from core.runtime.certification.certification_state_machine import (
    CertificationState,
    CertificationStateMachine,
    CertificationTransition,
)


class TestCertificationStateTransitions:
    """Test all valid state transitions."""

    def test_c1_idle_to_audit_start(self) -> None:
        sm = CertificationStateMachine()
        result = sm.transition(CertificationTransition.C1, certification_trace_id="t1")
        assert result["success"] is True
        assert result["to_state"] == "audit_start"
        assert sm.state == CertificationState.AUDIT_START

    def test_c2_audit_start_to_load_test(self) -> None:
        sm = CertificationStateMachine()
        sm.transition(CertificationTransition.C1, certification_trace_id="t1")
        result = sm.transition(CertificationTransition.C2, certification_trace_id="t2")
        assert result["success"] is True
        assert result["to_state"] == "load_test"
        assert sm.state == CertificationState.LOAD_TEST

    def test_c3_load_test_to_security_check(self) -> None:
        sm = CertificationStateMachine()
        sm.transition(CertificationTransition.C1, certification_trace_id="t1")
        sm.transition(CertificationTransition.C2, certification_trace_id="t2")
        result = sm.transition(CertificationTransition.C3, certification_trace_id="t3")
        assert result["success"] is True
        assert result["to_state"] == "security_check"
        assert sm.state == CertificationState.SECURITY_CHECK

    def test_c4_security_check_to_compliance_verify(self) -> None:
        sm = CertificationStateMachine()
        sm.transition(CertificationTransition.C1, certification_trace_id="t1")
        sm.transition(CertificationTransition.C2, certification_trace_id="t2")
        sm.transition(CertificationTransition.C3, certification_trace_id="t3")
        result = sm.transition(CertificationTransition.C4, certification_trace_id="t4")
        assert result["success"] is True
        assert result["to_state"] == "compliance_verify"

    def test_c9_certify_to_idle(self) -> None:
        sm = CertificationStateMachine()
        sm.transition(CertificationTransition.C1, certification_trace_id="t1")
        sm.transition(CertificationTransition.C2, certification_trace_id="t2")
        sm.transition(CertificationTransition.C3, certification_trace_id="t3")
        sm.transition(CertificationTransition.C4, certification_trace_id="t4")
        sm.transition(CertificationTransition.C5, guard_inputs={
            "compliance_pct": 100, "regressions": 0, "p99_latency_ms": 50,
            "oscillation_prevented": True, "trace_integrity": True,
        }, certification_trace_id="t5")
        result = sm.transition(CertificationTransition.C9, certification_trace_id="t6")
        assert result["success"] is True
        assert result["to_state"] == "idle"
        assert sm.state == CertificationState.IDLE

    def test_c10_reject_to_idle(self) -> None:
        sm = CertificationStateMachine()
        sm.transition(CertificationTransition.C1, certification_trace_id="t1")
        sm.transition(CertificationTransition.C2, certification_trace_id="t2")
        sm.transition(CertificationTransition.C3, certification_trace_id="t3")
        sm.transition(CertificationTransition.C4, certification_trace_id="t4")
        sm.transition(CertificationTransition.C6, guard_inputs={
            "compliance_pct": 50, "has_violations": True,
        }, certification_trace_id="t5")
        assert sm.state == CertificationState.REJECT
        result = sm.transition(CertificationTransition.C10, certification_trace_id="t6")
        assert result["success"] is True
        assert result["to_state"] == "idle"

    def test_c11_flag_to_idle(self) -> None:
        sm = CertificationStateMachine()
        sm.transition(CertificationTransition.C1, certification_trace_id="t1")
        sm.transition(CertificationTransition.C2, certification_trace_id="t2")
        sm.transition(CertificationTransition.C3, certification_trace_id="t3")
        sm.transition(CertificationTransition.C4, certification_trace_id="t4")
        sm.transition(CertificationTransition.C5, guard_inputs={
            "compliance_pct": 100, "regressions": 1, "p99_latency_ms": 50,
            "oscillation_prevented": True, "trace_integrity": True,
        }, certification_trace_id="t5")
        assert sm.state == CertificationState.FLAG
        result = sm.transition(CertificationTransition.C11, certification_trace_id="t6")
        assert result["success"] is True
        assert result["to_state"] == "idle"

    def test_c8_flag_to_audit_start_recycle(self) -> None:
        sm = CertificationStateMachine()
        sm.transition(CertificationTransition.C1, certification_trace_id="t1")
        sm.transition(CertificationTransition.C2, certification_trace_id="t2")
        sm.transition(CertificationTransition.C3, certification_trace_id="t3")
        sm.transition(CertificationTransition.C4, certification_trace_id="t4")
        sm.transition(CertificationTransition.C5, guard_inputs={
            "compliance_pct": 100, "regressions": 1, "p99_latency_ms": 50,
            "oscillation_prevented": True, "trace_integrity": True,
        }, certification_trace_id="t5")
        assert sm.state == CertificationState.FLAG
        result = sm.transition(CertificationTransition.C8, certification_trace_id="t6")
        assert result["success"] is True
        assert result["to_state"] == "audit_start"


class TestInvalidTransitions:
    """Test that invalid transitions are rejected."""

    def test_invalid_transition_from_idle(self) -> None:
        sm = CertificationStateMachine()
        result = sm.transition(CertificationTransition.C5, certification_trace_id="t1")
        assert result["success"] is False
        assert result["blocked_by"] == ["invalid_transition"]
        assert sm.state == CertificationState.IDLE

    def test_invalid_order_c2_from_idle(self) -> None:
        sm = CertificationStateMachine()
        result = sm.transition(CertificationTransition.C2, certification_trace_id="t1")
        assert result["success"] is False

    def test_transition_history_recorded(self) -> None:
        sm = CertificationStateMachine()
        sm.transition(CertificationTransition.C1, certification_trace_id="t1")
        sm.transition(CertificationTransition.C2, certification_trace_id="t2")
        assert len(sm.transition_history) == 2
        assert sm.transition_history[0].transition == CertificationTransition.C1
        assert sm.transition_history[1].transition == CertificationTransition.C2


class TestReadinessGuards:
    """Test all 5 readiness guards that gate CERTIFY."""

    def test_gc1_compliance_100_passes(self) -> None:
        sm = CertificationStateMachine()
        sm.transition(CertificationTransition.C1, certification_trace_id="t1")
        sm.transition(CertificationTransition.C2, certification_trace_id="t2")
        sm.transition(CertificationTransition.C3, certification_trace_id="t3")
        sm.transition(CertificationTransition.C4, certification_trace_id="t4")
        result = sm.transition(CertificationTransition.C5, guard_inputs={
            "compliance_pct": 100, "regressions": 0, "p99_latency_ms": 50,
            "oscillation_prevented": True, "trace_integrity": True,
        }, certification_trace_id="t5")
        assert result["success"] is True
        assert result["to_state"] == "certify"
        assert sm.state == CertificationState.CERTIFY

    def test_gc1_compliance_99_fails(self) -> None:
        sm = CertificationStateMachine()
        sm.transition(CertificationTransition.C1, certification_trace_id="t1")
        sm.transition(CertificationTransition.C2, certification_trace_id="t2")
        sm.transition(CertificationTransition.C3, certification_trace_id="t3")
        sm.transition(CertificationTransition.C4, certification_trace_id="t4")
        result = sm.transition(CertificationTransition.C5, guard_inputs={
            "compliance_pct": 99, "regressions": 0, "p99_latency_ms": 50,
            "oscillation_prevented": True, "trace_integrity": True,
        }, certification_trace_id="t5")
        assert result["success"] is True
        assert result["to_state"] == "flag"
        assert "G-C1_canon_compliance" in result["blocked_by"]

    def test_gc2_regression_nonzero_fails(self) -> None:
        sm = CertificationStateMachine()
        sm.transition(CertificationTransition.C1, certification_trace_id="t1")
        sm.transition(CertificationTransition.C2, certification_trace_id="t2")
        sm.transition(CertificationTransition.C3, certification_trace_id="t3")
        sm.transition(CertificationTransition.C4, certification_trace_id="t4")
        result = sm.transition(CertificationTransition.C5, guard_inputs={
            "compliance_pct": 100, "regressions": 3, "p99_latency_ms": 50,
            "oscillation_prevented": True, "trace_integrity": True,
        }, certification_trace_id="t5")
        assert result["success"] is True
        assert result["to_state"] == "flag"
        assert "G-C2_regression_zero" in result["blocked_by"]

    def test_gc3_p99_latency_over_threshold_fails(self) -> None:
        sm = CertificationStateMachine()
        sm.transition(CertificationTransition.C1, certification_trace_id="t1")
        sm.transition(CertificationTransition.C2, certification_trace_id="t2")
        sm.transition(CertificationTransition.C3, certification_trace_id="t3")
        sm.transition(CertificationTransition.C4, certification_trace_id="t4")
        result = sm.transition(CertificationTransition.C5, guard_inputs={
            "compliance_pct": 100, "regressions": 0, "p99_latency_ms": 250,
            "oscillation_prevented": True, "trace_integrity": True,
        }, certification_trace_id="t5")
        assert result["success"] is True
        assert result["to_state"] == "flag"
        assert "G-C3_p99_latency" in result["blocked_by"]

    def test_gc4_oscillation_not_prevented_fails(self) -> None:
        sm = CertificationStateMachine()
        sm.transition(CertificationTransition.C1, certification_trace_id="t1")
        sm.transition(CertificationTransition.C2, certification_trace_id="t2")
        sm.transition(CertificationTransition.C3, certification_trace_id="t3")
        sm.transition(CertificationTransition.C4, certification_trace_id="t4")
        result = sm.transition(CertificationTransition.C5, guard_inputs={
            "compliance_pct": 100, "regressions": 0, "p99_latency_ms": 50,
            "oscillation_prevented": False, "trace_integrity": True,
        }, certification_trace_id="t5")
        assert result["success"] is True
        assert result["to_state"] == "flag"
        assert "G-C4_oscillation_prevented" in result["blocked_by"]

    def test_gc5_trace_integrity_false_fails(self) -> None:
        sm = CertificationStateMachine()
        sm.transition(CertificationTransition.C1, certification_trace_id="t1")
        sm.transition(CertificationTransition.C2, certification_trace_id="t2")
        sm.transition(CertificationTransition.C3, certification_trace_id="t3")
        sm.transition(CertificationTransition.C4, certification_trace_id="t4")
        result = sm.transition(CertificationTransition.C5, guard_inputs={
            "compliance_pct": 100, "regressions": 0, "p99_latency_ms": 50,
            "oscillation_prevented": True, "trace_integrity": False,
        }, certification_trace_id="t5")
        assert result["success"] is True
        assert result["to_state"] == "flag"
        assert "G-C5_trace_integrity" in result["blocked_by"]

    def test_multiple_guards_fail(self) -> None:
        sm = CertificationStateMachine()
        sm.transition(CertificationTransition.C1, certification_trace_id="t1")
        sm.transition(CertificationTransition.C2, certification_trace_id="t2")
        sm.transition(CertificationTransition.C3, certification_trace_id="t3")
        sm.transition(CertificationTransition.C4, certification_trace_id="t4")
        result = sm.transition(CertificationTransition.C5, guard_inputs={
            "compliance_pct": 90, "regressions": 2, "p99_latency_ms": 300,
            "oscillation_prevented": False, "trace_integrity": False,
        }, certification_trace_id="t5")
        assert result["success"] is True
        assert result["to_state"] == "flag"
        blocked = result["blocked_by"]
        assert "G-C1_canon_compliance" in blocked
        assert "G-C2_regression_zero" in blocked
        assert "G-C3_p99_latency" in blocked
        assert "G-C4_oscillation_prevented" in blocked
        assert "G-C5_trace_integrity" in blocked

    def test_c6_with_violations_rejects(self) -> None:
        sm = CertificationStateMachine()
        sm.transition(CertificationTransition.C1, certification_trace_id="t1")
        sm.transition(CertificationTransition.C2, certification_trace_id="t2")
        sm.transition(CertificationTransition.C3, certification_trace_id="t3")
        sm.transition(CertificationTransition.C4, certification_trace_id="t4")
        result = sm.transition(CertificationTransition.C6, guard_inputs={
            "compliance_pct": 50, "has_violations": True,
        }, certification_trace_id="t5")
        assert result["success"] is True
        assert result["to_state"] == "reject"
        assert sm.state == CertificationState.REJECT

    def test_reset_returns_to_idle(self) -> None:
        sm = CertificationStateMachine()
        sm.transition(CertificationTransition.C1, certification_trace_id="t1")
        sm.transition(CertificationTransition.C2, certification_trace_id="t2")
        sm.reset()
        assert sm.state == CertificationState.IDLE
        assert len(sm.transition_history) == 0


class TestDeterministicGuardEvaluation:
    """Test that guards produce deterministic results (RULE 1)."""

    def test_deterministic_guard_same_inputs(self) -> None:
        sm1 = CertificationStateMachine()
        sm2 = CertificationStateMachine()

        def run_full(sm: CertificationStateMachine) -> Dict[str, Any]:
            sm.transition(CertificationTransition.C1, certification_trace_id="t1")
            sm.transition(CertificationTransition.C2, certification_trace_id="t2")
            sm.transition(CertificationTransition.C3, certification_trace_id="t3")
            sm.transition(CertificationTransition.C4, certification_trace_id="t4")
            return sm.transition(CertificationTransition.C5, guard_inputs={
                "compliance_pct": 100, "regressions": 0, "p99_latency_ms": 50,
                "oscillation_prevented": True, "trace_integrity": True,
            }, certification_trace_id="t5")

        r1 = run_full(sm1)
        r2 = run_full(sm2)
        assert r1["to_state"] == r2["to_state"]
        assert r1["blocked_by"] == r2["blocked_by"]
        assert r1["guard_results"]["G-C1_canon_compliance"]["passed"] == r2["guard_results"]["G-C1_canon_compliance"]["passed"]
        assert r1["guard_results"]["G-C2_regression_zero"]["passed"] == r2["guard_results"]["G-C2_regression_zero"]["passed"]
