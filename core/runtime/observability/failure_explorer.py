"""Phase F4 — FailureExplorer: root cause analysis + trace export.

LAW 5: Failure analysis derived from EventStore + scheduling events.
LAW 12: Every failure hint linked to trace_id.
RULE 3: Patterns matched deterministically for reproducibility.

Ref: Canon LAW 5, LAW 12, RULE 3
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("emo_ai.observability.failure")


@dataclass
class RootCauseHint:
    cause: str = ""
    confidence: float = 0.0
    trace_id: str = ""
    affected_nodes: List[str] = field(default_factory=list)
    suggested_action: str = ""
    pattern_matched: str = ""


@dataclass
class TraceBundle:
    trace_id: str
    spans: List[Dict[str, Any]] = field(default_factory=list)
    failures: List[RootCauseHint] = field(default_factory=list)
    export_format: str = "json"


class FailureExplorer:
    """Root cause analysis engine for execution failures.

    Matches failure patterns against EventStore traces to suggest
    root causes and corrective actions.

    LAW 5: All analysis derived from observable events.
    RULE 3: Pattern matching is deterministic.
    """

    PATTERNS = [
        {
            "name": "quota_exhaustion",
            "keywords": ["quota", "exceeded", "resource", "ceiling"],
            "suggested_action": "Scale up cluster or reduce task resource requirements",
        },
        {
            "name": "worker_drain",
            "keywords": ["drain", "draining", "worker_drained", "DRAINED"],
            "suggested_action": "Check worker health and restart drained workers",
        },
        {
            "name": "retry_loop",
            "keywords": ["retry", "RETRY", "retry_handler", "max_retries"],
            "suggested_action": "Inspect task configuration and downstream dependencies",
        },
        {
            "name": "lease_expiry",
            "keywords": ["lease", "expired", "LEASE_EXPIRED", "lease_expired"],
            "suggested_action": "Renew lease or increase lease TTL",
        },
        {
            "name": "capability_violation",
            "keywords": ["capability", "violation", "blocked", "CAPABILITY"],
            "suggested_action": "Update capability registry or task requirements",
        },
        {
            "name": "preemption_loss",
            "keywords": ["preempt", "preempted", "PREEMPTED"],
            "suggested_action": "Increase task priority or reduce cluster load",
        },
    ]

    def __init__(
        self,
        event_store: Any = None,
        event_bus: Any = None,
        trace_collector: Any = None,
    ):
        self._event_store = event_store
        self._event_bus = event_bus
        self._trace_collector = trace_collector

    # ── analyze_failure ──────────────────────────────────────

    def analyze_failure(
        self,
        failure_event: Dict[str, Any],
        trace_id: str = "",
    ) -> RootCauseHint:
        """Analyze a failure event against known patterns.

        Matches the failure_event payload and EventStore events
        against PATTERNS to produce a RootCauseHint with confidence.

        Args:
            failure_event: Dict with error details (message, source, type).
            trace_id: Optional trace_id for correlation.

        Returns:
            RootCauseHint with cause, confidence, and suggested action.
        """
        error_message = str(failure_event.get("error", failure_event.get("message", "")))
        error_source = str(failure_event.get("source", failure_event.get("event_type", "")))

        candidates: List[tuple[str, float, str]] = []

        for pattern in self.PATTERNS:
            score = 0.0
            for keyword in pattern["keywords"]:
                if keyword.lower() in error_message.lower():
                    score += 0.25
                if keyword.lower() in error_source.lower():
                    score += 0.2

            if score > 0:
                candidates.append((pattern["name"], score, pattern["suggested_action"]))

        if self._event_store is not None:
            events = self._event_store.replay()
            trace_events = [e for e in events if trace_id and (
                getattr(e, "trace_id", "") == trace_id
                or e.event_id == trace_id
            )]
            for event in trace_events:
                payload = event.payload or {}
                event_msg = str(payload.get("reason", ""))
                for pattern in self.PATTERNS:
                    for keyword in pattern["keywords"]:
                        if keyword.lower() in event_msg.lower():
                            score = 0.15
                            candidates.append((
                                pattern["name"], score, pattern["suggested_action"],
                            ))

        if not candidates:
            return RootCauseHint(
                cause="unknown",
                confidence=0.0,
                trace_id=trace_id,
                suggested_action="Review execution logs for details",
                pattern_matched="none",
            )

        best = max(candidates, key=lambda c: c[1])
        confidence = min(1.0, best[1])

        return RootCauseHint(
            cause=best[0],
            confidence=round(confidence, 2),
            trace_id=trace_id,
            affected_nodes=[error_source],
            suggested_action=best[2],
            pattern_matched=best[0],
        )

    # ── export_trace_bundle ──────────────────────────────────

    def export_trace_bundle(
        self,
        trace_id: str,
        fmt: str = "json",
    ) -> TraceBundle:
        """Export complete trace data as a bundle for audit/replay.

        Args:
            trace_id: The trace to export.
            fmt: Export format ("json" or "csv").

        Returns:
            TraceBundle with spans, failures, and export format.
        """
        spans: List[Dict[str, Any]] = []

        if self._event_store is not None:
            events = self._event_store.replay()
            for event in events:
                if getattr(event, "trace_id", "") == trace_id or event.event_id == trace_id:
                    spans.append({
                        "event_id": event.event_id,
                        "event_type": event.event_type,
                        "timestamp": event.timestamp,
                        "source": event.source,
                        "payload": event.payload,
                        "trace_id": getattr(event, "trace_id", ""),
                    })

        if self._trace_collector is not None:
            for span in self._trace_collector.completed_spans:
                if span.trace_id == trace_id:
                    spans.append({
                        "span_id": span.span_id,
                        "trace_id": span.trace_id,
                        "operation": span.operation_name,
                        "duration_ns": span.duration_ns,
                        "status": span.status.value,
                    })

        failure = self.analyze_failure({}, trace_id=trace_id)

        if fmt == "csv":
            return TraceBundle(
                trace_id=trace_id,
                spans=spans,
                failures=[failure],
                export_format="csv",
            )

        return TraceBundle(
            trace_id=trace_id,
            spans=spans,
            failures=[failure],
            export_format="json",
        )
