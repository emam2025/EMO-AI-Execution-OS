"""Phase H1 — Session State Machine & Interaction Guards.  # LAW-10 LAW-24 RULE-2 RULE-3

Tests 6-state lifecycle with 8 Interaction Guards (I1–I8) and 12
transitions (G1–G12). Every transition enforces Canon LAW 10, RULE 2.

Ref: Canon LAW 10, LAW 24, RULE 1-4
Ref: artifacts/design/h1/03_session_state_machine.md
"""

from __future__ import annotations

import pytest

from core.runtime.computer_use.session_state_machine import (
    ComputerUseSessionStateMachine,
    InteractionGuardResult,
    SessionState,
)


@pytest.fixture
def sm() -> ComputerUseSessionStateMachine:
    return ComputerUseSessionStateMachine()


# ── Guard I1: Selector Validity ──────────────────────────────────

class TestGuardI1SelectorValidity:
    def test_valid_selector_passes(self, sm: ComputerUseSessionStateMachine):
        ok, _ = sm.guard_selector_valid("#my-button")
        assert ok

    def test_empty_selector_blocked(self, sm: ComputerUseSessionStateMachine):
        ok, msg = sm.guard_selector_valid("")
        assert not ok
        assert "I1" in msg


# ── Guard I2: Spatial Bounding Box ──────────────────────────────

class TestGuardI2SpatialBBox:
    def test_valid_coordinates_passes(self, sm: ComputerUseSessionStateMachine):
        ok, msg = sm.guard_spatial_bbox_verified(
            coordinates={"x": 100, "y": 200},
            viewport={"width": 1280, "height": 720},
        )
        assert ok

    def test_invalid_bbox_dimensions(self, sm: ComputerUseSessionStateMachine):
        ok, msg = sm.guard_spatial_bbox_verified(bounding_box=[0, 0, 0, 0])
        assert not ok
        assert "I2" in msg


# ── Guard I3: Capability Match ──────────────────────────────────

class TestGuardI3CapabilityMatch:
    def test_matching_capability_passes(self, sm: ComputerUseSessionStateMachine):
        ok, msg = sm.guard_capability_match(
            action_type="click",
            session_capabilities=["pointer_input"],
            sandbox_token="tok_a",
            expected_token="tok_a",
        )
        assert ok

    def test_missing_capability_blocked(self, sm: ComputerUseSessionStateMachine):
        ok, msg = sm.guard_capability_match(
            action_type="click",
            session_capabilities=["screenshot"],
        )
        assert not ok
        assert "I3" in msg

    def test_sandbox_token_mismatch_blocked(self, sm: ComputerUseSessionStateMachine):
        ok, msg = sm.guard_capability_match(
            action_type="click",
            session_capabilities=["pointer_input"],
            sandbox_token="tok_a",
            expected_token="tok_b",
        )
        assert not ok

    def test_no_action_type_blocked(self, sm: ComputerUseSessionStateMachine):
        ok, msg = sm.guard_capability_match(action_type="")
        assert not ok


# ── Guard I4: Session Isolation ─────────────────────────────────

class TestGuardI4SessionIsolation:
    def test_allowed_state_passes(self, sm: ComputerUseSessionStateMachine):
        ok, msg = sm.guard_session_isolation(allowed_states=[SessionState.INIT, SessionState.READY])
        assert ok

    def test_disallowed_state_blocked(self, sm: ComputerUseSessionStateMachine):
        sm.force_set(SessionState.TERMINATED)
        ok, msg = sm.guard_session_isolation(allowed_states=[SessionState.READY])
        assert not ok


# ── Guard I5: Vision Consistency ─────────────────────────────────

class TestGuardI5VisionConsistency:
    def test_matching_visual_hash_passes(self, sm: ComputerUseSessionStateMachine):
        ok, msg = sm.guard_vision_consistency(
            visual_context_hash="abc", current_visual_hash="abc",
        )
        assert ok

    def test_stale_visual_context_blocked(self, sm: ComputerUseSessionStateMachine):
        ok, msg = sm.guard_vision_consistency(
            visual_context_hash="abc", current_visual_hash="def",
        )
        assert not ok
        assert "I5" in msg

    def test_low_confidence_blocked(self, sm: ComputerUseSessionStateMachine):
        ok, msg = sm.guard_vision_consistency(confidence=0.5, min_confidence=0.7)
        assert not ok


# ── Guard I6: Journal Integrity ─────────────────────────────────

class TestGuardI6JournalIntegrity:
    def test_matching_hashes_passes(self, sm: ComputerUseSessionStateMachine):
        ok, msg = sm.guard_journal_integrity(expected_prev_hash="abc", actual_prev_hash="abc")
        assert ok

    def test_hash_mismatch_blocked(self, sm: ComputerUseSessionStateMachine):
        ok, msg = sm.guard_journal_integrity(expected_prev_hash="abc", actual_prev_hash="xyz")
        assert not ok


# ── Guard I7: Resource Quota ────────────────────────────────────

class TestGuardI7ResourceQuota:
    def test_within_limits_passes(self, sm: ComputerUseSessionStateMachine):
        ok, _ = sm.guard_resource_quota()
        assert ok

    def test_action_limit_reached_blocked(self, sm: ComputerUseSessionStateMachine):
        ok, msg = sm.guard_resource_quota(action_count=1000, max_actions=1000)
        assert not ok
        assert "I7" in msg

    def test_cpu_limit_reached_blocked(self, sm: ComputerUseSessionStateMachine):
        ok, msg = sm.guard_resource_quota(cpu_sec=120.0, max_cpu_sec=120.0)
        assert not ok

    def test_session_duration_exceeded_blocked(self, sm: ComputerUseSessionStateMachine):
        ok, msg = sm.guard_resource_quota(session_duration_sec=3600.0, max_session_sec=3600.0)
        assert not ok


# ── Guard I8: Replay Determinism ─────────────────────────────────

class TestGuardI8ReplayDeterminism:
    def test_matching_state_hashes_passes(self, sm: ComputerUseSessionStateMachine):
        ok, msg = sm.guard_replay_determinism(expected_state_hash="abc", actual_state_hash="abc")
        assert ok

    def test_hash_mismatch_blocked(self, sm: ComputerUseSessionStateMachine):
        ok, msg = sm.guard_replay_determinism(expected_state_hash="abc", actual_state_hash="xyz")
        assert not ok
        assert "I8" in msg


# ── Pre-Action Composite Guard ──────────────────────────────────

class TestPreActionCompositeGuard:
    def test_all_checks_pass(self, sm: ComputerUseSessionStateMachine):
        result = sm.check_pre_action(
            action_type="click",
            target_selector="#btn",
            coordinates={"x": 100, "y": 200},
            viewport={"width": 1280, "height": 720},
            session_capabilities=["pointer_input"],
            sandbox_token="tok",
            expected_token="tok",
            confidence=0.9,
            min_confidence=0.7,
        )
        assert result == InteractionGuardResult.PASSED

    def test_blocked_on_selector(self, sm: ComputerUseSessionStateMachine):
        result = sm.check_pre_action(target_selector="")
        assert result == InteractionGuardResult.BLOCKED_SELECTOR

    def test_blocked_on_capability(self, sm: ComputerUseSessionStateMachine):
        result = sm.check_pre_action(
            action_type="execute_script",
            target_selector="#x",
            session_capabilities=["navigate"],
        )
        assert result == InteractionGuardResult.BLOCKED_CAPABILITY


# ── State Machine Transitions ───────────────────────────────────

class TestStateMachineTransitions:
    def test_initial_state(self, sm: ComputerUseSessionStateMachine):
        assert sm.current == SessionState.INIT

    def test_init_to_ready(self, sm: ComputerUseSessionStateMachine):
        ok, _ = sm.transition(SessionState.READY, isolation_context=ISOLATION_CTX,
                               capabilities=["navigate"], sandbox_token="tok")
        assert ok
        assert sm.current == SessionState.READY

    def test_ready_to_interacting(self, sm: ComputerUseSessionStateMachine):
        sm.force_set(SessionState.READY)
        ok, _ = sm.transition(SessionState.INTERACTING, action_type="click", sandbox_token="tok")
        assert ok
        assert sm.current == SessionState.INTERACTING

    def test_interacting_to_ready(self, sm: ComputerUseSessionStateMachine):
        sm.force_set(SessionState.INTERACTING)
        ok, _ = sm.transition(SessionState.READY)
        assert ok

    def test_interacting_to_paused(self, sm: ComputerUseSessionStateMachine):
        sm.force_set(SessionState.INTERACTING)
        ok, _ = sm.transition(SessionState.PAUSED, has_checkpoint=True)
        assert ok
        assert sm.current == SessionState.PAUSED

    def test_interacting_to_checkpointed(self, sm: ComputerUseSessionStateMachine):
        sm.force_set(SessionState.INTERACTING)
        ok, _ = sm.transition(SessionState.CHECKPOINTED, state_valid=True)
        assert ok
        assert sm.current == SessionState.CHECKPOINTED

    def test_terminal_state_blocks(self, sm: ComputerUseSessionStateMachine):
        sm.force_set(SessionState.TERMINATED)
        ok, msg = sm.transition(SessionState.READY)
        assert not ok
        assert "Terminal" in msg

    def test_invalid_transition_rejected(self, sm: ComputerUseSessionStateMachine):
        ok, msg = sm.transition(SessionState.TERMINATED, isolation_context={},
                                 capabilities=[], sandbox_token="")
        assert not ok
        assert "Invalid" in msg

    def test_history_records(self, sm: ComputerUseSessionStateMachine):
        sm.force_set(SessionState.READY)
        sm.transition(SessionState.INTERACTING, action_type="click", sandbox_token="tok")
        assert len(sm.history) == 1
        assert sm.history[0]["to"] == SessionState.INTERACTING.value

    def test_reset(self, sm: ComputerUseSessionStateMachine):
        sm.force_set(SessionState.TERMINATED)
        sm.reset()
        assert sm.current == SessionState.INIT
        assert len(sm.history) == 0


# ── Deterministic Hashing ───────────────────────────────────────

class TestDeterministicHash:
    def test_same_inputs_same_hash(self):
        sm = ComputerUseSessionStateMachine()
        h1 = sm.compute_state_hash("init", "click", "#btn", "", 1, "vhash", "passed")
        h2 = sm.compute_state_hash("init", "click", "#btn", "", 1, "vhash", "passed")
        assert h1 == h2

    def test_different_action_different_hash(self):
        sm = ComputerUseSessionStateMachine()
        h1 = sm.compute_state_hash("init", "click", "#a", "", 1, "vh", "passed")
        h2 = sm.compute_state_hash("init", "type_text", "#b", "x", 2, "vh", "passed")
        assert h1 != h2


ISOLATION_CTX = {
    "sandbox_id": "sb_test",
    "network_policy": {"allowlist": []},
    "filesystem_policy": {"read_paths": []},
    "capability_guard_token": "tok_test",
}
