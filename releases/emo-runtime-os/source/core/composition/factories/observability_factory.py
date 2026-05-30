"""ObservabilityFactory — Pure wiring for F4 observability stack.

ZERO business logic.  Pure construction + wiring of EventBus, Metrics,
Tracing, and Dashboard components.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("emo_ai.factory.observability")


def build_in_memory_event_bus() -> Any:
    """Return an InMemoryEventBus singleton-compatible instance."""
    from core.runtime.event_bus import InMemoryEventBus

    return InMemoryEventBus()


def build_event_store() -> Any:
    """Return an EventStore instance."""
    from core.runtime.event_store import EventStore

    return EventStore()


def build_trace_collector() -> Any:
    from core.runtime.observability.trace_collector import TraceCollector

    return TraceCollector()


def build_telemetry_aggregator() -> Any:
    from core.runtime.observability.telemetry_aggregator import TelemetryAggregator
    from core.runtime.observability.aggregation_state_machine import (
        AggregationStateMachine,
    )
    from core.runtime.observability.backpressure_sampler import BackpressureSampler

    return TelemetryAggregator(
        state_machine=AggregationStateMachine(),
        sampler=BackpressureSampler(),
    )


def build_dashboard_provider() -> Any:
    from core.runtime.observability.dashboard_data_provider import (
        DashboardDataProvider,
    )

    return DashboardDataProvider()


def build_alert_router() -> Any:
    from core.runtime.observability.alert_router import AlertRouter

    return AlertRouter()
