"""Tests for Agent Lifecycle Manager (Strict State Machine).

Ref: RC16.8.2 — Agent Lifecycle Manager
"""

import pytest

from core.agents.lifecycle_manager import AgentLifecycleManager
from core.models.agent import AgentStatus


class MockResourceManager:
    """Mock IResourceManager for testing."""

    def __init__(self):
        self.resources = {"agent-001": "mock", "agent-002": "mock"}

    def get_resource(self, agent_id):
        return self.resources.get(agent_id)


@pytest.fixture
def manager():
    return AgentLifecycleManager(MockResourceManager())


# ── Test Valid Transitions ─────────────────────────────────────────────────


def test_activate_created_agent(manager):
    """CREATED → ACTIVE (valid)"""
    res = manager.activate("agent-001")
    assert res["success"] is True
    assert res["status"] == "active"


def test_suspend_active_agent(manager):
    """ACTIVE → SUSPENDED (valid)"""
    manager.activate("agent-001")
    res = manager.suspend("agent-001", "maintenance")
    assert res["success"] is True
    assert res["status"] == "suspended"


def test_activate_suspended_agent(manager):
    """SUSPENDED → ACTIVE (valid)"""
    manager.activate("agent-001")
    manager.suspend("agent-001", "maintenance")
    res = manager.activate("agent-001")
    assert res["success"] is True
    assert res["status"] == "active"


def test_terminate_from_created(manager):
    """CREATED → TERMINATED (valid)"""
    res = manager.terminate("agent-002", "end_of_contract")
    assert res["success"] is True
    assert res["status"] == "terminated"


def test_terminate_from_active(manager):
    """ACTIVE → TERMINATED (valid)"""
    manager.activate("agent-002")
    res = manager.terminate("agent-002", "end_of_contract")
    assert res["success"] is True
    assert res["status"] == "terminated"


def test_terminate_from_suspended(manager):
    """SUSPENDED → TERMINATED (valid)"""
    manager.activate("agent-001")
    manager.suspend("agent-001", "maintenance")
    res = manager.terminate("agent-001", "end_of_contract")
    assert res["success"] is True
    assert res["status"] == "terminated"


# ── Test Invalid Transitions (TERMINATED = Final) ─────────────────────────


def test_cannot_activate_terminated(manager):
    """TERMINATED → ACTIVE (invalid)"""
    manager.activate("agent-002")
    manager.terminate("agent-002", "test")
    res = manager.activate("agent-002")
    assert res["success"] is False
    assert "Cannot activate terminated" in res["error"]


def test_cannot_suspend_terminated(manager):
    """TERMINATED → SUSPENDED (invalid)"""
    manager.activate("agent-001")
    manager.terminate("agent-001", "test")
    res = manager.suspend("agent-001", "test")
    assert res["success"] is False
    assert "Cannot suspend terminated" in res["error"]


def test_cannot_terminate_twice(manager):
    """TERMINATED → TERMINATED (invalid)"""
    manager.terminate("agent-001", "first")
    res = manager.terminate("agent-001", "second")
    assert res["success"] is False
    assert "already terminated" in res["error"]


def test_cannot_suspend_already_suspended(manager):
    """SUSPENDED → SUSPENDED (invalid)"""
    manager.activate("agent-001")
    manager.suspend("agent-001", "first")
    res = manager.suspend("agent-001", "second")
    assert res["success"] is False
    assert "Cannot suspend suspended" in res["error"]


# ── Test Edge Cases ──────────────────────────────────────────────────────


def test_activate_already_active(manager):
    """ACTIVE → ACTIVE (idempotent)"""
    manager.activate("agent-001")
    res = manager.activate("agent-001")
    assert res["success"] is True
    assert "Already active" in res["note"]


def test_get_status_nonexistent(manager):
    """Agent not found."""
    res = manager.get_status("agent-999")
    assert res["exists"] is False


def test_get_status_after_transitions(manager):
    """Status tracking through multiple transitions."""
    res = manager.get_status("agent-001")
    assert res["exists"] is True
    assert res["status"] == "created"

    manager.activate("agent-001")
    res = manager.get_status("agent-001")
    assert res["status"] == "active"

    manager.suspend("agent-001", "maintenance")
    res = manager.get_status("agent-001")
    assert res["status"] == "suspended"

    manager.terminate("agent-001", "done")
    res = manager.get_status("agent-001")
    assert res["status"] == "terminated"


# ── Test Audit Trail ──────────────────────────────────────────────────────


def test_audit_trail_recorded(manager):
    """Every transition is recorded in audit trail."""
    manager.activate("agent-001")
    manager.suspend("agent-001", "maintenance")
    manager.terminate("agent-001", "done")

    assert len(manager._audit.action_log) == 3
    assert manager._audit.action_log[0]["action"] == "lifecycle.activate"
    assert manager._audit.action_log[1]["action"] == "lifecycle.suspend"
    assert manager._audit.action_log[2]["action"] == "lifecycle.terminate"


# ── Test Agent Not Found ─────────────────────────────────────────────────


def test_activate_nonexistent(manager):
    res = manager.activate("agent-999")
    assert res["success"] is False
    assert res["error"] == "Agent not found"


def test_suspend_nonexistent(manager):
    res = manager.suspend("agent-999", "test")
    assert res["success"] is False
    assert res["error"] == "Agent not found"


def test_terminate_nonexistent(manager):
    res = manager.terminate("agent-999", "test")
    assert res["success"] is False
    assert res["error"] == "Agent not found"


# ── Test Event Publishing ─────────────────────────────────────────────


class MockEventBus:
    """Mock IEventBus for testing event publishing."""

    def __init__(self):
        self.published = []

    async def publish(self, topic, event):
        self.published.append({"topic": topic, "event": event})

    def subscribe(self, topic, handler):
        return "mock-sub-id"

    def unsubscribe(self, subscription_id):
        pass


@pytest.mark.asyncio
async def test_publish_event_on_activate():
    """Publish event when agent is activated."""
    from core.models.event import EventTopic, ExecutionEvent

    event_bus = MockEventBus()
    manager = AgentLifecycleManager(MockResourceManager(), event_bus=event_bus)
    result = manager.activate("agent-001")

    assert result["success"] is True
    # Give event loop time to process the task
    import asyncio
    await asyncio.sleep(0.01)
    assert len(event_bus.published) == 1
    assert event_bus.published[0]["topic"] == EventTopic.STATE_TRANSITION


@pytest.mark.asyncio
async def test_publish_event_on_suspend():
    """Publish event when agent is suspended."""
    from core.models.event import EventTopic

    event_bus = MockEventBus()
    manager = AgentLifecycleManager(MockResourceManager(), event_bus=event_bus)
    manager.activate("agent-001")
    result = manager.suspend("agent-001", "maintenance")

    assert result["success"] is True
    import asyncio
    await asyncio.sleep(0.01)
    assert len(event_bus.published) == 2  # activate + suspend
    assert event_bus.published[1]["topic"] == EventTopic.STATE_TRANSITION


@pytest.mark.asyncio
async def test_publish_event_on_terminate():
    """Publish event when agent is terminated."""
    from core.models.event import EventTopic

    event_bus = MockEventBus()
    manager = AgentLifecycleManager(MockResourceManager(), event_bus=event_bus)
    manager.activate("agent-001")
    result = manager.terminate("agent-001", "done")

    assert result["success"] is True
    import asyncio
    await asyncio.sleep(0.01)
    assert len(event_bus.published) == 2  # activate + terminate
    assert event_bus.published[1]["topic"] == EventTopic.STATE_TRANSITION


@pytest.mark.asyncio
async def test_no_event_bus_still_works():
    """Lifecycle works without event_bus."""
    manager = AgentLifecycleManager(MockResourceManager(), event_bus=None)
    result = manager.activate("agent-001")
    assert result["success"] is True
