"""3.8.3 — Runtime Self-Awareness API.

This is the Cognitive Runtime API — the first layer where the runtime
can explain itself. Every execution, failure, dependency, and decision
becomes introspectable.

API:
  explain_execution(execution_id)  → full execution narrative
  explain_failure(execution_id)    → failure path + root cause
  explain_dependency(tool)         → why this tool was called
  why_executed(tool)               → execution triggers + frequency
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional

from core.codegraph.bridge import RuntimeStats
from core.codegraph.graph import CodeGraph
from core.codegraph.runtime_intelligence import (
    ExecutionTopology,
    FailureTopology,
    HotspotAnalyzer,
    RuntimeCentrality,
)
from core.codegraph.runtime_intelligence.execution_frequency import ExecutionFrequencyTracker
from core.runtime.event_store import EventStore


class RuntimeIntelligence:
    """Self-awareness API for the execution runtime.

    Wires RuntimeStats, EventStore, CodeGraph, and the trace intelligence
    layers into a single explainable interface.
    """

    def __init__(
        self,
        event_store: Optional[EventStore] = None,
        stats: Optional[RuntimeStats] = None,
        graph: Optional[CodeGraph] = None,
    ):
        self._event_store = event_store
        self._stats = stats or RuntimeStats()
        self._graph = graph
        self._execution_topology = ExecutionTopology()
        self._failure_topology = FailureTopology()
        self._frequency_tracker = ExecutionFrequencyTracker()

    def explain_execution(self, execution_id: str) -> Dict[str, Any]:
        """Full execution narrative for a given session/trace ID."""
        events = self._load_events(execution_id)
        if not events:
            return {"execution_id": execution_id, "error": "not found"}

        exec_graph = self._execution_topology.build(events)
        failure_paths = self._failure_topology.analyze(events)

        tool_counts: Dict[str, int] = defaultdict(int)
        failure_counts: Dict[str, int] = defaultdict(int)
        for event in events:
            payload = self._extract(event, "payload", {})
            tool = payload.get("tool", "")
            etype = self._extract(event, "event_type", "")
            if tool:
                tool_counts[tool] += 1
                if etype in ("NODE_FAILED",):
                    failure_counts[tool] += 1

        return {
            "execution_id": execution_id,
            "total_events": len(events),
            "tools_invoked": dict(tool_counts),
            "failure_count": dict(failure_counts),
            "execution_graph": exec_graph.to_dict(),
            "failure_paths": [
                {
                    "root_tool": fp.root_tool,
                    "retry_count": fp.retry_count,
                    "final_outcome": fp.final_outcome,
                    "is_storm": fp.is_storm(),
                }
                for fp in failure_paths
            ],
        }

    def explain_failure(self, execution_id: str) -> Dict[str, Any]:
        """Failure path + root cause analysis for a session."""
        events = self._load_events(execution_id)
        if not events:
            return {"execution_id": execution_id, "error": "not found"}

        failure_paths = self._failure_topology.analyze(events)
        if not failure_paths:
            return {
                "execution_id": execution_id,
                "has_failures": False,
                "message": "No failures detected",
            }

        primary = failure_paths[0]
        return {
            "execution_id": execution_id,
            "has_failures": True,
            "root_tool": primary.root_tool,
            "retry_count": primary.retry_count,
            "final_outcome": primary.final_outcome,
            "is_storm": primary.is_storm(),
            "failure_chain": [
                {
                    "tool": fn.tool,
                    "failure_type": fn.failure_type,
                    "error": fn.error,
                }
                for fn in primary.nodes
            ],
            "total_paths": len(failure_paths),
        }

    def explain_dependency(self, tool: str) -> Dict[str, Any]:
        """Why a tool was called — its execution triggers + runtime dependencies."""
        hotspot = self._compute_hotspot(tool)
        centrality = self._compute_centrality(tool)
        trend = self._frequency_tracker.get_trend(tool)

        return {
            "tool": tool,
            "hotspot_score": hotspot.score if hotspot else 0.0,
            "execution_count": hotspot.execution_count if hotspot else 0,
            "failure_rate": hotspot.failure_rate if hotspot else 0.0,
            "runtime_centrality": centrality.runtime_centrality if centrality else 0.0,
            "static_coupling": centrality.static_coupling if centrality else 0.0,
            "trend": {
                "direction": trend.trend_direction,
                "total_executions": trend.total_executions,
                "avg_per_session": trend.avg_per_session,
                "session_count": trend.session_count,
            },
        }

    def why_executed(self, tool: str) -> Dict[str, Any]:
        """Execution triggers + frequency summary for a tool."""
        records = self._frequency_tracker.get_tool_frequency(tool)
        hotspot = self._compute_hotspot(tool)

        return {
            "tool": tool,
            "total_executions": sum(r.execution_count for r in records),
            "total_sessions": len(records),
            "hotspot_rank": hotspot.score if hotspot else 0.0,
            "execution_log": [
                {
                    "session_id": r.session_id,
                    "count": r.execution_count,
                    "failures": r.failure_count,
                }
                for r in records[-10:]
            ],
            "last_5_sessions": [
                r.session_id for r in records[-5:]
            ],
        }

    def record_execution(
        self,
        session_id: str,
        tool: str,
        success: bool,
    ) -> None:
        self._frequency_tracker.record_execution(session_id, tool, success)

    def _load_events(self, execution_id: str) -> List[Any]:
        if self._event_store is None:
            return []
        return self._event_store.replay(session_id=execution_id)

    def _compute_hotspot(self, tool: str):
        analyzer = HotspotAnalyzer(self._stats, self._graph)
        hotspots = analyzer.analyze(min_executions=0)
        for h in hotspots:
            if h.tool == tool:
                return h
        return None

    def _compute_centrality(self, tool: str):
        engine = RuntimeCentrality(self._stats, self._graph)
        scores = engine.compute()
        for s in scores:
            if s.tool == tool:
                return s
        return None

    @staticmethod
    def _extract(event, key: str, default=None):
        if isinstance(event, dict):
            return event.get(key, default)
        return getattr(event, key, default)
