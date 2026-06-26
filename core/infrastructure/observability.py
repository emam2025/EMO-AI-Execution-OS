"""Observability Infrastructure — InMemory Implementations.

Metrics collector and tracer for testing and MVP.

Ref: P10.1 — Observability Foundation (Metrics & Tracing)
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from core.interfaces.event_bus import IEventBus

from core.models.observability import Span, SpanStatus


class InMemoryMetricsCollector:
    """In-memory metrics collector with optional event bus integration."""

    def __init__(self, event_bus: Optional[IEventBus] = None,
                 db: Any = None) -> None:
        self._event_bus = event_bus
        self._db = db
        self._metrics: Dict[str, float] = {}
        self._history: List[Dict[str, Any]] = []

    def record_metric(
        self, name: str, value: float, labels: Optional[Dict[str, str]] = None
    ) -> None:
        """Record a metric value."""
        self._metrics[name] = value
        self._history.append({"name": name, "value": value, "labels": labels})

        if self._event_bus is not None:
            import asyncio
            from core.models.event import EventTopic, ExecutionEvent

            event = ExecutionEvent(
                topic=EventTopic.METRIC_RECORDED,
                trace_id=f"metric-{name}",
                payload={"name": name, "value": value, "labels": labels or {}},
            )
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(
                    self._event_bus.publish(EventTopic.METRIC_RECORDED, event)
                )
            except RuntimeError:
                pass

        if self._db is not None:
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(
                    self._db.record_metric(
                        name=name,
                        value=value,
                        labels=json.dumps(labels or {}),
                    )
                )
            except RuntimeError:
                pass

    def get_metric(self, name: str) -> Optional[float]:
        """Get the latest value for a metric."""
        return self._metrics.get(name)

    def get_history(self, name: str) -> List[Dict[str, Any]]:
        """Get all recorded values for a metric."""
        return [h for h in self._history if h["name"] == name]


class InMemoryTracer:
    """In-memory distributed tracer with optional event bus integration."""

    def __init__(self, event_bus: Optional[IEventBus] = None) -> None:
        self._event_bus = event_bus
        self._spans: Dict[str, Span] = {}

    def start_span(self, operation: str, trace_id: Optional[str] = None) -> Span:
        """Start a new span."""
        span = Span(operation=operation, trace_id=trace_id or "")
        self._spans[span.span_id] = span
        return span

    def end_span(self, span_id: str, status: SpanStatus) -> None:
        """End a span and publish completion event."""
        span = self._spans.get(span_id)
        if span is None:
            return

        from datetime import datetime, timezone

        # Create new frozen span with end_time and status
        completed_span = Span(
            span_id=span.span_id,
            trace_id=span.trace_id,
            operation=span.operation,
            start_time=span.start_time,
            end_time=datetime.now(timezone.utc),
            status=status,
            metadata=span.metadata,
        )
        self._spans[span_id] = completed_span

        if self._event_bus is not None:
            import asyncio
            from core.models.event import EventTopic, ExecutionEvent

            event = ExecutionEvent(
                topic=EventTopic.SPAN_COMPLETED,
                trace_id=span.trace_id,
                payload={
                    "span_id": span.span_id,
                    "operation": span.operation,
                    "status": status.value,
                },
            )
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(
                    self._event_bus.publish(EventTopic.SPAN_COMPLETED, event)
                )
            except RuntimeError:
                pass

    def get_span(self, span_id: str) -> Optional[Span]:
        """Get a span by ID."""
        return self._spans.get(span_id)
