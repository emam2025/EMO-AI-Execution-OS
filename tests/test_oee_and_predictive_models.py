"""Tests for OEE Metrics Engine & Predictive Domain Models (RC17.2.1).

6 tests covering OEE calculation, predictive alerts, event publishing,
frozen models, and zero-division safety.

Ref: RC17.2.1 — OEE Metrics Engine & Predictive Domain Models
"""

import asyncio

import pytest

from core.industrial.oee_engine import OEECalculator, ProductionMetrics
from core.models.event import EventTopic
from core.models.manufacturing_advanced import (
    FailureMode,
    OEEState,
    PredictiveAlert,
)


# ── Mock Event Bus ────────────────────────────────────────────────────────────


class MockEventBus:
    def __init__(self) -> None:
        self.published: list[dict] = []

    async def publish(self, topic: EventTopic, event) -> None:
        self.published.append({"topic": topic, "event": event})

    def subscribe(self, topic, handler) -> str:
        return "mock-sub-001"

    def unsubscribe(self, subscription_id: str) -> None:
        pass


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_oee_calculation_perfect_conditions():
    """Perfect conditions: 100% availability, 100% performance, 100% quality → OEE ≈ 100%."""
    calc = OEECalculator()
    metrics = ProductionMetrics(
        planned_production_time_minutes=60.0,
        run_time_minutes=60.0,
        total_count=100,
        good_count=100,
        ideal_run_rate_per_minute=100 / 60,  # 100 parts in 60 min
    )
    state = calc.calculate_oee("asset-1", metrics)
    assert state.availability_pct == 100.0
    assert state.performance_pct == 100.0
    assert state.quality_pct == 100.0
    assert state.overall_oee_pct == 100.0
    assert state.asset_id == "asset-1"


def test_oee_calculation_with_downtime_and_defects():
    """With downtime and defects: verify mathematical correctness."""
    calc = OEECalculator()
    metrics = ProductionMetrics(
        planned_production_time_minutes=60.0,
        run_time_minutes=45.0,  # 75% availability
        total_count=90,  # (90/45) = 2 parts/min
        good_count=81,  # 90% quality
        ideal_run_rate_per_minute=2.0,  # Ideal = 2 parts/min → 100% performance
    )
    state = calc.calculate_oee("asset-2", metrics)
    assert state.availability_pct == 75.0
    assert state.performance_pct == 100.0
    assert state.quality_pct == 90.0
    expected_oee = 75.0 * 100.0 * 90.0 / 10000  # = 67.5
    assert state.overall_oee_pct == round(expected_oee, 2)


def test_predictive_alert_generation():
    """Create a PredictiveAlert with valid data."""
    alert = PredictiveAlert(
        asset_id="pump-01",
        failure_mode=FailureMode.OVERHEAT,
        confidence_score=0.87,
        estimated_time_to_failure_hours=48.0,
        recommended_action="Schedule bearing replacement within 48 hours",
    )
    assert alert.asset_id == "pump-01"
    assert alert.failure_mode == FailureMode.OVERHEAT
    assert alert.confidence_score == 0.87
    assert alert.estimated_time_to_failure_hours == 48.0
    assert alert.alert_id != ""


@pytest.mark.asyncio
async def test_oee_engine_publishes_event():
    """calculate_oee must publish OEE_CALCULATED event."""
    event_bus = MockEventBus()
    calc = OEECalculator(event_bus=event_bus)
    metrics = ProductionMetrics(
        planned_production_time_minutes=60.0,
        run_time_minutes=60.0,
        total_count=100,
        good_count=100,
        ideal_run_rate_per_minute=100 / 60,
    )
    calc.calculate_oee("asset-3", metrics)
    await asyncio.sleep(0.01)

    assert len(event_bus.published) == 1
    pub = event_bus.published[0]
    assert pub["topic"] == EventTopic.OEE_CALCULATED
    assert pub["event"].payload["asset_id"] == "asset-3"
    assert pub["event"].payload["overall_oee_pct"] == 100.0
    assert pub["event"].trace_id.startswith("oee-")


def test_models_are_frozen():
    """OEEState and PredictiveAlert must be immutable."""
    state = OEEState(asset_id="x", availability_pct=95.0)
    with pytest.raises(AttributeError):
        state.availability_pct = 50.0

    alert = PredictiveAlert(asset_id="y", confidence_score=0.9)
    with pytest.raises(AttributeError):
        alert.confidence_score = 0.1


def test_oee_handles_zero_division_safely():
    """Zero values in metrics must not crash the calculator."""
    calc = OEECalculator()

    # Zero planned time
    metrics_zero_planned = ProductionMetrics(
        planned_production_time_minutes=0.0,
        run_time_minutes=0.0,
        total_count=0,
        good_count=0,
    )
    state = calc.calculate_oee("asset-zero", metrics_zero_planned)
    assert state.availability_pct == 0.0
    assert state.performance_pct == 0.0
    assert state.quality_pct == 0.0
    assert state.overall_oee_pct == 0.0

    # Zero run time
    metrics_zero_run = ProductionMetrics(
        planned_production_time_minutes=60.0,
        run_time_minutes=0.0,
        total_count=0,
        good_count=0,
    )
    state = calc.calculate_oee("asset-zero-run", metrics_zero_run)
    assert state.performance_pct == 0.0

    # Zero total count
    metrics_zero_count = ProductionMetrics(
        planned_production_time_minutes=60.0,
        run_time_minutes=60.0,
        total_count=0,
        good_count=0,
    )
    state = calc.calculate_oee("asset-zero-count", metrics_zero_count)
    assert state.quality_pct == 0.0
