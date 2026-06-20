"""OEE Metrics Engine — Pure Calculation Layer.

Calculates Overall Equipment Effectiveness (OEE) from production metrics.
Publishes OEE_CALCULATED events via IEventBus.

OEE = Availability × Performance × Quality
Availability = Run Time / Planned Production Time
Performance = (Total Count / Run Time) / Ideal Run Rate
Quality = Good Count / Total Count

Ref: RC17.2.1 — OEE Metrics Engine & Predictive Domain Models
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, Optional

from core.models.manufacturing_advanced import OEEState

if TYPE_CHECKING:
    from core.interfaces.event_bus import IEventBus

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProductionMetrics:
    """Raw production metrics for OEE calculation."""

    planned_production_time_minutes: float = 0.0
    run_time_minutes: float = 0.0
    total_count: int = 0
    good_count: int = 0
    ideal_run_rate_per_minute: float = 1.0


class OEECalculator:
    """Pure OEE calculation engine with event publishing.

    Deterministic: same inputs always produce same outputs.
    Safe: handles zero division gracefully.
    """

    def __init__(self, event_bus: Optional[IEventBus] = None) -> None:
        self._event_bus = event_bus

    def calculate_oee(
        self, asset_id: str, metrics: ProductionMetrics
    ) -> OEEState:
        """Calculate OEE from production metrics.

        Returns OEEState with availability, performance, quality, and overall OEE.
        Publishes OEE_CALCULATED event if event_bus is available.
        """
        availability = self._calculate_availability(metrics)
        performance = self._calculate_performance(metrics)
        quality = self._calculate_quality(metrics)
        overall = availability * performance * quality

        state = OEEState(
            asset_id=asset_id,
            availability_pct=round(availability * 100, 2),
            performance_pct=round(performance * 100, 2),
            quality_pct=round(quality * 100, 2),
            overall_oee_pct=round(overall * 100, 2),
        )

        self._publish_oee_event(state)
        return state

    def _calculate_availability(self, metrics: ProductionMetrics) -> float:
        """Availability = Run Time / Planned Production Time."""
        if metrics.planned_production_time_minutes <= 0:
            logger.warning(
                "OEE: planned_production_time is zero, returning 0.0 availability"
            )
            return 0.0
        return metrics.run_time_minutes / metrics.planned_production_time_minutes

    def _calculate_performance(self, metrics: ProductionMetrics) -> float:
        """Performance = (Total Count / Run Time) / Ideal Run Rate."""
        if metrics.run_time_minutes <= 0:
            logger.warning("OEE: run_time is zero, returning 0.0 performance")
            return 0.0
        if metrics.ideal_run_rate_per_minute <= 0:
            logger.warning(
                "OEE: ideal_run_rate is zero, returning 0.0 performance"
            )
            return 0.0
        actual_rate = metrics.total_count / metrics.run_time_minutes
        return actual_rate / metrics.ideal_run_rate_per_minute

    def _calculate_quality(self, metrics: ProductionMetrics) -> float:
        """Quality = Good Count / Total Count."""
        if metrics.total_count <= 0:
            logger.warning("OEE: total_count is zero, returning 0.0 quality")
            return 0.0
        return metrics.good_count / metrics.total_count

    def _publish_oee_event(self, state: OEEState) -> None:
        """Publish OEE_CALCULATED event to the event bus."""
        if self._event_bus is None:
            return
        from core.models.event import EventTopic, ExecutionEvent

        event = ExecutionEvent(
            topic=EventTopic.OEE_CALCULATED,
            trace_id=f"oee-{state.asset_id}",
            payload={
                "asset_id": state.asset_id,
                "availability_pct": state.availability_pct,
                "performance_pct": state.performance_pct,
                "quality_pct": state.quality_pct,
                "overall_oee_pct": state.overall_oee_pct,
            },
        )
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(
                self._event_bus.publish(EventTopic.OEE_CALCULATED, event)
            )
        except RuntimeError:
            pass
