"""F4 — Distributed Tracing Models.

Pure frozen dataclasses and Enums for distributed tracing.
No business logic, no execution.

Ref: DEVELOPER.md §15.11
Ref: Canon LAW 10, LAW 23
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class SpanStatus(Enum):
    """Trace span completion status."""

    OK = "ok"
    ERROR = "error"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class TraceContext:
    """Propagated trace context across service boundaries."""

    trace_id: str
    span_id: str
    parent_span_id: Optional[str]
    service_name: str
    operation_name: str
    baggage: Dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SpanRecord:
    """Immutable record of a completed span."""

    trace_id: str
    span_id: str
    parent_span_id: Optional[str]
    service_name: str
    operation_name: str
    start_time_ns: int
    end_time_ns: int
    status: SpanStatus
    attributes: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TraceSummary:
    """Aggregated trace statistics for reporting."""

    trace_id: str
    total_spans: int
    total_duration_ns: int
    services_involved: List[str]
    error_count: int
    span_records: List[SpanRecord] = field(default_factory=list)
