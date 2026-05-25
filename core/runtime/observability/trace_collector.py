"""Phase F4 — TraceCollector implementation.  # LAW-12 # LAW-11 # RULE-2

Implements ITraceCollector: start_span, end_span, add_attribute, propagate_context.

LAW 12: Every span carries trace_id, span_id, parent_id.
LAW 11: No global state — per-instance span tracking.

Ref: Canon LAW 12 (Traceability), LAW 11 (No global state)
Ref: artifacts/design/f4/protocols/01_observability_protocols.py::ITraceCollector
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Dict, List, Optional

from core.runtime.models.observability_models import SpanStatus, TraceSpan

logger = logging.getLogger("emo_ai.observability.trace_collector")


class TraceCollector:  # ←→ ITraceCollector  # LAW-12
    """Concrete implementation of ITraceCollector.

    Manages span lifecycle with per-instance tracking (LAW 11).
    Each span is stored in _active_spans dict until end_span().
    """

    def __init__(self) -> None:
        self._active_spans: Dict[str, TraceSpan] = {}
        self._completed_spans: List[TraceSpan] = []

    @property
    def active_span_count(self) -> int:
        return len(self._active_spans)

    @property
    def completed_spans(self) -> List[TraceSpan]:
        return list(self._completed_spans)

    # ── start_span ──────────────────────────────────────────────

    def start_span(  # LAW-12
        self,
        operation_name: str,
        trace_id: str,
        parent_id: Optional[str] = None,
        attributes: Optional[Dict[str, str]] = None,
    ) -> str:
        span_id = str(uuid.uuid4())
        span = TraceSpan(
            trace_id=trace_id,
            span_id=span_id,
            parent_id=parent_id,
            operation_name=operation_name,
            start_ns=time.monotonic_ns(),
            attributes=attributes or {},
            domain=self._infer_domain(operation_name),
        )
        self._active_spans[span_id] = span
        logger.debug("Started span %s (%s)", span_id, operation_name)
        return span_id

    # ── end_span ────────────────────────────────────────────────

    def end_span(  # LAW-12, RULE-2
        self,
        span_id: str,
        status: SpanStatus = SpanStatus.OK,
        attributes: Optional[Dict[str, str]] = None,
    ) -> None:
        span = self._active_spans.pop(span_id, None)
        if span is None:
            logger.warning("end_span called for unknown span: %s", span_id)
            return

        span.end_ns = time.monotonic_ns()
        span.status = status
        if attributes:
            span.attributes.update(attributes)

        self._completed_spans.append(span)
        logger.debug("Ended span %s (%s) status=%s", span_id, span.operation_name, status.value)

    # ── add_attribute ───────────────────────────────────────────

    def add_attribute(  # LAW-12
        self,
        span_id: str,
        key: str,
        value: str,
    ) -> None:
        span = self._active_spans.get(span_id)
        if span is None:
            logger.warning("add_attribute called for unknown/inactive span: %s", span_id)
            return
        span.attributes[key] = value

    # ── propagate_context ───────────────────────────────────────

    def propagate_context(  # LAW-12
        self,
        trace_id: str,
        span_id: str,
        target_domain: str,
    ) -> Dict[str, str]:
        return {
            "trace_id": trace_id,
            "parent_span_id": span_id,
            "target_domain": target_domain,
            "source": "f4_observer",
        }

    # ── reset (testing) ─────────────────────────────────────────

    def reset(self) -> None:
        self._active_spans.clear()
        self._completed_spans.clear()

    @staticmethod
    def _infer_domain(operation_name: str) -> str:
        prefix = operation_name.split(".")[0] if "." in operation_name else "f4"
        known = {"api": "f1", "mesh": "d8", "scheduler": "f3", "worker": "f3"}
        return known.get(prefix, "f4")
