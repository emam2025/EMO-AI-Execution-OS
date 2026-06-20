"""Tests for Guardrails Engine.

6 independent tests covering behavioral drift, performance regression, and event publishing.

Ref: P8.2 — Guardrails Engine
"""

import asyncio

import pytest

from core.governance.guardrails_engine import GuardrailsEngine
from core.models.guardrails import DriftType, GuardrailAlert


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
async def test_record_and_evaluate_baseline_within_bounds():
    """Metrics within baseline bounds should produce no alert."""
    engine = GuardrailsEngine()
    engine.record_baseline("agent-001", {"response_time": 100.0, "failure_rate": 0.05})

    # response_time at 100 is equal to baseline (no regression)
    result = engine.evaluate_performance("agent-001", {"response_time": 100.0, "failure_rate": 0.05})

    assert result is None


@pytest.mark.asyncio
async def test_detect_performance_regression():
    """Metrics significantly below baseline should trigger regression alert."""
    event_bus = MockEventBus()
    engine = GuardrailsEngine(event_bus=event_bus)
    engine.record_baseline("agent-001", {"response_time": 100.0, "failure_rate": 0.05})

    # response_time degrades from 100 to 150 (50% regression)
    result = engine.evaluate_performance("agent-001", {"response_time": 150.0, "failure_rate": 0.05})

    assert result is not None
    assert result.drift_type == DriftType.PERFORMANCE_REGRESSION
    assert result.agent_id == "agent-001"
    assert result.details["metric"] == "response_time"
    assert result.details["regression_pct"] == 50.0

    await asyncio.sleep(0.01)
    assert len(event_bus.published) == 1
    assert event_bus.published[0]["topic"].value == "guardrail_alert"


@pytest.mark.asyncio
async def test_detect_behavioral_drift():
    """Actions outside allowed set should trigger behavioral drift alert."""
    event_bus = MockEventBus()
    engine = GuardrailsEngine(event_bus=event_bus)
    engine.set_allowed_actions("agent-002", ["read", "list", "get"])

    # 5 out of 7 actions are disallowed (71% drift)
    recent_actions = [
        {"type": "read"},
        {"type": "write"},
        {"type": "delete"},
        {"type": "read"},
        {"type": "write"},
        {"type": "delete"},
        {"type": "write"},
    ]

    result = engine.evaluate_behavior("agent-002", recent_actions)

    assert result is not None
    assert result.drift_type == DriftType.BEHAVIORAL_DRIFT
    assert result.agent_id == "agent-002"
    assert result.details["disallowed_count"] == 5
    assert result.details["disallowed_ratio"] > 50.0

    await asyncio.sleep(0.01)
    assert len(event_bus.published) == 1
    assert event_bus.published[0]["topic"].value == "guardrail_alert"


@pytest.mark.asyncio
async def test_no_alert_on_normal_behavior():
    """Normal behavior within thresholds should produce no alert."""
    engine = GuardrailsEngine()
    engine.set_allowed_actions("agent-003", ["read", "list", "get", "write"])

    recent_actions = [
        {"type": "read"},
        {"type": "read"},
        {"type": "list"},
        {"type": "write"},
        {"type": "read"},
    ]

    result = engine.evaluate_behavior("agent-003", recent_actions)

    assert result is None


@pytest.mark.asyncio
async def test_alert_publishes_to_event_bus():
    """Every alert must be published to event bus with correct payload."""
    event_bus = MockEventBus()
    engine = GuardrailsEngine(event_bus=event_bus)
    engine.record_baseline("agent-004", {"latency": 100.0})

    # latency degrades from 100 to 150 (50% regression)
    engine.evaluate_performance("agent-004", {"latency": 150.0})

    await asyncio.sleep(0.01)
    assert len(event_bus.published) == 1

    payload = event_bus.published[0]["event"].payload
    assert "alert_id" in payload
    assert "agent_id" in payload
    assert "drift_type" in payload
    assert "severity" in payload
    assert "details" in payload
    assert "action_taken" in payload
    assert payload["agent_id"] == "agent-004"
    assert payload["drift_type"] == "performance_regression"


@pytest.mark.asyncio
async def test_multiple_agents_isolation():
    """Baselines and alerts must be isolated per agent."""
    engine = GuardrailsEngine()
    engine.record_baseline("agent-A", {"latency": 50.0})
    engine.record_baseline("agent-B", {"latency": 200.0})

    # agent-A at 50 is equal to baseline (no regression)
    result_a = engine.evaluate_performance("agent-A", {"latency": 50.0})
    assert result_a is None

    # agent-B at 200 is equal to baseline (no regression)
    result_b = engine.evaluate_performance("agent-B", {"latency": 200.0})
    assert result_b is None

    # agent-A at 80 is 60% regression from 50 — should alert
    result_a_bad = engine.evaluate_performance("agent-A", {"latency": 80.0})
    assert result_a_bad is not None
    assert result_a_bad.agent_id == "agent-A"
    assert result_a_bad.drift_type == DriftType.PERFORMANCE_REGRESSION

    # agent-B still fine
    result_b_still = engine.evaluate_performance("agent-B", {"latency": 220.0})
    assert result_b_still is None
