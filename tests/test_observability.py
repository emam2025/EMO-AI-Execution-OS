"""Tests for Observability Infrastructure.

6 independent tests covering metrics collection, tracing, and event publishing.

Ref: P10.1 — Observability Foundation (Metrics & Tracing)
"""

import asyncio

import pytest

from core.infrastructure.observability import InMemoryMetricsCollector, InMemoryTracer
from core.models.observability import SpanStatus


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
async def test_record_metric_stores_value():
    """Recorded metric should be retrievable by name."""
    collector = InMemoryMetricsCollector()
    collector.record_metric("request_count", 42.0)

    value = collector.get_metric("request_count")
    assert value == 42.0


@pytest.mark.asyncio
async def test_record_metric_publishes_event():
    """Recording a metric should publish METRIC_RECORDED event."""
    event_bus = MockEventBus()
    collector = InMemoryMetricsCollector(event_bus=event_bus)

    collector.record_metric("latency_ms", 150.0, labels={"endpoint": "/api"})

    await asyncio.sleep(0.01)
    assert len(event_bus.published) == 1
    assert event_bus.published[0]["topic"].value == "metric_recorded"
    assert event_bus.published[0]["event"].payload["name"] == "latency_ms"
    assert event_bus.published[0]["event"].payload["value"] == 150.0
    assert event_bus.published[0]["event"].payload["labels"]["endpoint"] == "/api"


@pytest.mark.asyncio
async def test_metric_history_tracking():
    """Multiple recordings of the same metric should be tracked in history."""
    collector = InMemoryMetricsCollector()
    collector.record_metric("cpu_usage", 45.0)
    collector.record_metric("cpu_usage", 60.0)
    collector.record_metric("cpu_usage", 55.0)

    history = collector.get_history("cpu_usage")
    assert len(history) == 3
    assert history[0]["value"] == 45.0
    assert history[2]["value"] == 55.0


@pytest.mark.asyncio
async def test_start_and_end_span():
    """Spans should be created and completed with correct status."""
    tracer = InMemoryTracer()
    span = tracer.start_span("http_request", trace_id="trace-001")

    assert span.span_id is not None
    assert span.operation == "http_request"
    assert span.trace_id == "trace-001"
    assert span.end_time is None

    tracer.end_span(span.span_id, SpanStatus.OK)

    completed = tracer.get_span(span.span_id)
    assert completed is not None
    assert completed.status == SpanStatus.OK
    assert completed.end_time is not None


@pytest.mark.asyncio
async def test_end_span_publishes_event():
    """Ending a span should publish SPAN_COMPLETED event."""
    event_bus = MockEventBus()
    tracer = InMemoryTracer(event_bus=event_bus)

    span = tracer.start_span("db_query", trace_id="trace-002")
    tracer.end_span(span.span_id, SpanStatus.OK)

    await asyncio.sleep(0.01)
    assert len(event_bus.published) == 1
    assert event_bus.published[0]["topic"].value == "span_completed"
    assert event_bus.published[0]["event"].payload["span_id"] == span.span_id
    assert event_bus.published[0]["event"].payload["operation"] == "db_query"
    assert event_bus.published[0]["event"].payload["status"] == "ok"


@pytest.mark.asyncio
async def test_multiple_traces_isolation():
    """Spans from different traces should be isolated."""
    tracer = InMemoryTracer()

    span_a = tracer.start_span("operation_a", trace_id="trace-A")
    span_b = tracer.start_span("operation_b", trace_id="trace-B")

    tracer.end_span(span_a.span_id, SpanStatus.OK)
    tracer.end_span(span_b.span_id, SpanStatus.ERROR)

    completed_a = tracer.get_span(span_a.span_id)
    completed_b = tracer.get_span(span_b.span_id)

    assert completed_a.trace_id == "trace-A"
    assert completed_a.status == SpanStatus.OK
    assert completed_b.trace_id == "trace-B"
    assert completed_b.status == SpanStatus.ERROR
