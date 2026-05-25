"""Phase G5 — Agent Lifecycle State Machine Isolation Guards.  # LAW-11 LAW-23 LAW-24 LAW-25 LAW-26 LAW-27 RULE-4 RULE-5

Tests 12 transitions with 7 Isolation Guards (I1–I7) and 6 Planning Guards (H1–H6).
Each guard enforces Canon LAW 23-27 and RULE 4.

Ref: Canon LAW 23-27, RULE 1-5
Ref: artifacts/design/g5/03_agent_lifecycle_machine.md
"""

from __future__ import annotations

import pytest

from core.runtime.models.multiagent_models import AgentLifecycleState
from core.runtime.multi_agent.lifecycle_state_machine import LifecycleStateMachine


def _make_sm() -> LifecycleStateMachine:
    return LifecycleStateMachine()


VALID_SPEC = {
    "domain": "data_processing",
    "capability_profile": ["read", "write"],
    "resource_quota": {"max_cpu_sec": 60.0},
}


class TestIsolationGuardsI1toI4:
    """I1–I4: Spec and spawn guards."""

    def test_initial_state_is_idle(self):
        sm = _make_sm()
        assert sm.current == AgentLifecycleState.IDLE

    def test_I1_missing_domain_rejected(self):
        sm = _make_sm()
        ok, msg = sm.guard_spec_valid({"capability_profile": [], "resource_quota": {}})
        assert not ok
        assert "I1" in msg

    def test_I2_missing_capability_profile_rejected(self):
        sm = _make_sm()
        ok, msg = sm.guard_spec_valid({"domain": "d", "resource_quota": {}})
        assert not ok
        assert "capability_profile" in msg

    def test_I3_missing_resource_quota_rejected(self):
        sm = _make_sm()
        ok, msg = sm.guard_spec_valid({"domain": "d", "capability_profile": ["read"]})
        assert not ok
        assert "resource_quota" in msg

    def test_spec_valid_passes_all_checks(self):
        sm = _make_sm()
        ok, msg = sm.guard_spec_valid(VALID_SPEC)
        assert ok
        assert msg == ""

    def test_I5_spawn_needs_resources(self):
        sm = _make_sm()
        ok, msg = sm.guard_spawn_success(resources_allocated=False)
        assert not ok
        assert "I5" in msg

    def test_spawn_success_with_resources(self):
        sm = _make_sm()
        ok, msg = sm.guard_spawn_success(resources_allocated=True)
        assert ok


class TestIsolationGuardsI6toI7:
    """I6–I7: Pause and termination guards."""

    def test_I6_pause_needs_checkpoint(self):
        sm = _make_sm()
        ok, msg = sm.guard_can_pause(has_checkpoint=False)
        assert not ok
        assert "I6" in msg

    def test_I6_pause_blocked_with_inflight(self):
        sm = _make_sm()
        ok, msg = sm.guard_can_pause(has_checkpoint=True, has_inflight=True)
        assert not ok
        assert "Cannot pause" in msg

    def test_I6_pause_allows_with_checkpoint_no_inflight(self):
        sm = _make_sm()
        ok, msg = sm.guard_can_pause(has_checkpoint=True, has_inflight=False)
        assert ok

    def test_I7_termination_needs_checkpoint(self):
        sm = _make_sm()
        ok, msg = sm.guard_termination(has_checkpoint=False, lifecycle_expired=True)
        assert not ok
        assert "I7" in msg

    def test_I7_termination_needs_lifecycle_expired(self):
        sm = _make_sm()
        ok, msg = sm.guard_termination(has_checkpoint=True, lifecycle_expired=False)
        assert not ok
        assert "Lifecycle" in msg

    def test_I7_termination_allows_with_both(self):
        sm = _make_sm()
        ok, msg = sm.guard_termination(has_checkpoint=True, lifecycle_expired=True)
        assert ok


class TestNormalTransitions:
    """12 transitions between 6 states."""

    def test_transition_idle_to_spawning(self):
        sm = _make_sm()
        ok, _ = sm.transition(AgentLifecycleState.SPAWNING, spec=VALID_SPEC)
        assert ok
        assert sm.current == AgentLifecycleState.SPAWNING

    def test_transition_idle_to_terminated_spec_invalid(self):
        sm = _make_sm()
        ok, _ = sm.transition(AgentLifecycleState.TERMINATED, spec={"domain": "", "capability_profile": []})
        assert ok
        assert sm.current == AgentLifecycleState.TERMINATED

    def test_transition_spawning_to_running(self):
        sm = _make_sm()
        sm._current = AgentLifecycleState.SPAWNING
        ok, _ = sm.transition(AgentLifecycleState.RUNNING, resources_allocated=True)
        assert ok
        assert sm.current == AgentLifecycleState.RUNNING

    def test_transition_spawning_to_terminated_resources_fail(self):
        sm = _make_sm()
        ok, _ = sm.transition(AgentLifecycleState.SPAWNING, spec=VALID_SPEC)
        assert ok
        ok2, _ = sm.transition(AgentLifecycleState.RUNNING, resources_allocated=False)
        assert not ok2
        term, _ = sm.transition(AgentLifecycleState.TERMINATED, resources_allocated=False)
        assert term
        assert sm.current == AgentLifecycleState.TERMINATED

    def test_transition_running_to_paused(self):
        sm = _make_sm()
        sm._current = AgentLifecycleState.RUNNING
        ok, _ = sm.transition(AgentLifecycleState.PAUSED, has_checkpoint=True, has_inflight=False)
        assert ok
        assert sm.current == AgentLifecycleState.PAUSED

    def test_transition_running_to_degraded(self):
        sm = _make_sm()
        sm._current = AgentLifecycleState.RUNNING
        ok, _ = sm.transition(AgentLifecycleState.DEGRADED, resource_ratio=0.95)
        assert ok
        assert sm.current == AgentLifecycleState.DEGRADED

    def test_transition_running_to_terminated(self):
        sm = _make_sm()
        sm._current = AgentLifecycleState.RUNNING
        ok, _ = sm.transition(AgentLifecycleState.TERMINATED, has_checkpoint=True, lifecycle_expired=True)
        assert ok
        assert sm.current == AgentLifecycleState.TERMINATED

    def test_transition_paused_to_running_resume(self):
        sm = _make_sm()
        sm._current = AgentLifecycleState.PAUSED
        ok, _ = sm.transition(AgentLifecycleState.RUNNING, checkpoint_valid=True, resources_available=True)
        assert ok
        assert sm.current == AgentLifecycleState.RUNNING

    def test_transition_paused_to_terminated_timeout(self):
        sm = _make_sm()
        sm._current = AgentLifecycleState.PAUSED
        ok, _ = sm.transition(AgentLifecycleState.TERMINATED, pause_duration_sec=3601.0)
        assert ok
        assert sm.current == AgentLifecycleState.TERMINATED

    def test_transition_degraded_to_running_recovered(self):
        sm = _make_sm()
        sm._current = AgentLifecycleState.DEGRADED
        ok, _ = sm.transition(AgentLifecycleState.RUNNING, health_restored=True)
        assert ok
        assert sm.current == AgentLifecycleState.RUNNING

    def test_transition_degraded_to_terminated_unrecoverable(self):
        sm = _make_sm()
        sm._current = AgentLifecycleState.DEGRADED
        ok, _ = sm.transition(AgentLifecycleState.TERMINATED, health_restored=False)
        assert ok
        assert sm.current == AgentLifecycleState.TERMINATED

    def test_invalid_transition_rejected(self):
        sm = _make_sm()
        ok, msg = sm.transition(AgentLifecycleState.PAUSED)
        assert not ok
        assert "Invalid" in msg

    def test_terminal_state_blocks_transitions(self):
        sm = _make_sm()
        sm._current = AgentLifecycleState.TERMINATED
        ok, msg = sm.transition(AgentLifecycleState.SPAWNING)
        assert not ok
        assert "Terminal" in msg


class TestStateMachineReset:
    """Reset, terminal check, force_set, history."""

    def test_reset_goes_to_idle(self):
        sm = _make_sm()
        sm._current = AgentLifecycleState.TERMINATED
        sm.reset()
        assert sm.current == AgentLifecycleState.IDLE

    def test_is_terminal_true(self):
        sm = _make_sm()
        sm._current = AgentLifecycleState.TERMINATED
        assert sm.is_terminal()

    def test_is_terminal_false(self):
        sm = _make_sm()
        assert not sm.is_terminal()

    def test_force_set(self):
        sm = _make_sm()
        sm.force_set(AgentLifecycleState.PAUSED)
        assert sm.current == AgentLifecycleState.PAUSED

    def test_history_records_transitions(self):
        sm = _make_sm()
        sm.transition(AgentLifecycleState.SPAWNING, spec=VALID_SPEC)
        assert len(sm.history) == 1
        assert sm.history[0]["from"] == AgentLifecycleState.IDLE.value
        assert sm.history[0]["to"] == AgentLifecycleState.SPAWNING.value

    def test_reset_clears_history(self):
        sm = _make_sm()
        sm.transition(AgentLifecycleState.SPAWNING, spec=VALID_SPEC)
        sm.reset()
        assert len(sm.history) == 0


class TestPlanningGuards:
    """H1–H6: Planning guard enforcement."""

    def test_guard_can_resume_needs_both(self):
        sm = _make_sm()
        ok, msg = sm.guard_can_resume(checkpoint_valid=False, resources_available=True)
        assert not ok
        assert "Cannot resume" in msg

    def test_guard_can_resume_allows_with_both(self):
        sm = _make_sm()
        ok, msg = sm.guard_can_resume(checkpoint_valid=True, resources_available=True)
        assert ok

    def test_guard_pause_timeout_blocks_below_threshold(self):
        sm = _make_sm()
        ok, msg = sm.guard_pause_timeout(pause_duration_sec=60.0, max_pause_sec=3600.0)
        assert not ok
        assert "60s < 3600s" in msg

    def test_guard_pause_timeout_allows_at_threshold(self):
        sm = _make_sm()
        ok, msg = sm.guard_pause_timeout(pause_duration_sec=3600.0, max_pause_sec=3600.0)
        assert ok

    def test_guard_recovered_blocks_if_not_restored(self):
        sm = _make_sm()
        ok, msg = sm.guard_recovered(health_restored=False)
        assert not ok

    def test_guard_recovered_allows_if_restored(self):
        sm = _make_sm()
        ok, msg = sm.guard_recovered(health_restored=True)
        assert ok

    def test_guard_unrecoverable_blocks_if_restored(self):
        sm = _make_sm()
        ok, msg = sm.guard_unrecoverable(health_restored=True)
        assert not ok

    def test_guard_unrecoverable_allows_if_not_restored(self):
        sm = _make_sm()
        ok, msg = sm.guard_unrecoverable(health_restored=False)
        assert ok

    def test_guard_health_degraded_blocks_below_threshold(self):
        sm = _make_sm()
        ok, msg = sm.guard_health_degraded(resource_ratio=0.5)
        assert not ok

    def test_guard_health_degraded_allows_at_threshold(self):
        sm = _make_sm()
        ok, msg = sm.guard_health_degraded(resource_ratio=0.9)
        assert ok

    def test_guard_spec_invalid_allows_for_none(self):
        sm = _make_sm()
        ok, msg = sm.guard_spec_invalid(None)
        assert ok

    def test_guard_spawn_failed_allows_for_no_resources(self):
        sm = _make_sm()
        ok, msg = sm.guard_spawn_failed(resources_allocated=False)
        assert ok
