"""Tests for Rollback Engine.

6 independent tests covering rollback, failure handling, and event-driven triggers.

Ref: P8.3 — Rollback & Containment
"""

import asyncio

import pytest

from core.governance.rollback_engine import RollbackEngine
from core.models.event import EventTopic, ExecutionEvent
from core.models.rollback import RollbackScope, RollbackStatus


class MockEventBus:
    """Mock IEventBus for testing event publishing and subscription."""

    def __init__(self):
        self.published = []
        self.subscriptions = {}

    async def publish(self, topic, event):
        self.published.append({"topic": topic, "event": event})

    def subscribe(self, topic, handler):
        sub_id = f"sub-{len(self.subscriptions)}"
        self.subscriptions[sub_id] = {"topic": topic, "handler": handler}
        return sub_id

    def unsubscribe(self, subscription_id):
        self.subscriptions.pop(subscription_id, None)


@pytest.mark.asyncio
async def test_register_and_trigger_rollback_success():
    """Registered handler should be called and action recorded as EXECUTED."""
    engine = RollbackEngine()

    async def success_handler(target_id: str, reason: str) -> bool:
        return True

    engine.register_handler(RollbackScope.AGENT, success_handler)
    action = await engine.trigger_rollback(
        scope=RollbackScope.AGENT,
        target_id="agent-001",
        reason="Test rollback",
    )

    assert action.status == RollbackStatus.EXECUTED
    assert action.target_id == "agent-001"
    assert action.scope == RollbackScope.AGENT

    audit = engine.get_audit_log("agent-001")
    assert len(audit) == 1
    assert audit[0].status == RollbackStatus.EXECUTED


@pytest.mark.asyncio
async def test_rollback_handler_failure_recorded_as_failed():
    """Handler returning False should record action as FAILED."""
    engine = RollbackEngine()

    async def failing_handler(target_id: str, reason: str) -> bool:
        return False

    engine.register_handler(RollbackScope.NODE, failing_handler)
    action = await engine.trigger_rollback(
        scope=RollbackScope.NODE,
        target_id="node-001",
        reason="Handler will fail",
    )

    assert action.status == RollbackStatus.FAILED
    assert action.target_id == "node-001"

    audit = engine.get_audit_log("node-001")
    assert len(audit) == 1
    assert audit[0].status == RollbackStatus.FAILED


@pytest.mark.asyncio
async def test_auto_rollback_on_critical_guardrail_alert():
    """Critical guardrail alert should trigger automatic rollback."""
    event_bus = MockEventBus()
    engine = RollbackEngine(event_bus=event_bus)

    async def success_handler(target_id: str, reason: str) -> bool:
        return True

    engine.register_handler(RollbackScope.AGENT, success_handler)
    engine.subscribe_to_events()

    # Simulate critical guardrail alert
    alert_event = ExecutionEvent(
        topic=EventTopic.GUARDRAIL_ALERT,
        trace_id="test-alert-001",
        payload={
            "agent_id": "agent-002",
            "severity": "critical",
            "drift_type": "behavioral_drift",
        },
    )

    # Trigger the handler directly
    handler = event_bus.subscriptions[list(event_bus.subscriptions.keys())[0]]["handler"]
    await handler(alert_event)

    await asyncio.sleep(0.01)

    audit = engine.get_audit_log("agent-002")
    assert len(audit) == 1
    assert audit[0].status == RollbackStatus.EXECUTED
    assert audit[0].scope == RollbackScope.AGENT


@pytest.mark.asyncio
async def test_auto_rollback_on_safety_violation():
    """Safety violation event should trigger automatic rollback."""
    event_bus = MockEventBus()
    engine = RollbackEngine(event_bus=event_bus)

    async def success_handler(target_id: str, reason: str) -> bool:
        return True

    engine.register_handler(RollbackScope.SESSION, success_handler)
    engine.subscribe_to_events()

    # Simulate safety violation
    violation_event = ExecutionEvent(
        topic=EventTopic.SAFETY_VIOLATION,
        trace_id="test-violation-001",
        payload={
            "violation_type": "token_limit",
            "context": {"agent_id": "agent-003"},
        },
    )

    # Find the safety violation handler
    safety_sub = None
    for sub_id, sub_info in event_bus.subscriptions.items():
        if sub_info["topic"] == EventTopic.SAFETY_VIOLATION:
            safety_sub = sub_info
            break

    assert safety_sub is not None
    await safety_sub["handler"](violation_event)

    await asyncio.sleep(0.01)

    audit = engine.get_audit_log("agent-003")
    assert len(audit) == 1
    assert audit[0].status == RollbackStatus.EXECUTED
    assert audit[0].scope == RollbackScope.SESSION


@pytest.mark.asyncio
async def test_audit_log_tracks_all_actions():
    """All rollback actions should be recorded in the audit log."""
    engine = RollbackEngine()

    async def success_handler(target_id: str, reason: str) -> bool:
        return True

    async def failing_handler(target_id: str, reason: str) -> bool:
        return False

    engine.register_handler(RollbackScope.AGENT, success_handler)
    engine.register_handler(RollbackScope.NODE, failing_handler)

    await engine.trigger_rollback(RollbackScope.AGENT, "agent-001", "reason-1")
    await engine.trigger_rollback(RollbackScope.NODE, "node-001", "reason-2")
    await engine.trigger_rollback(RollbackScope.AGENT, "agent-001", "reason-3")

    all_actions = engine.get_all_actions()
    assert len(all_actions) == 3

    agent_actions = engine.get_audit_log("agent-001")
    assert len(agent_actions) == 2
    assert all(a.status == RollbackStatus.EXECUTED for a in agent_actions)

    node_actions = engine.get_audit_log("node-001")
    assert len(node_actions) == 1
    assert node_actions[0].status == RollbackStatus.FAILED


@pytest.mark.asyncio
async def test_multiple_scopes_isolation():
    """Handlers for different scopes should be isolated."""
    engine = RollbackEngine()

    agent_called = []
    node_called = []

    async def agent_handler(target_id: str, reason: str) -> bool:
        agent_called.append(target_id)
        return True

    async def node_handler(target_id: str, reason: str) -> bool:
        node_called.append(target_id)
        return True

    engine.register_handler(RollbackScope.AGENT, agent_handler)
    engine.register_handler(RollbackScope.NODE, node_handler)

    await engine.trigger_rollback(RollbackScope.AGENT, "agent-001", "test")
    await engine.trigger_rollback(RollbackScope.NODE, "node-001", "test")

    assert agent_called == ["agent-001"]
    assert node_called == ["node-001"]

    agent_audit = engine.get_audit_log("agent-001")
    node_audit = engine.get_audit_log("node-001")
    assert len(agent_audit) == 1
    assert len(node_audit) == 1
    assert agent_audit[0].scope == RollbackScope.AGENT
    assert node_audit[0].scope == RollbackScope.NODE
