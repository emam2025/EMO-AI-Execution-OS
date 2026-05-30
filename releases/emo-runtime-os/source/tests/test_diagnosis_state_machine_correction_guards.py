"""Phase G2 — Diagnosis State Machine Correction Guard Tests.  # RULE-3

Tests the 7-state diagnosis SM with all guards, particularly the
3 correction guards (≥1 signal, ≥0.75 confidence, rollback_safe).

Ref: Canon RULE 3, LAW 7, LAW 8
Ref: artifacts/design/g2/03_diagnosis_state_machine.md
"""

from __future__ import annotations

import pytest

from core.runtime.models.critic_models import (
    CorrectionGuardReason,
    DiagnosisReport,
    SeverityLevel,
)
from core.runtime.critic.diagnosis_state_machine import (
    DiagnosisState,
    DiagnosisStateMachine,
)


class TestDiagnosisStateMachine:
    """7-state machine transitions and correction guards."""

    def test_initial_state(self):
        sm = DiagnosisStateMachine()
        assert sm.current == DiagnosisState.FAILURE_OBSERVED

    def test_happy_path_to_correct(self):
        sm = DiagnosisStateMachine()
        assert sm.transition(DiagnosisState.PATTERN_MATCH, trace={
            "error_type": "timeout", "stack_pattern": "ConnectionError"
        })[0]
        assert sm.transition(DiagnosisState.ROOT_CAUSE_ISOLATE, match_confidence=0.5)[0]
        diag = DiagnosisReport(evidence_chain=[{"n": "1"}], confidence_score=0.8)
        ok, _ = sm.transition(DiagnosisState.CORRECT, diagnosis=diag)
        assert ok
        assert sm.current == DiagnosisState.CORRECT

    def test_happy_path_reject_low_confidence(self):
        sm = DiagnosisStateMachine()
        sm.transition(DiagnosisState.PATTERN_MATCH, trace={"error_type": "err", "stack_pattern": "x"})
        sm.transition(DiagnosisState.ROOT_CAUSE_ISOLATE, match_confidence=0.5)
        ok, _ = sm.transition(DiagnosisState.REJECT, confidence=0.4)
        assert ok
        assert sm.current == DiagnosisState.REJECT

    def test_no_match_path(self):
        sm = DiagnosisStateMachine()
        sm.transition(DiagnosisState.PATTERN_MATCH, trace={"error_type": "err", "stack_pattern": "x"})
        ok, _ = sm.transition(DiagnosisState.NO_OP, match_confidence=0.1)
        assert ok
        assert sm.current == DiagnosisState.NO_OP

    def test_guard_has_trace_empty(self):
        sm = DiagnosisStateMachine()
        ok, _ = sm.transition(DiagnosisState.PATTERN_MATCH, trace={})
        assert not ok

    def test_guard_has_trace_missing_fields(self):
        sm = DiagnosisStateMachine()
        ok, _ = sm.transition(DiagnosisState.PATTERN_MATCH, trace={"irrelevant": True})
        assert not ok

    def test_guard_correction_allowed_signal_count_below_1(self):
        sm = DiagnosisStateMachine()
        diag = DiagnosisReport(evidence_chain=[], confidence_score=0.8)
        ok, _ = sm.guard_correction_allowed(diagnosis=diag)
        assert not ok

    def test_guard_correction_allowed_confidence_below_075(self):
        sm = DiagnosisStateMachine()
        diag = DiagnosisReport(evidence_chain=[{"n": "1"}], confidence_score=0.5)
        ok, _ = sm.guard_correction_allowed(diagnosis=diag)
        assert not ok

    def test_guard_correction_allowed_passes(self):
        sm = DiagnosisStateMachine()
        diag = DiagnosisReport(evidence_chain=[{"n": "1"}], confidence_score=0.8)
        ok, _ = sm.guard_correction_allowed(diagnosis=diag)
        assert ok

    def test_guard_escalate_critical_severity(self):
        sm = DiagnosisStateMachine()
        ok, _ = sm.guard_escalate(severity="critical", risk=0.0)
        assert ok

    def test_guard_escalate_high_risk(self):
        sm = DiagnosisStateMachine()
        ok, _ = sm.guard_escalate(severity="warning", risk=0.9)
        assert ok

    def test_guard_escalate_both_low(self):
        sm = DiagnosisStateMachine()
        ok, _ = sm.guard_escalate(severity="info", risk=0.3)
        assert not ok

    def test_guard_retry_cooldown(self):
        sm = DiagnosisStateMachine()
        ok, _ = sm.guard_retry()
        assert ok
        ok, _ = sm.guard_retry()
        assert not ok

    def test_max_corrections(self):
        sm = DiagnosisStateMachine()
        sm._correction_count = 3
        diag = DiagnosisReport(evidence_chain=[{"n": "1"}], confidence_score=0.9)
        ok, _ = sm.guard_correction_allowed(diagnosis=diag)
        assert not ok

    def test_invalid_transition(self):
        sm = DiagnosisStateMachine()
        ok, _ = sm.transition(DiagnosisState.ESCALATE)
        assert not ok

    def test_terminal_no_transitions(self):
        sm = DiagnosisStateMachine()
        sm.force_set(DiagnosisState.REJECT)
        ok, _ = sm.transition(DiagnosisState.CORRECT)
        assert not ok

    def test_history(self):
        sm = DiagnosisStateMachine()
        sm.transition(DiagnosisState.PATTERN_MATCH, trace={"error_type": "t", "stack_pattern": "s"})
        assert len(sm.history) == 1
        assert sm.history[0]["to"] == "pattern_match"


class TestCorrectionGuardEvaluation:
    """evaluate_correction_guards — RULE 3 enforcement."""

    def test_all_guards_pass(self):
        sm = DiagnosisStateMachine()
        diag = DiagnosisReport(evidence_chain=[{"n": "1"}], confidence_score=0.8)
        result = sm.evaluate_correction_guards(diag)
        assert result.allowed

    def test_fails_no_signals(self):
        sm = DiagnosisStateMachine()
        diag = DiagnosisReport(evidence_chain=[], confidence_score=0.9)
        result = sm.evaluate_correction_guards(diag)
        assert not result.allowed
        assert result.failed_guard == CorrectionGuardReason.INSUFFICIENT_DIAGNOSIS_SIGNALS

    def test_fails_low_confidence(self):
        sm = DiagnosisStateMachine()
        diag = DiagnosisReport(evidence_chain=[{"n": "1"}], confidence_score=0.5)
        result = sm.evaluate_correction_guards(diag)
        assert not result.allowed
        assert result.failed_guard == CorrectionGuardReason.BELOW_CONFIDENCE_THRESHOLD

    def test_fails_max_corrections(self):
        sm = DiagnosisStateMachine()
        sm._correction_count = 3
        diag = DiagnosisReport(evidence_chain=[{"n": "1"}], confidence_score=0.9)
        result = sm.evaluate_correction_guards(diag)
        assert not result.allowed
        assert result.failed_guard == CorrectionGuardReason.EXCEEDS_MAX_CORRECTIONS

    def test_determinism_hash_stable(self):
        sm = DiagnosisStateMachine()
        h1 = sm.compute_determinism_hash({"a": 1}, {"b": 2})
        h2 = sm.compute_determinism_hash({"a": 1}, {"b": 2})
        assert h1 == h2

    def test_determinism_hash_different_inputs(self):
        sm = DiagnosisStateMachine()
        h1 = sm.compute_determinism_hash({"a": 1}, {"b": 2})
        h2 = sm.compute_determinism_hash({"a": 2}, {"b": 2})
        assert h1 != h2
