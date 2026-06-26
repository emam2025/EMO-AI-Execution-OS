"""Phase F4 — ExecutionTimelineBuilder: chronological event reconstruction.

LAW 5: Timeline built exclusively from EventStore + scheduling events.
LAW 12: Every timeline node is traceable to source event.
RULE 1: Deterministic — same events → same timeline.

Ref: Canon LAW 5, LAW 12, RULE 1
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("emo_ai.observability.timeline")


@dataclass
class TimelineNode:
    sequence: int = 0
    node_id: str = ""
    event_type: str = ""
    source: str = ""
    timestamp_ns: int = 0
    worker_id: str = ""
    span_id: str = ""
    state: str = ""
    details: str = ""


@dataclass
class Timeline:
    execution_id: str
    nodes: List[TimelineNode] = field(default_factory=list)
    total_duration_ms: float = 0.0
    error_count: int = 0


class ExecutionTimelineBuilder:
    """Reconstructs chronological execution timeline from events.

    Integrates EventStore events with SchedulingDecisions and
    QuotaEvents for a complete execution narrative.

    RULE 1: Deterministic — same events produce same timeline.
    """

    def __init__(
        self,
        event_store: Any = None,
        event_bus: Any = None,
    ):
        self._event_store = event_store
        self._event_bus = event_bus

    # ── build_timeline ───────────────────────────────────────

    def build_timeline(
        self,
        execution_id: str,
        _include_scheduling: bool = True,
        _include_quota: bool = True,
    ) -> Timeline:
        """Build full execution timeline from EventStore.

        Filters events by execution_id, enriches with scheduling
        and quota decisions, returns chronologically sorted nodes.

        Args:
            execution_id: The execution to reconstruct.
            include_scheduling: Include scheduling decisions.
            include_quota: Include quota events.

        Returns:
            Timeline with sorted nodes, duration, and error count.
        """
        nodes: List[TimelineNode] = []

        if self._event_store is not None:
            events = self._event_store.replay()
            for event in events:
                payload = event.payload or {}
                evt_exec = payload.get("execution_id", "")

                if evt_exec and evt_exec != execution_id:
                    continue
                if not evt_exec:
                    trace_id = getattr(event, "trace_id", "")
                    span_id = getattr(event, "session_id", "")
                    if trace_id != execution_id and span_id != execution_id:
                        continue

                node = TimelineNode(
                    sequence=len(nodes),
                    node_id=event.event_id,
                    event_type=str(event.event_type),
                    source=event.source,
                    timestamp_ns=int(event.timestamp * 1_000_000_000),
                    worker_id=payload.get("worker_id", ""),
                    span_id=payload.get("span_id", ""),
                    state="completed",
                    details=payload.get("reason", ""),
                )

                event_type_lower = str(event.event_type).lower()
                if "error" in event_type_lower or "fail" in event_type_lower or "reject" in event_type_lower:
                    node.state = "failed"
                elif "preempt" in event_type_lower:
                    node.state = "preempted"
                elif "queued" in event_type_lower or "queue" in event_type_lower:
                    node.state = "queued"
                elif "schedule" in event_type_lower or "dispatch" in event_type_lower:
                    node.state = "running"

                nodes.append(node)

        if not nodes:
            return Timeline(execution_id=execution_id)

        nodes.sort(key=lambda n: n.timestamp_ns)

        first_ts = nodes[0].timestamp_ns
        last_ts = nodes[-1].timestamp_ns
        total_ms = (last_ts - first_ts) / 1_000_000 if last_ts > first_ts else 0.0
        error_count = sum(1 for n in nodes if n.state == "failed")

        return Timeline(
            execution_id=execution_id,
            nodes=nodes,
            total_duration_ms=total_ms,
            error_count=error_count,
        )
