"""Tests for Safety Gate.

6 independent tests covering Default Deny logic and event publishing.

Ref: P8.1 — Safety Limits & Policy Gate
"""

import asyncio

import pytest

from core.governance.safety_gate import SafetyGate
from core.models.safety import SafetyDecision, SafetyLimitType, SafetyLimits


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
async def test_evaluate_within_limits_allowed():
    """Context within all limits should be allowed."""
    gate = SafetyGate()
    context = {"tokens": 50_000, "estimated_cost": 5.0, "estimated_runtime": 1800.0}
    limits = SafetyLimits(max_tokens=100_000, max_cost_usd=10.0, max_runtime_seconds=3600.0)

    decision = gate.evaluate(context, limits)

    assert decision.allowed is True
    assert decision.reason == "Within all safety limits"
    assert decision.violation_type is None


@pytest.mark.asyncio
async def test_evaluate_token_limit_exceeded_denied_and_evented():
    """Token limit exceeded should deny and publish event."""
    event_bus = MockEventBus()
    gate = SafetyGate(event_bus=event_bus)
    context = {"tokens": 150_000, "estimated_cost": 5.0, "estimated_runtime": 1800.0}
    limits = SafetyLimits(max_tokens=100_000, max_cost_usd=10.0, max_runtime_seconds=3600.0)

    decision = gate.evaluate(context, limits)

    assert decision.allowed is False
    assert decision.violation_type == SafetyLimitType.TOKEN_LIMIT
    assert "Token limit exceeded" in decision.reason

    await asyncio.sleep(0.01)
    assert len(event_bus.published) == 1
    assert event_bus.published[0]["topic"].value == "safety_violation"
    assert event_bus.published[0]["event"].payload["violation_type"] == "token_limit"


@pytest.mark.asyncio
async def test_evaluate_cost_limit_exceeded_denied_and_evented():
    """Cost limit exceeded should deny and publish event."""
    event_bus = MockEventBus()
    gate = SafetyGate(event_bus=event_bus)
    context = {"tokens": 50_000, "estimated_cost": 15.0, "estimated_runtime": 1800.0}
    limits = SafetyLimits(max_tokens=100_000, max_cost_usd=10.0, max_runtime_seconds=3600.0)

    decision = gate.evaluate(context, limits)

    assert decision.allowed is False
    assert decision.violation_type == SafetyLimitType.COST_LIMIT
    assert "Cost limit exceeded" in decision.reason

    await asyncio.sleep(0.01)
    assert len(event_bus.published) == 1
    assert event_bus.published[0]["event"].payload["violation_type"] == "cost_limit"


@pytest.mark.asyncio
async def test_evaluate_runtime_limit_exceeded_denied_and_evented():
    """Runtime limit exceeded should deny and publish event."""
    event_bus = MockEventBus()
    gate = SafetyGate(event_bus=event_bus)
    context = {"tokens": 50_000, "estimated_cost": 5.0, "estimated_runtime": 7200.0}
    limits = SafetyLimits(max_tokens=100_000, max_cost_usd=10.0, max_runtime_seconds=3600.0)

    decision = gate.evaluate(context, limits)

    assert decision.allowed is False
    assert decision.violation_type == SafetyLimitType.RUNTIME_LIMIT
    assert "Runtime limit exceeded" in decision.reason

    await asyncio.sleep(0.01)
    assert len(event_bus.published) == 1
    assert event_bus.published[0]["event"].payload["violation_type"] == "runtime_limit"


@pytest.mark.asyncio
async def test_no_hidden_fallback_to_permissive():
    """Deny decisions must be final — no silent override to allow."""
    gate = SafetyGate()
    context = {"tokens": 200_000, "estimated_cost": 50.0, "estimated_runtime": 10_000.0}
    limits = SafetyLimits(max_tokens=100_000, max_cost_usd=10.0, max_runtime_seconds=3600.0)

    decision = gate.evaluate(context, limits)

    # First violation (tokens) is reported — deny is final
    assert decision.allowed is False
    assert decision.violation_type == SafetyLimitType.TOKEN_LIMIT

    # Evaluate again with same violations — still denied
    decision2 = gate.evaluate(context, limits)
    assert decision2.allowed is False


@pytest.mark.asyncio
async def test_event_payload_contains_violation_details():
    """Published event must contain full violation details."""
    event_bus = MockEventBus()
    gate = SafetyGate(event_bus=event_bus)
    context = {"tokens": 150_000, "estimated_cost": 5.0, "estimated_runtime": 1800.0}
    limits = SafetyLimits(max_tokens=100_000, max_cost_usd=10.0, max_runtime_seconds=3600.0)

    gate.evaluate(context, limits)

    await asyncio.sleep(0.01)
    assert len(event_bus.published) == 1

    payload = event_bus.published[0]["event"].payload
    assert "violation_type" in payload
    assert "reason" in payload
    assert "context" in payload
    assert "limits" in payload
    assert payload["context"]["tokens"] == 150_000
    assert payload["limits"]["max_tokens"] == 100_000
    assert payload["limits"]["max_cost_usd"] == 10.0
    assert payload["limits"]["max_runtime_seconds"] == 3600.0
