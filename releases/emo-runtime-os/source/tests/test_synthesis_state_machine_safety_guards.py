"""Phase G4 — Synthesis State Machine Safety Guard Tests.  # RULE-3

Tests the 8-state synthesis SM with all 7 Safety Guards (G1–G7).

Ref: Canon RULE 3, LAW 2, LAW 10, LAW 14
Ref: artifacts/design/g4/03_synthesis_state_machine.md §2
"""

from __future__ import annotations

import pytest

from core.runtime.tool_synthesis.synthesis_state_machine import (
    SynthesisState,
    SynthesisStateMachine,
)


class TestSynthesisStateMachine:
    """8-state machine transitions and safety guards."""

    def test_initial_state(self):
        sm = SynthesisStateMachine()
        assert sm.current == SynthesisState.INTENT_RECEIVED

    def test_happy_path_to_register(self):
        sm = SynthesisStateMachine()
        intent = {"goal": "process", "target_nodes": ["n1"]}
        sm.transition(SynthesisState.CODE_GENERATION, intent=intent)
        sm.transition(SynthesisState.AST_VALIDATION, generated_code="def foo(): pass")
        sm.transition(SynthesisState.SECURITY_SCAN, ast_valid=True)
        ok, _ = sm.transition(
            SynthesisState.SANDBOX_DRY_RUN,
            no_os_imports=True, risk_score=0.1,
        )
        assert ok
        ok, _ = sm.transition(
            SynthesisState.REGISTER,
            sandbox_success=True, side_effects=[],
        )
        assert ok
        assert sm.current == SynthesisState.REGISTER

    def test_incomplete_intent_rejected(self):
        sm = SynthesisStateMachine()
        ok, _ = sm.transition(SynthesisState.CODE_GENERATION, intent={})
        assert not ok

    def test_empty_code_rejected(self):
        sm = SynthesisStateMachine()
        intent = {"goal": "test", "target_nodes": ["n1"]}
        sm.transition(SynthesisState.CODE_GENERATION, intent=intent)
        ok, _ = sm.transition(SynthesisState.AST_VALIDATION, generated_code="")
        assert not ok

    def test_ast_invalid_rejected(self):  # G1
        sm = SynthesisStateMachine()
        intent = {"goal": "test", "target_nodes": ["n1"]}
        sm.transition(SynthesisState.CODE_GENERATION, intent=intent)
        sm.transition(SynthesisState.AST_VALIDATION, generated_code="x")
        ok, _ = sm.transition(SynthesisState.SECURITY_SCAN, ast_valid=False)
        assert not ok
        assert sm.current == SynthesisState.AST_VALIDATION

    def test_no_os_imports_guard(self):  # G2
        sm = SynthesisStateMachine()
        ok, _ = sm.transition(
            SynthesisState.SANDBOX_DRY_RUN,
            no_os_imports=False, risk_score=0.1,
        )
        assert not ok

    def test_high_risk_score_rejected(self):  # G7
        sm = SynthesisStateMachine()
        ok, _ = sm.transition(
            SynthesisState.SANDBOX_DRY_RUN,
            no_os_imports=True, risk_score=0.5,
        )
        assert not ok

    def test_sandbox_fail_rejected(self):  # G5
        sm = SynthesisStateMachine()
        ok, _ = sm.transition(
            SynthesisState.REGISTER,
            sandbox_success=False, side_effects=[],
        )
        assert not ok

    def test_side_effects_detected(self):  # G6
        sm = SynthesisStateMachine()
        ok, _ = sm.transition(
            SynthesisState.REGISTER,
            sandbox_success=True, side_effects=[{"effect_type": "file_io"}],
        )
        assert not ok

    def test_combined_registration_guard_all_pass(self):
        sm = SynthesisStateMachine()
        assert sm.guard_sandbox_passed(sandbox_success=True, side_effects=[])[0]

    def test_combined_registration_guard_fails_sandbox(self):
        sm = SynthesisStateMachine()
        ok, _ = sm.guard_sandbox_passed(sandbox_success=False, side_effects=[])
        assert not ok

    def test_terminal_state_blocks(self):
        sm = SynthesisStateMachine()
        sm.force_set(SynthesisState.REGISTER)
        ok, _ = sm.transition(SynthesisState.REJECT)
        assert not ok

    def test_invalid_transition(self):
        sm = SynthesisStateMachine()
        ok, _ = sm.transition(SynthesisState.REGISTER)
        assert not ok


class TestDeterministicSynthesisGuard:
    """RULE 1: Determinism cache and drift detection."""

    def test_determinism_hash_stable(self):
        sm = SynthesisStateMachine()
        h1 = sm.compute_determinism_hash({"a": 1}, {"b": 2}, ["c"])
        h2 = sm.compute_determinism_hash({"a": 1}, {"b": 2}, ["c"])
        assert h1 == h2

    def test_determinism_hash_different(self):
        sm = SynthesisStateMachine()
        h1 = sm.compute_determinism_hash({"a": 1}, {"b": 2}, ["c"])
        h2 = sm.compute_determinism_hash({"a": 1}, {"b": 9}, ["c"])
        assert h1 != h2

    def test_cache_hit(self):
        sm = SynthesisStateMachine()
        sm.cache_deterministic_review({"a": 1}, {"b": 2}, ["c"], "code1", "hash1")
        hit, code, h = sm.check_deterministic_review({"a": 1}, {"b": 2}, ["c"])
        assert hit
        assert code == "code1"

    def test_cache_miss(self):
        sm = SynthesisStateMachine()
        hit, _, _ = sm.check_deterministic_review({"x": 1}, {"y": 2}, ["z"])
        assert not hit

    def test_drift_detected(self):
        sm = SynthesisStateMachine()
        sm.cache_deterministic_review({"a": 1}, {"b": 2}, ["c"], "expected_code", "expected_hash")
        drift = sm.detect_drift({"a": 1}, {"b": 2}, ["c"], "different_code", "different_hash")
        assert drift

    def test_no_drift(self):
        sm = SynthesisStateMachine()
        sm.cache_deterministic_review({"a": 1}, {"b": 2}, ["c"], "code", "hash")
        drift = sm.detect_drift({"a": 1}, {"b": 2}, ["c"], "code", "hash")
        assert not drift


class TestEscalationGuard:
    """Escalation paths for ambiguous security / sandbox results."""

    def test_escalate_on_moderate_risk(self):
        sm = SynthesisStateMachine()
        ok, _ = sm.guard_needs_escalation(risk_score=0.5)
        assert ok

    def test_no_escalate_on_low_risk(self):
        sm = SynthesisStateMachine()
        ok, _ = sm.guard_needs_escalation(risk_score=0.1)
        assert not ok

    def test_reject_on_high_risk(self):
        sm = SynthesisStateMachine()
        ok, _ = sm.guard_security_fail(risk_score=0.8)
        assert ok

    def test_escalate_on_sandbox_side_effects(self):
        sm = SynthesisStateMachine()
        ok, _ = sm.guard_sandbox_ambiguous(
            sandbox_success=True,
            side_effects=[{"effect_type": "test"}],
            resource_used={"cpu_sec": 1.0, "memory_mb": 10.0},
        )
        assert ok
