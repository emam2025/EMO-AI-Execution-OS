"""Tests for Predictive Maintenance Agent (RC17.2.2).

6 tests covering metric processing, alert generation, event publishing,
activation subscription, and audit trail.

Ref: RC17.2.2 — Predictive Maintenance Agent
"""

import asyncio
import pytest

from core.agents.manufacturing.predictive_maintenance_agent import (
    PredictiveMaintenanceAgent,
)
from core.models.agent import AgentIdentity
from core.models.event import EventTopic
from core.models.manufacturing_advanced import FailureMode


class MockEventBus:
    """Mock event bus for testing."""

    def __init__(self) -> None:
        self.published: list[dict] = []
        self._subscriptions: dict[str, tuple] = {}
        self._next_id = 0

    async def publish(self, topic: EventTopic, event) -> None:
        self.published.append({"topic": topic, "event": event})

    def subscribe(self, topic, handler) -> str:
        sub_id = f"sub-{self._next_id}"
        self._next_id += 1
        self._subscriptions[sub_id] = (topic, handler)
        return sub_id

    def unsubscribe(self, subscription_id: str) -> None:
        self._subscriptions.pop(subscription_id, None)


def _make_agent(event_bus=None) -> PredictiveMaintenanceAgent:
    identity = AgentIdentity(
        id="predictive-agent-01",
        tenant_id="tenant-1",
        org_id=None,
        name="Predictive Maintenance Agent",
        agent_type="predictive_maintenance",
    )
    return PredictiveMaintenanceAgent(identity=identity, event_bus=event_bus)


# --- Tests ---


def test_agent_subscribes_to_events_on_activation():
    event_bus = MockEventBus()
    agent = _make_agent(event_bus=event_bus)
    agent.activate()
    assert agent._status == "active"
    assert agent._subscription_id is not None
    assert agent._subscription_id in event_bus._subscriptions


def test_process_normal_metric_no_alert():
    agent = _make_agent()
    alert = agent.process_metric("pump-01", "temperature", 75.0)
    assert alert is None

    alert = agent.process_metric("pump-01", "vibration", 2.5)
    assert alert is None


def test_process_overheat_metric_generates_alert():
    agent = _make_agent()
    alert = agent.process_metric("pump-01", "temperature", 96.0)
    assert alert is not None
    assert alert.asset_id == "pump-01"
    assert alert.failure_mode == FailureMode.OVERHEAT
    assert alert.confidence_score == 0.85
    assert alert.estimated_time_to_failure_hours == 48.0
    assert "Temperature 96" in alert.recommended_action


def test_process_vibration_metric_generates_alert():
    agent = _make_agent()
    alert = agent.process_metric("motor-02", "vibration", 5.5)
    assert alert is not None
    assert alert.asset_id == "motor-02"
    assert alert.failure_mode == FailureMode.VIBRATION
    assert alert.confidence_score == 0.80
    assert alert.estimated_time_to_failure_hours == 72.0
    assert "Vibration 5.5" in alert.recommended_action


@pytest.mark.asyncio
async def test_alert_is_published_to_event_bus():
    event_bus = MockEventBus()
    agent = _make_agent(event_bus=event_bus)
    agent.process_metric("pump-01", "temperature", 97.0)
    await asyncio.sleep(0.01)
    assert len(event_bus.published) == 1
    published = event_bus.published[0]
    assert published["topic"] == EventTopic.PREDICTIVE_ALERT
    assert published["event"].payload["asset_id"] == "pump-01"
    assert published["event"].payload["failure_mode"] == "overheat"
    assert published["event"].payload["confidence_score"] == 0.85


def test_audit_trail_records_alert_generation():
    agent = _make_agent()
    agent.process_metric("pump-01", "temperature", 98.0)
    records = agent.audit.action_log
    assert len(records) == 1
    assert records[0]["action"] == "predictive_alert.generated"
    assert records[0]["context"]["asset_id"] == "pump-01"
    assert records[0]["context"]["failure_mode"] == "overheat"
    assert records[0]["result"]["status"] == "published"
