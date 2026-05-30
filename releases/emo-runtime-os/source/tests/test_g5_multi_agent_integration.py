"""Phase G5 — Multi-Agent Runtime Integration Tests.  # LAW-26 LAW-27 RULE-4 RULE-5

End-to-end integration tests: spawn_agent → monitor_health → pause_agent
→ terminate_agent. Exercises lifecycle management, domain isolation,
health monitoring, and state machine transitions.

Ref: Canon LAW 26, LAW 27, RULE 4, RULE 5
Ref: artifacts/design/g5/04_integration_blueprint.md
"""

from __future__ import annotations

import pytest

from core.runtime.multi_agent.lifecycle_manager import AgentLifecycleManager
from core.runtime.multi_agent.lifecycle_state_machine import (
    AgentLifecycleState,
    LifecycleStateMachine,
)


def _make_manager() -> AgentLifecycleManager:
    return AgentLifecycleManager(state_machine=LifecycleStateMachine())


VALID_SPEC = {
    "agent_id": "spec_a1",
    "domain": "data_processing",
    "capability_profile": ["read", "write", "transform"],
    "resource_quota": {"max_cpu_sec": 60.0, "max_memory_mb": 256.0},
    "lifecycle_policy": {"max_runtime_sec": 3600, "heartbeat_interval_sec": 15},
}


class TestAgentLifecycleManager:
    """Agent lifecycle management: spawn → monitor → pause → terminate."""

    def test_spawn_agent_happy_path(self):
        mgr = _make_manager()
        result = mgr.spawn_agent(VALID_SPEC, mission_trace_id="msn_test")
        assert result["spawn_status"] == "spawning"
        assert result["agent_id"].startswith("agent_")
        assert result["assigned_domain"] == "data_processing"
        assert result["checkpoint_ref"].startswith("ckpt_")
        assert result["mission_trace_id"] == "msn_test"

    def test_spawn_agent_duplicate_domain_rejected(self):
        mgr = _make_manager()
        mgr.spawn_agent(VALID_SPEC)
        result = mgr.spawn_agent(VALID_SPEC)
        assert result["spawn_status"] == "failed"

    def test_spawn_agent_different_domain_unique_agents(self):
        mgr = _make_manager()
        r1 = mgr.spawn_agent(VALID_SPEC, mission_trace_id="m1")
        mgr.state_machine.reset()
        spec2 = {**VALID_SPEC, "domain": "monitoring"}
        r2 = mgr.spawn_agent(spec2, mission_trace_id="m2")
        assert r1["spawn_status"] == "spawning"
        assert r2["spawn_status"] == "spawning"
        assert r1["agent_id"] != r2["agent_id"]

    def test_spawn_agent_missing_domain_rejected(self):
        mgr = _make_manager()
        bad_spec = {k: v for k, v in VALID_SPEC.items() if k != "domain"}
        result = mgr.spawn_agent(bad_spec)
        assert result["spawn_status"] == "failed"

    def test_spawn_agent_missing_capability_rejected(self):
        mgr = _make_manager()
        bad_spec = {k: v for k, v in VALID_SPEC.items() if k != "capability_profile"}
        result = mgr.spawn_agent(bad_spec)
        assert result["spawn_status"] == "failed"

    def test_spawn_agent_missing_resource_quota_rejected(self):
        mgr = _make_manager()
        bad_spec = {k: v for k, v in VALID_SPEC.items() if k != "resource_quota"}
        result = mgr.spawn_agent(bad_spec)
        assert result["spawn_status"] == "failed"

    def test_monitor_health_running_agent(self):
        mgr = _make_manager()
        spawn = mgr.spawn_agent(VALID_SPEC)
        health = mgr.monitor_health(spawn["agent_id"])
        assert health["state"] == AgentLifecycleState.RUNNING.value
        assert health["health"] in ("healthy", "degraded")

    def test_monitor_health_unknown_agent(self):
        mgr = _make_manager()
        health = mgr.monitor_health("nonexistent_agent")
        assert health["state"] == AgentLifecycleState.TERMINATED.value
        assert health["health"] == "unreachable"

    def test_pause_agent_happy_path(self):
        mgr = _make_manager()
        spawn = mgr.spawn_agent(VALID_SPEC)
        result = mgr.pause_agent(spawn["agent_id"])
        assert result["state"] == AgentLifecycleState.PAUSED.value
        assert result["pause_timestamp_ns"] > 0

    def test_pause_agent_unknown(self):
        mgr = _make_manager()
        result = mgr.pause_agent("nonexistent")
        assert result["state"] == AgentLifecycleState.TERMINATED.value

    def test_terminate_agent_happy_path(self):
        mgr = _make_manager()
        spawn = mgr.spawn_agent(VALID_SPEC)
        result = mgr.terminate_agent(spawn["agent_id"], reason="test_complete")
        assert result["state"] == AgentLifecycleState.TERMINATED.value
        assert len(result["resources_released"]) > 0

    def test_terminate_agent_releases_domain(self):
        mgr = _make_manager()
        spawn = mgr.spawn_agent(VALID_SPEC)
        mgr.terminate_agent(spawn["agent_id"])
        mgr.state_machine.reset()
        spec2 = {**VALID_SPEC, "domain": "data_processing"}
        r2 = mgr.spawn_agent(spec2)
        assert r2["spawn_status"] == "spawning"

    def test_terminate_agent_unknown(self):
        mgr = _make_manager()
        result = mgr.terminate_agent("nonexistent")
        assert result["state"] == AgentLifecycleState.TERMINATED.value

    def test_is_registered_after_spawn(self):
        mgr = _make_manager()
        spawn = mgr.spawn_agent(VALID_SPEC)
        assert mgr.is_registered(spawn["agent_id"])

    def test_is_registered_after_terminate(self):
        mgr = _make_manager()
        spawn = mgr.spawn_agent(VALID_SPEC)
        mgr.terminate_agent(spawn["agent_id"])
        assert not mgr.is_registered(spawn["agent_id"])

    def test_agent_count(self):
        mgr = _make_manager()
        assert mgr.agent_count() == 0
        mgr.spawn_agent(VALID_SPEC, mission_trace_id="m1")
        mgr.state_machine.reset()
        mgr.spawn_agent({**VALID_SPEC, "domain": "d2"}, mission_trace_id="m2")
        assert mgr.agent_count() == 2

    def test_reset_clears_all_agents(self):
        mgr = _make_manager()
        mgr.spawn_agent(VALID_SPEC)
        mgr.spawn_agent({**VALID_SPEC, "domain": "d3"})
        mgr.reset()
        assert mgr.agent_count() == 0
        assert mgr.state_machine.current == AgentLifecycleState.IDLE

    def test_state_machine_property(self):
        mgr = _make_manager()
        assert mgr.state_machine.current == AgentLifecycleState.IDLE


class TestAgentLifecycleFailure:
    """Failure paths in agent lifecycle."""

    def test_spawn_then_pause_then_terminate(self):
        mgr = _make_manager()
        spawn = mgr.spawn_agent(VALID_SPEC)
        pause = mgr.pause_agent(spawn["agent_id"])
        assert pause["state"] == AgentLifecycleState.PAUSED.value
        term = mgr.terminate_agent(spawn["agent_id"])
        assert term["state"] == AgentLifecycleState.TERMINATED.value

    def test_reset_after_partial_state(self):
        mgr = _make_manager()
        mgr.spawn_agent(VALID_SPEC)
        mgr.spawn_agent({**VALID_SPEC, "domain": "d4"})
        mgr.reset()
        spawn = mgr.spawn_agent(VALID_SPEC)
        assert spawn["spawn_status"] == "spawning"
