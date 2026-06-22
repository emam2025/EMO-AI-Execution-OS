"""Tests for runtime AgentLifecycleManager (9-state lifecycle).

Covers: register, transition_state, heartbeat, check_stale_agents, deregister,
event emission, lease management integration, and edge cases.

Ref: AD-003 — previously zero test coverage for runtime agent lifecycle layer.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from core.runtime.agents.agent_lifecycle import (
    AgentLifecycleManager,
    AgentSpec,
    AgentState,
)


def _spec(**overrides: object) -> AgentSpec:
    kwargs: dict = {
        "agent_id": "test-agent-1",
        "name": "Test Agent",
        "capabilities": {"read": True, "write": False},
    }
    kwargs.update(overrides)
    return AgentSpec(**kwargs)


@pytest.fixture
def mgr() -> AgentLifecycleManager:
    return AgentLifecycleManager()


class TestRegister:
    def test_register_creates_agent(self, mgr: AgentLifecycleManager) -> None:
        agent_id = mgr.register(_spec())
        assert agent_id == "test-agent-1"
        agent = mgr.get_agent(agent_id)
        assert agent is not None
        assert agent.state == AgentState.IDLE

    def test_register_generates_id_when_empty(self, mgr: AgentLifecycleManager) -> None:
        agent_id = mgr.register(_spec(agent_id=""))
        assert agent_id.startswith("agent-")
        assert mgr.get_agent(agent_id) is not None

    def test_register_creates_lease_with_manager(self) -> None:
        lease_mgr = MagicMock()
        lease_mgr.acquire_lease.return_value = "lease-123"
        lm = AgentLifecycleManager(lease_manager=lease_mgr)
        lm.register(_spec())
        lease_mgr.acquire_lease.assert_called_once()

    def test_register_handles_lease_failure(self) -> None:
        lease_mgr = MagicMock()
        lease_mgr.acquire_lease.return_value = None
        lm = AgentLifecycleManager(lease_manager=lease_mgr)
        agent_id = lm.register(_spec())
        agent = lm.get_agent(agent_id)
        assert agent is not None
        assert agent.lease_id == ""

    def test_register_events_recorded(self, mgr: AgentLifecycleManager) -> None:
        mgr.register(_spec())
        assert len(mgr._event_history) == 1
        assert mgr._event_history[0].event_type == "registered"

    def test_active_agents_after_register(self, mgr: AgentLifecycleManager) -> None:
        mgr.register(_spec())
        assert mgr.agent_count == 1
        assert len(mgr.active_agents) == 1


class TestTransitionState:
    def test_valid_idle_to_planning(self, mgr: AgentLifecycleManager) -> None:
        mgr.register(_spec())
        assert mgr.transition_state("test-agent-1", AgentState.PLANNING)
        agent = mgr.get_agent("test-agent-1")
        assert agent is not None
        assert agent.state == AgentState.PLANNING

    def test_valid_planning_to_executing(self, mgr: AgentLifecycleManager) -> None:
        mgr.register(_spec())
        mgr.transition_state("test-agent-1", AgentState.PLANNING)
        assert mgr.transition_state("test-agent-1", AgentState.EXECUTING)
        agent = mgr.get_agent("test-agent-1")
        assert agent is not None
        assert agent.state == AgentState.EXECUTING

    def test_invalid_transition_returns_false(self, mgr: AgentLifecycleManager) -> None:
        mgr.register(_spec())
        assert mgr.transition_state("test-agent-1", AgentState.EXECUTING) is False

    def test_transition_unknown_agent(self, mgr: AgentLifecycleManager) -> None:
        assert mgr.transition_state("nonexistent", AgentState.PLANNING) is False

    def test_transition_from_terminal_blocked(self, mgr: AgentLifecycleManager) -> None:
        mgr.register(_spec())
        mgr.transition_state("test-agent-1", AgentState.PLANNING)
        mgr.transition_state("test-agent-1", AgentState.FAILED)
        assert mgr.transition_state("test-agent-1", AgentState.PLANNING) is False

    def test_transition_events_recorded(self, mgr: AgentLifecycleManager) -> None:
        mgr.register(_spec())
        before = len(mgr._event_history)
        mgr.transition_state("test-agent-1", AgentState.PLANNING)
        assert len(mgr._event_history) == before + 1
        assert mgr._event_history[-1].event_type == "state_changed"

    def test_full_lifecycle(self, mgr: AgentLifecycleManager) -> None:
        mgr.register(_spec())
        mgr.transition_state("test-agent-1", AgentState.PLANNING)
        mgr.transition_state("test-agent-1", AgentState.EXECUTING)
        mgr.transition_state("test-agent-1", AgentState.REVIEWING)
        mgr.transition_state("test-agent-1", AgentState.COMPLETED)
        agent = mgr.get_agent("test-agent-1")
        assert agent is not None
        assert agent.state == AgentState.COMPLETED


class TestHeartbeat:
    def test_heartbeat_updates_timestamp(self, mgr: AgentLifecycleManager) -> None:
        mgr.register(_spec())
        agent = mgr.get_agent("test-agent-1")
        assert agent is not None
        old_ts = agent.last_heartbeat
        time.sleep(0.001)
        assert mgr.heartbeat("test-agent-1")
        assert agent.last_heartbeat > old_ts

    def test_heartbeat_unknown_agent(self, mgr: AgentLifecycleManager) -> None:
        assert mgr.heartbeat("nonexistent") is False

    def test_heartbeat_terminal_agent(self, mgr: AgentLifecycleManager) -> None:
        mgr.register(_spec())
        mgr.transition_state("test-agent-1", AgentState.DEREGISTERED)
        assert mgr.heartbeat("test-agent-1") is False

    def test_heartbeat_recovers_from_stale(self, mgr: AgentLifecycleManager) -> None:
        mgr.register(_spec())
        mgr.transition_state("test-agent-1", AgentState.PLANNING)

        agent = mgr.get_agent("test-agent-1")
        assert agent is not None
        agent.last_heartbeat = 0
        agent.state = AgentState.STALE

        assert mgr.heartbeat("test-agent-1")
        assert agent.state == AgentState.IDLE


class TestCheckStaleAgents:
    def test_stale_detection(self, mgr: AgentLifecycleManager) -> None:
        mgr.register(_spec())
        mgr.transition_state("test-agent-1", AgentState.PLANNING)

        agent = mgr.get_agent("test-agent-1")
        assert agent is not None
        agent.last_heartbeat = 0

        stale = mgr.check_stale_agents()
        assert "test-agent-1" in stale
        assert agent.state == AgentState.STALE

    def test_stale_skips_terminal(self, mgr: AgentLifecycleManager) -> None:
        mgr.register(_spec())
        mgr.transition_state("test-agent-1", AgentState.DEREGISTERED)
        assert mgr.check_stale_agents() == []

    def test_active_agents_not_stale(self, mgr: AgentLifecycleManager) -> None:
        mgr.register(_spec())
        mgr.transition_state("test-agent-1", AgentState.PLANNING)
        agent = mgr.get_agent("test-agent-1")
        assert agent is not None
        agent.last_heartbeat = time.time()
        assert mgr.check_stale_agents() == []

    def test_stale_to_offline_after_timeout(self, mgr: AgentLifecycleManager) -> None:
        mgr.register(_spec())
        mgr.transition_state("test-agent-1", AgentState.PLANNING)
        agent = mgr.get_agent("test-agent-1")
        assert agent is not None

        agent.last_heartbeat = 0
        mgr.check_stale_agents()
        assert agent.state == AgentState.STALE

        agent.last_heartbeat = 0
        stale = mgr.check_stale_agents()
        assert "test-agent-1" in stale
        assert agent.state == AgentState.OFFLINE


class TestDeregister:
    def test_deregister_removes_agent(self, mgr: AgentLifecycleManager) -> None:
        mgr.register(_spec())
        assert mgr.deregister("test-agent-1")
        assert mgr.get_agent("test-agent-1") is None

    def test_deregister_releases_lease(self) -> None:
        lease_mgr = MagicMock()
        lease_mgr.acquire_lease.return_value = "lease-123"
        lm = AgentLifecycleManager(lease_manager=lease_mgr)
        lm.register(_spec())
        lm.deregister("test-agent-1")
        lease_mgr.release_lease.assert_called_with("lease-123")

    def test_deregister_unknown_agent(self, mgr: AgentLifecycleManager) -> None:
        assert mgr.deregister("nonexistent") is False

    def test_deregister_records_event(self, mgr: AgentLifecycleManager) -> None:
        mgr.register(_spec())
        before = len(mgr._event_history)
        mgr.deregister("test-agent-1")
        assert len(mgr._event_history) == before + 1
        assert mgr._event_history[-1].event_type == "deregistered"

    def test_active_agents_decreases(self, mgr: AgentLifecycleManager) -> None:
        mgr.register(_spec())
        assert mgr.agent_count == 1
        mgr.deregister("test-agent-1")
        assert mgr.agent_count == 0


class TestEventBusIntegration:
    def test_register_publishes_event(self) -> None:
        bus = MagicMock()
        mgr = AgentLifecycleManager(event_bus=bus)
        mgr.register(_spec())
        bus.publish.assert_called_once()

    def test_transition_publishes_event(self) -> None:
        bus = MagicMock()
        mgr = AgentLifecycleManager(event_bus=bus)
        mgr.register(_spec())
        bus.publish.reset_mock()
        mgr.transition_state("test-agent-1", AgentState.PLANNING)
        bus.publish.assert_called_once()

    def test_deregister_publishes_event(self) -> None:
        bus = MagicMock()
        mgr = AgentLifecycleManager(event_bus=bus)
        mgr.register(_spec())
        bus.publish.reset_mock()
        mgr.deregister("test-agent-1")
        bus.publish.assert_called_once()

    def test_event_bus_error_does_not_crash(self) -> None:
        bus = MagicMock()
        bus.publish.side_effect = RuntimeError("bus down")
        mgr = AgentLifecycleManager(event_bus=bus)
        mgr.register(_spec())
        assert mgr.agent_count == 1
