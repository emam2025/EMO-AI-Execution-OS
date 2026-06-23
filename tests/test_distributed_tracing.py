"""F4 — Distributed Tracing Tests.

Verifies trace creation, span lifecycle, context propagation, and summaries.

Ref: DEVELOPER.md §15.11
Ref: Canon LAW 10, LAW 13, LAW 23
"""

from unittest.mock import MagicMock

from core.models.distributed_tracing import SpanRecord, SpanStatus, TraceContext, TraceSummary
from core.runtime.observability.distributed_tracer import DistributedTracer


def _build_tracer() -> DistributedTracer:
    return DistributedTracer()


class TestDistributedTracing:
    def test_start_trace_returns_valid_context(self) -> None:
        tracer = _build_tracer()
        ctx = tracer.start_trace("service-a", "process-request")
        assert ctx.trace_id.startswith("trace-")
        assert ctx.span_id.startswith("span-")
        assert ctx.parent_span_id is None
        assert ctx.service_name == "service-a"

    def test_end_span_records_valid_span_record(self) -> None:
        tracer = _build_tracer()
        ctx = tracer.start_trace("service-a", "process-request")
        record = tracer.end_span(ctx, status=SpanStatus.OK)
        assert record.trace_id == ctx.trace_id
        assert record.status == SpanStatus.OK
        assert record.end_time_ns > record.start_time_ns

    def test_child_span_links_to_parent(self) -> None:
        tracer = _build_tracer()
        parent = tracer.start_trace("service-a", "parent-op")
        child = tracer.start_child_span(parent, "service-b", "child-op")
        assert child.trace_id == parent.trace_id
        assert child.parent_span_id == parent.span_id
        assert child.span_id != parent.span_id

    def test_trace_summary_aggregates_spans(self) -> None:
        tracer = _build_tracer()
        parent = tracer.start_trace("service-a", "parent-op")
        child = tracer.start_child_span(parent, "service-b", "child-op")
        tracer.end_span(parent, status=SpanStatus.OK)
        tracer.end_span(child, status=SpanStatus.ERROR)
        summary = tracer.get_trace_summary(parent.trace_id)
        assert summary.total_spans == 2
        assert summary.error_count == 1
        assert "service-a" in summary.services_involved
        assert "service-b" in summary.services_involved

    def test_inject_extract_context_roundtrip(self) -> None:
        tracer = _build_tracer()
        ctx = tracer.start_trace("service-a", "op-1")
        headers = tracer.inject_context(ctx)
        restored = tracer.extract_context(headers)
        assert restored is not None
        assert restored.trace_id == ctx.trace_id
        assert restored.span_id == ctx.span_id

    def test_end_span_raises_on_missing_span(self) -> None:
        tracer = _build_tracer()
        fake_ctx = TraceContext(
            trace_id="trace-missing",
            span_id="span-missing",
            parent_span_id=None,
            service_name="service-x",
            operation_name="op-x",
        )
        import pytest

        with pytest.raises(ValueError, match="No active span found"):
            tracer.end_span(fake_ctx)
