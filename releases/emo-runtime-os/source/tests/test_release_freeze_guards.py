"""Phase FINAL — Release Freeze Guards Tests.  # LAW-1 LAW-3 LAW-5 LAW-8 LAW-11 RULE-1 RULE-3

Tests for G-R1–G-R5 freeze guards and the ReleaseStateMachine.

Ref: Canon LAW 1-27, RULE 1-5
Ref: DEVELOPER.md §16 (Architecture Canon)
"""

from __future__ import annotations

import pytest

from scripts.release.release_state_machine import (
    ReleaseStateMachine,
    ReleaseState,
    ReleaseTransition,
    evaluate_freeze_guard_canon_compliance,
    evaluate_freeze_guard_zero_regressions,
    evaluate_freeze_guard_critical_guards,
    evaluate_freeze_guard_architecture_drift,
    evaluate_freeze_guard_baseline_locked,
)

TRACE_ID = "release_test_trace_001"


class TestG1CanonCompliance:
    """G-R1: Canon compliance must be 100%."""

    def test_passes_at_100(self) -> None:
        result = evaluate_freeze_guard_canon_compliance(100.0)
        assert result.passed is True

    def test_fails_below_100(self) -> None:
        result = evaluate_freeze_guard_canon_compliance(99.0)
        assert result.passed is False

    def test_fails_at_zero(self) -> None:
        result = evaluate_freeze_guard_canon_compliance(0.0)
        assert result.passed is False


class TestG2ZeroRegressions:
    """G-R2: Regressions must be 0."""

    def test_passes_at_zero(self) -> None:
        result = evaluate_freeze_guard_zero_regressions(0)
        assert result.passed is True

    def test_fails_at_one(self) -> None:
        result = evaluate_freeze_guard_zero_regressions(1)
        assert result.passed is False


class TestG3CriticalGuards:
    """G-R3: All critical guards must pass."""

    def test_passes_when_all_pass(self) -> None:
        result = evaluate_freeze_guard_critical_guards(True)
        assert result.passed is True

    def test_fails_when_any_fails(self) -> None:
        result = evaluate_freeze_guard_critical_guards(False)
        assert result.passed is False


class TestG4ArchitectureDrift:
    """G-R4: Architecture drift must be 0."""

    def test_passes_at_zero(self) -> None:
        result = evaluate_freeze_guard_architecture_drift(0)
        assert result.passed is True

    def test_fails_at_one(self) -> None:
        result = evaluate_freeze_guard_architecture_drift(1)
        assert result.passed is False


class TestG5BaselineLocked:
    """G-R5: Baseline must be locked before approval."""

    def test_passes_when_locked(self) -> None:
        result = evaluate_freeze_guard_baseline_locked(True)
        assert result.passed is True

    def test_fails_when_unlocked(self) -> None:
        result = evaluate_freeze_guard_baseline_locked(False)
        assert result.passed is False


class TestReleaseStateMachine:
    """Release SM: Full lifecycle with freeze guards."""

    def test_initial_state(self) -> None:
        sm = ReleaseStateMachine()
        assert sm.state == ReleaseState.IDLE

    def test_full_approve_cycle(self) -> None:
        sm = ReleaseStateMachine()
        sm.transition(ReleaseTransition.R_T1, {}, TRACE_ID)
        assert sm.state == ReleaseState.COLLECTING_REPORTS
        sm.transition(ReleaseTransition.R_T2, {}, TRACE_ID)
        assert sm.state == ReleaseState.VALIDATING_METRICS
        sm.transition(ReleaseTransition.R_T3, {}, TRACE_ID)
        assert sm.state == ReleaseState.CHECKING_GUARDS
        sm.transition(ReleaseTransition.R_T4, {
            "canon_compliance_pct": 100.0,
            "regression_count": 0,
            "all_critical_guards_passed": True,
            "drift_count": 0,
            "baseline_locked": True,
        }, TRACE_ID)
        assert sm.state == ReleaseState.FREEZING_BASELINE
        sm.transition(ReleaseTransition.R_T5, {
            "canon_compliance_pct": 100.0,
            "regression_count": 0,
            "all_critical_guards_passed": True,
            "drift_count": 0,
            "baseline_locked": True,
        }, TRACE_ID)
        assert sm.state == ReleaseState.APPROVED

    def test_blocked_when_guards_fail(self) -> None:
        sm = ReleaseStateMachine()
        sm.transition(ReleaseTransition.R_T1, {}, TRACE_ID)
        sm.transition(ReleaseTransition.R_T2, {}, TRACE_ID)
        sm.transition(ReleaseTransition.R_T3, {}, TRACE_ID)
        result = sm.transition(ReleaseTransition.R_T4, {
            "canon_compliance_pct": 50.0,
            "regression_count": 3,
            "all_critical_guards_passed": False,
            "drift_count": 2,
            "baseline_locked": False,
        }, TRACE_ID)
        assert sm.state == ReleaseState.BLOCKED
        assert "G-R1" in result["blocked_by"]
        assert "G-R2" in result["blocked_by"]
        assert "G-R3" in result["blocked_by"]
        assert "G-R4" in result["blocked_by"]
        assert "G-R5" in result["blocked_by"]

    def test_blocked_then_retry(self) -> None:
        sm = ReleaseStateMachine()
        sm.transition(ReleaseTransition.R_T1, {}, TRACE_ID)
        sm.transition(ReleaseTransition.R_T2, {}, TRACE_ID)
        sm.transition(ReleaseTransition.R_T3, {}, TRACE_ID)
        sm.transition(ReleaseTransition.R_T4, {
            "canon_compliance_pct": 50.0,
            "regression_count": 1,
            "all_critical_guards_passed": False,
            "drift_count": 1,
            "baseline_locked": False,
        }, TRACE_ID)
        assert sm.state == ReleaseState.BLOCKED
        sm.transition(ReleaseTransition.R_T9, {}, TRACE_ID)
        assert sm.state == ReleaseState.IDLE

    def test_invalid_transition(self) -> None:
        sm = ReleaseStateMachine()
        result = sm.transition(ReleaseTransition.R_T5, {}, TRACE_ID)
        assert result["success"] is False
        assert "invalid_transition" in result["blocked_by"]

    def test_approve_then_archive(self) -> None:
        sm = ReleaseStateMachine()
        for t in [ReleaseTransition.R_T1, ReleaseTransition.R_T2, ReleaseTransition.R_T3]:
            sm.transition(t, {}, TRACE_ID)
        sm.transition(ReleaseTransition.R_T4, {
            "canon_compliance_pct": 100.0,
            "regression_count": 0,
            "all_critical_guards_passed": True,
            "drift_count": 0,
            "baseline_locked": True,
        }, TRACE_ID)
        sm.transition(ReleaseTransition.R_T5, {
            "canon_compliance_pct": 100.0,
            "regression_count": 0,
            "all_critical_guards_passed": True,
            "drift_count": 0,
            "baseline_locked": True,
        }, TRACE_ID)
        assert sm.state == ReleaseState.APPROVED
        sm.transition(ReleaseTransition.R_T8, {}, TRACE_ID)
        assert sm.state == ReleaseState.ARCHIVED

    def test_reset(self) -> None:
        sm = ReleaseStateMachine()
        sm.transition(ReleaseTransition.R_T1, {}, TRACE_ID)
        sm.reset()
        assert sm.state == ReleaseState.IDLE
        assert len(sm.transition_history) == 0
