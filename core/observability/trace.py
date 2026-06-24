"""F4 — ExecutionTrace: distributed tracing for DAG executions.

Provides a span tree that tracks every step of an execution
through the system: submission → scheduling → dispatch → execution → result.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# SpanStatus is canonical from runtime models
from core.runtime.models.observability_models import SpanStatus  # noqa: F401

logger = logging.getLogger("emo_ai.observability.trace")


@dataclass
class Span:
    span_id: str
    parent_span_id: Optional[str]
    execution_id: str
    name: str
    service: str
    status: SpanStatus = SpanStatus.PENDING
    started_at: float = 0.0
    ended_at: float = 0.0
    duration_ms: float = 0.0
    error: Optional[str] = None
    tags: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_complete(self) -> bool:
        return self.status in (SpanStatus.OK, SpanStatus.ERROR, SpanStatus.CANCELLED)

    @property
    def is_error(self) -> bool:
        return self.status == SpanStatus.ERROR


@dataclass
class ExecutionTrace:
    execution_id: str
    dag_id: str = ""
    strategy: str = "balanced"
    root_span_id: str = ""
    spans: Dict[str, Span] = field(default_factory=dict)
    started_at: float = 0.0
    ended_at: float = 0.0
    total_duration_ms: float = 0.0
    status: SpanStatus = SpanStatus.PENDING
    error: Optional[str] = None

    def start_span(self, name: str, service: str,
                   parent_span_id: Optional[str] = None,
                   tags: Optional[Dict[str, str]] = None) -> Span:
        span_id = str(uuid.uuid4())
        span = Span(
            span_id=span_id,
            parent_span_id=parent_span_id,
            execution_id=self.execution_id,
            name=name,
            service=service,
            started_at=time.time(),
            tags=tags or {},
        )
        self.spans[span_id] = span
        if parent_span_id is None:
            self.root_span_id = span_id
        return span

    def end_span(self, span_id: str, status: SpanStatus = SpanStatus.OK,
                 error: Optional[str] = None,
                 metadata: Optional[Dict[str, Any]] = None) -> None:
        span = self.spans.get(span_id)
        if not span:
            return
        span.ended_at = time.time()
        span.duration_ms = (span.ended_at - span.started_at) * 1000
        span.status = status
        span.error = error
        if metadata:
            span.metadata.update(metadata)

    def get_span(self, span_id: str) -> Optional[Span]:
        return self.spans.get(span_id)

    def spans_by_service(self, service: str) -> List[Span]:
        return [s for s in self.spans.values() if s.service == service]

    def error_spans(self) -> List[Span]:
        return [s for s in self.spans.values() if s.is_error]

    def span_tree(self) -> List[Dict[str, Any]]:
        """Build a tree representation of spans."""
        children: Dict[Optional[str], List[Span]] = {}
        for s in self.spans.values():
            children.setdefault(s.parent_span_id, []).append(s)
        result: List[Dict[str, Any]] = []

        def build(parent_id: Optional[str], depth: int = 0) -> None:
            for s in children.get(parent_id, []):
                node = {
                    "span_id": s.span_id,
                    "name": s.name,
                    "service": s.service,
                    "status": s.status.value,
                    "duration_ms": round(s.duration_ms, 2),
                    "depth": depth,
                    "children": [],
                }
                result.append(node)
                build(s.span_id, depth + 1)

        build(None)
        return result

    def to_dict(self) -> Dict[str, Any]:
        self.total_duration_ms = (self.ended_at - self.started_at) * 1000 if self.ended_at > 0 else 0.0
        return {
            "execution_id": self.execution_id,
            "dag_id": self.dag_id,
            "strategy": self.strategy,
            "status": self.status.value,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "total_duration_ms": round(self.total_duration_ms, 2),
            "error": self.error,
            "spans": len(self.spans),
            "span_tree": self.span_tree(),
        }


class TraceStore:
    """In-memory store for execution traces.

    Limits: max_traces to prevent unbounded memory growth.
    """

    def __init__(self, max_traces: int = 1000):
        self._traces: Dict[str, ExecutionTrace] = {}
        self._max_traces = max_traces

    def create_trace(self, execution_id: str, dag_id: str = "",
                     strategy: str = "balanced") -> ExecutionTrace:
        self._evict_if_needed()
        trace = ExecutionTrace(
            execution_id=execution_id,
            dag_id=dag_id,
            strategy=strategy,
            started_at=time.time(),
        )
        self._traces[execution_id] = trace
        return trace

    def get_trace(self, execution_id: str) -> Optional[ExecutionTrace]:
        return self._traces.get(execution_id)

    def complete_trace(self, execution_id: str, status: SpanStatus = SpanStatus.OK,
                       error: Optional[str] = None) -> None:
        trace = self._traces.get(execution_id)
        if not trace:
            return
        trace.ended_at = time.time()
        trace.total_duration_ms = (trace.ended_at - trace.started_at) * 1000
        trace.status = status
        trace.error = error

    def all_traces(self, limit: int = 100, offset: int = 0) -> List[ExecutionTrace]:
        items = sorted(self._traces.values(), key=lambda t: t.started_at, reverse=True)
        return items[offset:offset + limit]

    def recent_errors(self, minutes: int = 5) -> List[ExecutionTrace]:
        cutoff = time.time() - (minutes * 60)
        return [
            t for t in self._traces.values()
            if t.status == SpanStatus.ERROR and t.started_at > cutoff
        ]

    def _evict_if_needed(self) -> None:
        if len(self._traces) < self._max_traces:
            return
        oldest = min(self._traces.keys(),
                     key=lambda eid: self._traces[eid].started_at)
        self._traces.pop(oldest, None)

    def clear(self) -> None:
        self._traces.clear()
