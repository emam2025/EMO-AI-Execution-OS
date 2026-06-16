"""F4 — Distributed Tracing: span creation and trace propagation.

Manages trace context propagation, span lifecycle, and trace summaries.
Delegates to D8 services via constructor injection.

Ref: DEVELOPER.md §15.11
Ref: Canon LAW 10, LAW 13, LAW 23
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from core.models.distributed_tracing import (
    SpanRecord,
    SpanStatus,
    TraceContext,
    TraceSummary,
)

logger = logging.getLogger("emo_ai.tracing.distributed")


class DistributedTracer:
    """Creates and manages distributed traces across service boundaries.

    LAW 13: Dependencies injected via constructor.
    No direct execution — manages trace lifecycle only.
    """

    def __init__(self) -> None:
        self._active_spans: Dict[str, Dict[str, Any]] = {}
        self._completed_spans: List[SpanRecord] = []
        self._trace_contexts: Dict[str, TraceContext] = {}

    def start_trace(
        self,
        service_name: str,
        operation_name: str,
        baggage: Optional[Dict[str, str]] = None,
    ) -> TraceContext:
        """Start a new root trace."""
        trace_id = f"trace-{uuid.uuid4().hex[:16]}"
        span_id = f"span-{uuid.uuid4().hex[:12]}"
        context = TraceContext(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=None,
            service_name=service_name,
            operation_name=operation_name,
            baggage=baggage or {},
        )
        self._trace_contexts[trace_id] = context
        self._active_spans[span_id] = {
            "trace_id": trace_id,
            "start_time_ns": time.time_ns(),
            "service_name": service_name,
            "operation_name": operation_name,
        }
        return context

    def start_child_span(
        self,
        parent_context: TraceContext,
        service_name: str,
        operation_name: str,
    ) -> TraceContext:
        """Start a child span under an existing trace."""
        child_span_id = f"span-{uuid.uuid4().hex[:12]}"
        child_context = TraceContext(
            trace_id=parent_context.trace_id,
            span_id=child_span_id,
            parent_span_id=parent_context.span_id,
            service_name=service_name,
            operation_name=operation_name,
            baggage=parent_context.baggage,
        )
        self._active_spans[child_span_id] = {
            "trace_id": parent_context.trace_id,
            "start_time_ns": time.time_ns(),
            "service_name": service_name,
            "operation_name": operation_name,
        }
        return child_context

    def end_span(
        self,
        context: TraceContext,
        status: SpanStatus = SpanStatus.OK,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> SpanRecord:
        """End an active span and record it."""
        span_data = self._active_spans.pop(context.span_id, None)
        if span_data is None:
            raise ValueError(f"No active span found for {context.span_id}")

        end_time_ns = time.time_ns()
        record = SpanRecord(
            trace_id=context.trace_id,
            span_id=context.span_id,
            parent_span_id=context.parent_span_id,
            service_name=context.service_name,
            operation_name=context.operation_name,
            start_time_ns=span_data["start_time_ns"],
            end_time_ns=end_time_ns,
            status=status,
            attributes=attributes or {},
        )
        self._completed_spans.append(record)
        return record

    def get_trace_summary(self, trace_id: str) -> TraceSummary:
        """Aggregate all spans for a trace into a summary."""
        trace_spans = [s for s in self._completed_spans if s.trace_id == trace_id]
        if not trace_spans:
            return TraceSummary(
                trace_id=trace_id,
                total_spans=0,
                total_duration_ns=0,
                services_involved=[],
                error_count=0,
            )

        services = list({s.service_name for s in trace_spans})
        error_count = sum(1 for s in trace_spans if s.status != SpanStatus.OK)
        total_duration = trace_spans[-1].end_time_ns - trace_spans[0].start_time_ns

        return TraceSummary(
            trace_id=trace_id,
            total_spans=len(trace_spans),
            total_duration_ns=total_duration,
            services_involved=services,
            error_count=error_count,
            span_records=trace_spans,
        )

    def inject_context(self, context: TraceContext) -> Dict[str, str]:
        """Inject trace context into headers for propagation."""
        return {
            "X-Trace-Id": context.trace_id,
            "X-Span-Id": context.span_id,
            "X-Parent-Span-Id": context.parent_span_id or "",
            "X-Service-Name": context.service_name,
        }

    def extract_context(self, headers: Dict[str, str]) -> Optional[TraceContext]:
        """Extract trace context from incoming headers."""
        trace_id = headers.get("X-Trace-Id")
        span_id = headers.get("X-Span-Id")
        service_name = headers.get("X-Service-Name")
        if not trace_id or not span_id or not service_name:
            return None

        parent_span_id = headers.get("X-Parent-Span-Id") or None
        return TraceContext(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            service_name=service_name,
            operation_name="extracted",
        )
