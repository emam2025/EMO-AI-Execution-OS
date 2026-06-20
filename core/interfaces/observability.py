"""Observability Protocols.

Defines interfaces for metrics collection and distributed tracing.

Ref: P10.1 — Observability Foundation (Metrics & Tracing)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Optional, Protocol

if TYPE_CHECKING:
    from core.models.observability import Span, SpanStatus


class IMetricsCollector(Protocol):
    """Protocol for collecting metrics."""

    def record_metric(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None: ...

    def get_metric(self, name: str) -> Optional[float]: ...


class ITracer(Protocol):
    """Protocol for distributed tracing."""

    def start_span(self, operation: str, trace_id: Optional[str] = None) -> Span: ...

    def end_span(self, span_id: str, status: SpanStatus) -> None: ...

    def get_span(self, span_id: str) -> Optional[Span]: ...
