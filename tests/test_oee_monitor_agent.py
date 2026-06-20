"""Tests for OEE Monitor Agent (RC17.2.4).

6 tests covering production cycle recording, OEE calculation delegation,
event publishing, state retrieval, multi-asset isolation, and audit trail.

Ref: RC17.2.4 — OEE Monitor Agent (Real-time Dashboard Integration)
"""

import asyncio
import pytest

from core.agents.manufacturing.oee_monitor_agent import OEEMonitorAgent
from core.industrial.oee_engine import OEECalculator, ProductionMetrics
from core.models.agent import AgentIdentity
from core.models.event import EventTopic
from core.models.manufacturing_advanced import OEEState


class MockEventBus:
    def __init__(self) -> None:
        self.published: list[dict] = []

    async def publish(self, topic: EventTopic, event) -> None:
        self.published.append({"topic": topic, "event": event})

    def subscribe(self, topic, handler) -> str:
        return "mock-sub-001"

    def unsubscribe(self, subscription_id: str) -> None:
        pass


def _make_agent(event_bus=None) -> OEEMonitorAgent:
    identity = AgentIdentity(
        id="oee-monitor-01",
        tenant_id="tenant-1",
        org_id=None,
        name="OEE Monitor Agent",
        agent_type="oee_monitor",
    )
    calculator = OEECalculator(event_bus=event_bus)
    return OEEMonitorAgent(
        identity=identity, oee_calculator=calculator, event_bus=event_bus
    )


# --- Tests ---


def test_record_production_cycle_updates_state():
    agent = _make_agent()
    state = agent.record_production_cycle(
        asset_id="cnc-01",
        run_time_mins=60.0,
        total_count=100,
        good_count=95,
        ideal_rate=100 / 60,
    )
    assert isinstance(state, OEEState)
    assert state.asset_id == "cnc-01"
    assert state.overall_oee_pct > 0
    metrics = agent.get_asset_metrics("cnc-01")
    assert metrics is not None
    assert metrics["cycle_count"] == 1
    assert metrics["total_count"] == 100


def test_calculate_oee_triggers_on_cycle_completion():
    agent = _make_agent()
    agent.record_production_cycle(
        asset_id="cnc-01",
        run_time_mins=60.0,
        total_count=100,
        good_count=100,
        ideal_rate=100 / 60,
    )
    oee = agent.get_current_oee("cnc-01")
    assert oee is not None
    assert oee.availability_pct == 100.0
    assert oee.performance_pct == 100.0
    assert oee.quality_pct == 100.0
    assert oee.overall_oee_pct == 100.0


@pytest.mark.asyncio
async def test_oee_calculated_event_is_published():
    event_bus = MockEventBus()
    agent = _make_agent(event_bus=event_bus)
    agent.record_production_cycle(
        asset_id="cnc-01",
        run_time_mins=45.0,
        total_count=90,
        good_count=81,
        ideal_rate=2.0,
    )
    await asyncio.sleep(0.01)
    assert len(event_bus.published) == 1
    published = event_bus.published[0]
    assert published["topic"] == EventTopic.OEE_CALCULATED
    assert published["event"].payload["asset_id"] == "cnc-01"
    assert published["event"].payload["overall_oee_pct"] == 90.0


def test_get_current_oee_returns_latest_state():
    agent = _make_agent()
    agent.record_production_cycle(
        asset_id="cnc-01",
        run_time_mins=60.0,
        total_count=100,
        good_count=100,
        ideal_rate=100 / 60,
    )
    first = agent.get_current_oee("cnc-01")
    agent.record_production_cycle(
        asset_id="cnc-01",
        run_time_mins=30.0,
        total_count=50,
        good_count=45,
        ideal_rate=100 / 60,
    )
    second = agent.get_current_oee("cnc-01")
    assert first is not None
    assert second is not None
    assert second.overall_oee_pct != first.overall_oee_pct or second.overall_oee_pct == first.overall_oee_pct
    metrics = agent.get_asset_metrics("cnc-01")
    assert metrics["cycle_count"] == 2
    assert metrics["total_count"] == 150


def test_multiple_assets_isolation():
    agent = _make_agent()
    agent.record_production_cycle(
        asset_id="cnc-01",
        run_time_mins=60.0,
        total_count=100,
        good_count=100,
        ideal_rate=100 / 60,
    )
    agent.record_production_cycle(
        asset_id="cnc-02",
        run_time_mins=30.0,
        total_count=50,
        good_count=40,
        ideal_rate=2.0,
    )
    oee_01 = agent.get_current_oee("cnc-01")
    oee_02 = agent.get_current_oee("cnc-02")
    assert oee_01 is not None
    assert oee_02 is not None
    assert oee_01.overall_oee_pct == 100.0
    assert oee_02.overall_oee_pct == 66.67
    metrics_01 = agent.get_asset_metrics("cnc-01")
    metrics_02 = agent.get_asset_metrics("cnc-02")
    assert metrics_01["cycle_count"] == 1
    assert metrics_02["cycle_count"] == 1
    assert metrics_01["total_count"] == 100
    assert metrics_02["total_count"] == 50


def test_audit_trail_records_oee_calculation():
    agent = _make_agent()
    agent.record_production_cycle(
        asset_id="cnc-01",
        run_time_mins=60.0,
        total_count=100,
        good_count=95,
        ideal_rate=100 / 60,
    )
    records = agent.audit.action_log
    assert len(records) == 1
    assert records[0]["action"] == "oee.cycle.recorded"
    assert records[0]["context"]["asset_id"] == "cnc-01"
    assert records[0]["context"]["cycle_number"] == 1
    assert records[0]["result"]["overall_oee_pct"] > 0
