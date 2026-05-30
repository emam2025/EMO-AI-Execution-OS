"""F4 — RuntimeDashboard: unified observability dashboard backend.

Aggregates data from all F4 subsystems:
  - TraceStore (distributed tracing)
  - TimelineStore (execution events)
  - FailureExplorer (failure analysis)
  - TopologyViewer (worker/node topology)
  - DAGVisualizer (DAG structure + paths)
  - ResourceScheduler (cluster summary)

Provides a single snapshot() call for the UI to consume.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from core.observability.trace import TraceStore, SpanStatus
from core.observability.timeline import TimelineStore, EventType
from core.observability.failure_explorer import FailureExplorer
from core.observability.topology_viewer import TopologyViewer
from core.observability.dag_visualizer import DAGVisualizer

logger = logging.getLogger("emo_ai.observability.dashboard")


class RuntimeDashboard:
    """Unified observability dashboard.

    Aggregates all F4 subsystems into a single snapshot
    that external tools (CLI, Web UI) can consume.
    """

    def __init__(self,
                 trace_store: Optional[TraceStore] = None,
                 timeline_store: Optional[TimelineStore] = None,
                 failure_explorer: Optional[FailureExplorer] = None,
                 topology_viewer: Optional[TopologyViewer] = None):
        self._traces = trace_store or TraceStore()
        self._timelines = timeline_store or TimelineStore()
        self._failures = failure_explorer or FailureExplorer()
        self._topology = topology_viewer or TopologyViewer()
        self._dag_viz = DAGVisualizer()

    @property
    def traces(self) -> TraceStore:
        return self._traces

    @property
    def timelines(self) -> TimelineStore:
        return self._timelines

    @property
    def failures(self) -> FailureExplorer:
        return self._failures

    @property
    def topology(self) -> TopologyViewer:
        return self._topology

    # ── Unified Snapshot ────────────────────────────────────

    def snapshot(self) -> Dict[str, Any]:
        """Aggregate all observability data into one snapshot.

        Returns:
            Complete dashboard state for UI rendering.
        """
        error_traces = self._traces.recent_errors(minutes=5)
        recent_events = self._timelines.query(
            since=time.time() - 300, limit=50,
        )

        return {
            "overview": self._overview(),
            "recent_errors": [
                {
                    "execution_id": t.execution_id,
                    "error": t.error,
                    "started_at": t.started_at,
                    "duration_ms": round(t.total_duration_ms, 2),
                }
                for t in error_traces
            ],
            "topology": self._topology.to_graph(),
            "failure_analysis": self._failures.summary(),
            "recent_events": [
                {
                    "time": e.timestamp,
                    "type": e.event_type.value,
                    "execution_id": e.execution_id,
                    "service": e.service,
                    "message": e.message,
                }
                for e in recent_events
            ],
            "timestamp": time.time(),
        }

    def execution_detail(self, execution_id: str) -> Dict[str, Any]:
        """Get detailed observability data for a single execution."""
        trace = self._traces.get_trace(execution_id)
        timeline = self._timelines.execution_summary(execution_id)

        result = {"execution_id": execution_id}

        if trace:
            result["trace"] = trace.to_dict()
        if timeline:
            result["timeline"] = timeline

        return result

    def system_overview(self) -> Dict[str, Any]:
        """High-level system overview."""
        return self._overview()

    def _overview(self) -> Dict[str, Any]:
        recent_failures = self._failures.summary()
        topology = self._topology.summary()
        all_traces = self._traces.all_traces(limit=100)
        running = sum(1 for t in all_traces if t.status == SpanStatus.PENDING)
        completed = sum(1 for t in all_traces if t.status == SpanStatus.OK)
        failed = sum(1 for t in all_traces if t.status == SpanStatus.ERROR)

        return {
            "traces": {
                "total": len(self._traces._traces),
                "running": running,
                "completed": completed,
                "failed": failed,
            },
            "topology": topology,
            "failures": {
                "total": recent_failures["total_failures"],
                "recovery_rate": recent_failures.get("recovery_rate", 0.0),
                "top_errors": recent_failures.get("top_errors", []),
            },
            "events": {
                "total_timelines": len(self._timelines._timelines),
            },
        }

    # ── Search / Query ──────────────────────────────────────

    def search_executions(self, query: str) -> List[Dict[str, Any]]:
        """Search executions by ID, error, or service."""
        query_lower = query.lower()
        results = []

        for execution_id, trace in self._traces._traces.items():
            if query_lower in execution_id.lower():
                results.append(self.execution_detail(execution_id))
                continue
            if trace.error and query_lower in trace.error.lower():
                results.append(self.execution_detail(execution_id))

        return results[:20]

    def failure_trends(self, minutes: int = 30) -> Dict[str, Any]:
        """Get failure trends for the dashboard."""
        return self._failures.failure_trend(minutes=minutes)
