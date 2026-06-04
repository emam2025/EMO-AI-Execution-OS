"""Phase F4 — DistributedTracer: trace/span creation + reconstruction.

LAW 12: Every span carries trace_id, span_id, parent_id.
LAW 5: All trace operations are observable via EventStore.
RULE 1: Deterministic reconstruction — same events → same trace.

Wraps the existing TraceCollector with higher-level trace lifecycle
and reconstruction from EventStore events.

Ref: Canon LAW 5, LAW 12, RULE 1
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.runtime.models.observability_models import SpanStatus, TraceSpan

logger = logging.getLogger("emo_ai.observability.tracer")


@dataclass
class Span:
    trace_id: str
    span_id: str
    parent_id: Optional[str] = None
    operation_name: str = ""
    start_ns: int = 0
    end_ns: int = 0
    status: SpanStatus = SpanStatus.UNKNOWN
    attributes: Dict[str, str] = field(default_factory=dict)
    domain: str = ""
    worker_id: str = ""
    service: str = ""

    @property
    def duration_ms(self) -> float:
        if self.end_ns > self.start_ns:
            return (self.end_ns - self.start_ns) / 1_000_000
        return 0.0


@dataclass
class Trace:
    trace_id: str
    execution_id: str = ""
    dag_id: str = ""
    spans: List[Span] = field(default_factory=list)
    created_at_ns: int = 0

    @property
    def total_duration_ms(self) -> float:
        if not self.spans:
            return 0.0
        start = min(s.start_ns for s in self.spans)
        end = max(s.end_ns for s in self.spans if s.end_ns > 0)
        if end > 0:
            return (end - start) / 1_000_000
        return 0.0

    @property
    def error_count(self) -> int:
        return sum(1 for s in self.spans if s.status == SpanStatus.ERROR)


class DistributedTracer:
    """Distributed trace creation, propagation, and reconstruction.

    LAW 12: Every span is linked to a trace_id and parent_id.
    LAW 5: All spans are recorded for reconstruction.
    RULE 1: reconstruct_trace is deterministic on same event set.
    """

    def __init__(
        self,
        trace_collector: Any = None,
        event_store: Any = None,
        event_bus: Any = None,
    ):
        self._collector = trace_collector
        self._event_store = event_store
        self._event_bus = event_bus
        self._traces: Dict[str, Trace] = {}

    # ── create_trace ─────────────────────────────────────────

    def create_trace(
        self,
        execution_id: str,
        dag_id: str = "",
    ) -> str:
        """Create a new trace root.

        Returns trace_id linked to execution_id and DAG nodes.
        """
        trace_id = uuid.uuid4().hex[:16]
        now_ns = time.monotonic_ns()

        trace = Trace(
            trace_id=trace_id,
            execution_id=execution_id,
            dag_id=dag_id,
            created_at_ns=now_ns,
        )
        self._traces[trace_id] = trace

        self._emit_event("trace.created", {
            "trace_id": trace_id,
            "execution_id": execution_id,
            "dag_id": dag_id,
        })

        logger.info("Trace created: %s (execution=%s)", trace_id, execution_id)
        return trace_id

    # ── propagate_span ───────────────────────────────────────

    def propagate_span(
        self,
        service: str,
        event_type: str,
        payload: Dict[str, Any],
        trace_id: str = "",
        parent_span_id: str = "",
    ) -> str:
        """Create and record a span for a service event.

        Links to parent trace/span and records in EventStore.

        Returns span_id.
        """
        span_id = uuid.uuid4().hex[:12]
        now_ns = time.monotonic_ns()

        span = Span(
            trace_id=trace_id,
            span_id=span_id,
            parent_id=parent_span_id or None,
            operation_name=f"{service}.{event_type}",
            start_ns=now_ns,
            status=SpanStatus.OK,
            attributes=dict(payload),
            domain=self._infer_domain(service),
            worker_id=payload.get("worker_id", ""),
            service=service,
        )

        if trace_id and trace_id in self._traces:
            self._traces[trace_id].spans.append(span)

        if self._collector is not None:
            collector_span_id = self._collector.start_span(
                operation_name=span.operation_name,
                trace_id=trace_id,
                parent_id=parent_span_id or None,
                attributes=dict(payload),
            )
            self._collector.end_span(
                collector_span_id,
                status=SpanStatus.OK,
                attributes=dict(payload),
            )

        self._emit_event("trace.span.propagated", {
            "trace_id": trace_id,
            "span_id": span_id,
            "parent_span_id": parent_span_id,
            "service": service,
            "event_type": event_type,
        })

        logger.debug("Span %s propagated for %s.%s", span_id, service, event_type)
        return span_id

    # ── reconstruct_trace ────────────────────────────────────

    def reconstruct_trace(self, trace_id: str) -> List[Span]:
        """Reconstruct the full chronological timeline for a trace.

        RULE 1: Deterministic — same events produce same span list.
        LAW 12: Every span is linked to trace_id.

        Returns spans sorted by start_ns (child-first within same time).
        """
        stored = self._traces.get(trace_id)
        if stored is None:
            spans = self._reconstruct_from_events(trace_id)
        else:
            spans = list(stored.spans)

        spans.sort(key=lambda s: (s.start_ns, s.span_id))
        return spans

    def _reconstruct_from_events(self, trace_id: str) -> List[Span]:
        """Rebuild trace spans from EventStore events."""
        if self._event_store is None:
            return []

        events = self._event_store.replay()
        spans: List[Span] = []

        for event in events:
            payload = event.payload or {}
            if event.trace_id != trace_id:
                continue

            span = Span(
                trace_id=event.trace_id,
                span_id=event.event_id,
                parent_id=payload.get("parent_span_id", ""),
                operation_name=f"{event.source}.{event.event_type.lower()}",
                start_ns=int(event.timestamp * 1_000_000_000),
                status=SpanStatus.OK,
                attributes=payload,
                domain=self._infer_domain(event.source),
                service=event.source,
            )
            spans.append(span)

        return spans

    def get_trace(self, trace_id: str) -> Optional[Trace]:
        return self._traces.get(trace_id)

    @staticmethod
    def _infer_domain(service: str) -> str:
        prefix = service.split(".")[0].lower() if "." in service else service.lower()
        known = {
            "api": "f1", "mesh": "d8", "scheduler": "f3", "orchestrator": "f3",
            "cluster": "f2", "runtime": "f1", "control": "f2", "isolation": "p4",
            "dashboard": "f4", "tracer": "f4", "timeline": "f4", "failure": "f4",
        }
        return known.get(prefix, "f4")

    def _emit_event(self, topic: str, payload: Dict[str, Any]) -> None:
        if self._event_bus is None:
            return
        try:
            from core.models.events import ExecutionEvent
            event = ExecutionEvent(
                event_id=uuid.uuid4().hex[:16],
                event_type=topic.split(".")[-1].upper(),
                timestamp=time.time(),
                source="DistributedTracer",
                payload=payload,
            )
            self._event_bus.publish(f"observability.{topic}", event)
        except Exception as e:
            logger.error("Failed to emit event %s: %s", topic, e)
