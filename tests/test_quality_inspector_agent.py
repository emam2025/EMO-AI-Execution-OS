"""Tests for Quality Closed-Loop Agent (RC17.2.3).

6 tests covering defect tracking, slowdown triggers, approval gate,
event publishing, and audit trail.

Ref: RC17.2.3 — Quality Closed-Loop Agent
"""

import asyncio
import pytest

from core.agents.manufacturing.quality_inspector_agent import (
    QualityInspectorClosedLoop,
)
from core.models.agent import AgentIdentity
from core.models.event import EventTopic


class MockEventBus:
    def __init__(self) -> None:
        self.published: list[dict] = []

    async def publish(self, topic: EventTopic, event) -> None:
        self.published.append({"topic": topic, "event": event})

    def subscribe(self, topic, handler) -> str:
        return "mock-sub-001"

    def unsubscribe(self, subscription_id: str) -> None:
        pass


class MockApprovalGate:
    def __init__(self, allow: bool = True) -> None:
        self._allow = allow
        self.calls: list[dict] = []

    def check_autonomy(self, **kwargs) -> dict:
        self.calls.append(kwargs)
        return {"allowed": self._allow, "reason": "approved" if self._allow else "denied"}


def _make_agent(event_bus=None, approval_gate=None) -> QualityInspectorClosedLoop:
    identity = AgentIdentity(
        id="quality-cl-agent-01",
        tenant_id="tenant-1",
        org_id=None,
        name="Quality Inspector Closed Loop Agent",
        agent_type="quality_inspector_closed_loop",
    )
    return QualityInspectorClosedLoop(
        identity=identity, event_bus=event_bus, approval_gate=approval_gate
    )


# --- Tests ---


def test_record_normal_check_no_action():
    agent = _make_agent()
    result = agent.record_quality_check("pump-01", is_defective=False)
    assert result["status"] == "recorded"
    assert result["action_taken"] == "none"
    assert agent.get_defect_count("pump-01") == 0


def test_record_defective_check_increments_counter():
    agent = _make_agent()
    result = agent.record_quality_check("pump-01", is_defective=True, defect_type="scratch")
    assert result["status"] == "recorded"
    assert result["defect_count"] == 1
    assert agent.get_defect_count("pump-01") == 1

    agent.record_quality_check("pump-01", is_defective=True, defect_type="dent")
    assert agent.get_defect_count("pump-01") == 2


def test_repeated_defects_trigger_slowdown_request():
    agent = _make_agent()
    for _ in range(3):
        result = agent.record_quality_check("pump-01", is_defective=True, defect_type="crack")
    assert result["status"] == "requested"
    assert result["action"] == "slowdown"
    assert result["defect_count"] == 3


def test_slowdown_request_requires_approval():
    gate = MockApprovalGate(allow=False)
    agent = _make_agent(approval_gate=gate)
    for _ in range(3):
        result = agent.record_quality_check("pump-01", is_defective=True, defect_type="crack")
    assert result["status"] == "denied"
    assert result["reason"] == "denied"
    assert len(gate.calls) == 1
    assert gate.calls[0]["action"] == "request_line_slowdown"


@pytest.mark.asyncio
async def test_alert_is_published_to_event_bus():
    event_bus = MockEventBus()
    agent = _make_agent(event_bus=event_bus)
    for _ in range(3):
        agent.record_quality_check("pump-01", is_defective=True, defect_type="crack")
    await asyncio.sleep(0.01)
    assert len(event_bus.published) == 1
    published = event_bus.published[0]
    assert published["topic"] == EventTopic.QUALITY_LINE_SLOWDOWN_REQUESTED
    assert published["event"].payload["asset_id"] == "pump-01"
    assert published["event"].payload["defect_count"] == 3
    assert published["event"].payload["action"] == "slowdown"


def test_audit_trail_records_quality_actions():
    agent = _make_agent()
    agent.record_quality_check("pump-01", is_defective=False)
    agent.record_quality_check("pump-01", is_defective=True, defect_type="scratch")
    records = agent.audit.action_log
    assert len(records) == 2
    assert records[0]["action"] == "quality_check.recorded"
    assert records[0]["context"]["is_defective"] is False
    assert records[1]["action"] == "quality_check.recorded"
    assert records[1]["context"]["is_defective"] is True
    assert records[1]["context"]["defect_type"] == "scratch"
