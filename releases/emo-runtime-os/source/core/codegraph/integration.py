"""CodeGraph → Runtime Integration Layer.

Bridges the static analysis subsystem into the live runtime.
Provides:
  - Tool-to-node deterministic mapping (replaces fragile string matching)
  - Incremental graph updates (for hot-reload)
  - Runtime query API (hotspots, risk, centrality)
  - Real-time drift monitoring

This is the ONLY entry point for runtime subsystems to access CodeGraph.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Set

from core.codegraph.bridge import (
    CodeGraphEventSubscriber,
    RuntimeStats,
    RuntimeAwareQueryEngine,
)
from core.codegraph.graph import CodeGraph, Node
from core.codegraph.query_engine import CodeGraphQueryEngine
from core.codegraph.runtime_intelligence.hotspot_analyzer import HotspotAnalyzer
from core.codegraph.runtime_intelligence.runtime_centrality import RuntimeCentrality
from core.codegraph.runtime_intelligence.execution_frequency import (
    ExecutionFrequencyTracker,
)
from core.codegraph.runtime_intelligence.failure_topology import FailureTopology
from core.codegraph.drift.runtime_drift_detector import RuntimeDriftDetector
from core.codegraph.drift.runtime_graph_builder import RuntimeGraphBuilder, RuntimeExecutionGraph

logger = logging.getLogger("emo_ai.codegraph.integration")


class CodeGraphRuntime:
    """Production bridge between CodeGraph static analysis and the live runtime.

    Responsibilities:
      1. Deterministic tool→node mapping (tool registry instead of string matching)
      2. Incremental graph updates
      3. Real-time hotspot/risk/centrality queries
      4. Runtime drift detection
      5. Failure topology analysis

    Usage:
        cg = CodeGraphRuntime(codegraph)
        cg.wire(event_bus, tool_registry)
        # Later:
        hotspots = cg.get_hotspots()
        risk = cg.get_risk_profile("my_tool")
        drift = cg.check_runtime_drift(events)
    """

    def __init__(self, codegraph: Optional[CodeGraph] = None):
        self._graph = codegraph
        self._stats = RuntimeStats()
        self._frequency = ExecutionFrequencyTracker()
        self._tool_map: Dict[str, str] = {}  # tool_name → node_id
        self._subscriber: Optional[CodeGraphEventSubscriber] = None
        self._query_engine: Optional[CodeGraphQueryEngine] = None
        self._runtime_query: Optional[RuntimeAwareQueryEngine] = None
        self._last_drift_check: float = 0.0
        self._drift_interval: float = 60.0

    # ── Lifecycle ─────────────────────────────────────────────

    def set_graph(self, codegraph: CodeGraph) -> None:
        """Set or replace the static analysis graph."""
        self._graph = codegraph
        self._query_engine = CodeGraphQueryEngine(codegraph)
        self._rebuild_runtime_query()

    def wire(self, event_bus: Any,
             tool_registry: Optional[Dict[str, str]] = None) -> None:
        """Wire into the runtime event bus.

        Args:
            event_bus: The system's IEventBus instance.
            tool_registry: Dict mapping tool_name → node_id for deterministic
                          correlation. If None, falls back to discovery.
        """
        if tool_registry:
            self._tool_map.update(tool_registry)

        if event_bus and self._stats:
            self._subscriber = CodeGraphEventSubscriber(event_bus)
            self._stats = self._subscriber._stats

    def register_tool_mapping(self, tool_name: str, node_id: str) -> None:
        """Register deterministic tool→node mapping.

        This replaces the fragile string matching in merge_into().
        """
        self._tool_map[tool_name] = node_id

    def register_tool_mappings(self, mapping: Dict[str, str]) -> None:
        self._tool_map.update(mapping)

    # ── Event Tracking ────────────────────────────────────────

    def record_execution(self, session_id: str, tool: str, success: bool) -> None:
        """Record an execution event in the frequency tracker."""
        self._frequency.record_execution(session_id, tool, success)

    # ── Hotspot Detection ─────────────────────────────────────

    def get_hotspots(self, min_executions: int = 3) -> List[Dict[str, Any]]:
        """Get tools with high failure rates or retry density."""
        if not self._graph:
            return []
        analyzer = HotspotAnalyzer(self._stats, self._graph)
        return [
            {
                "tool": h.tool,
                "score": round(h.score, 3),
                "failure_rate": round(h.failure_rate, 3),
                "avg_duration": round(h.avg_duration, 2),
                "execution_count": h.execution_count,
            }
            for h in analyzer.analyze(min_executions=min_executions)
        ]

    # ── Risk Profile ──────────────────────────────────────────

    def get_risk_profile(self, tool_name: str) -> Dict[str, Any]:
        """Get risk profile for a tool from the static graph."""
        if not self._query_engine:
            return {"risk_score": 0.0, "coupling_score": 0.0}

        node_id = self._tool_map.get(tool_name, "")
        if not node_id:
            return {"risk_score": 0.0, "coupling_score": 0.0}

        coupling = self._query_engine.get_coupling_score(node_id)
        risk = self._query_engine.get_risk_profile(node_id)
        return {
            "risk_score": round(risk.get("risk_score", 0.0), 3),
            "coupling_score": round(coupling, 3),
            "dependencies": risk.get("dependencies", []),
            "dependents": risk.get("dependents", []),
        }

    # ── Centrality ────────────────────────────────────────────

    def get_centrality(self) -> List[Dict[str, Any]]:
        """Get runtime centrality scores for all tools."""
        if not self._graph:
            return []
        centrality = RuntimeCentrality(self._stats, self._graph)
        return [
            {
                "tool": c.tool,
                "centrality": round(c.centrality, 3),
                "execution_frequency": c.execution_frequency,
                "failure_impact": round(c.failure_impact, 3),
                "silently_critical": c.silently_critical,
            }
            for c in centrality.compute()
        ]

    def silently_critical(self, threshold: float = 0.7) -> List[str]:
        """Find tools with low static risk but high runtime importance."""
        if not self._graph:
            return []
        centrality = RuntimeCentrality(self._stats, self._graph)
        return centrality.silently_critical(threshold)

    # ── Runtime Drift Detection ───────────────────────────────

    def check_runtime_drift(self, events: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Compare static graph vs runtime behavior.

        Detects hidden dependencies, boundary violations, coupling explosions.
        """
        if not self._graph:
            return {"drift_detected": False, "events": []}

        builder = RuntimeGraphBuilder()
        runtime_graph: RuntimeExecutionGraph = builder.build(events)

        detector = RuntimeDriftDetector()
        result = detector.detect(self._graph, runtime_graph)

        return {
            "drift_detected": result.drift_detected if hasattr(result, "drift_detected") else False,
            "severity": result.severity if hasattr(result, "severity") else "none",
            "events": (
                [{"type": e.type, "severity": e.severity, "description": e.description}
                 for e in result.events]
                if hasattr(result, "events") else []
            ),
        }

    # ── Failure Topology ──────────────────────────────────────

    def analyze_failures(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Analyze failure propagation from runtime events."""
        topology = FailureTopology()
        paths = topology.analyze(events)
        return [
            {
                "path": [{"tool": n.tool, "error": n.error} for n in p.nodes],
                "total_duration": p.total_duration,
                "error_count": len(p.nodes),
            }
            for p in paths
        ]

    # ── Frequency Trends ──────────────────────────────────────

    def get_frequency_trends(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get execution frequency trends across sessions."""
        return [
            {
                "tool": f.tool,
                "frequency": f.frequency,
                "sessions": f.sessions,
            }
            for f in self._frequency.get_all_frequencies()[:limit]
        ]

    def get_trend(self, tool: str) -> Optional[Dict[str, Any]]:
        """Get the execution trend for a specific tool."""
        trend = self._frequency.get_trend(tool)
        if not trend:
            return None
        return {
            "tool": trend.tool,
            "direction": trend.direction.value if hasattr(trend.direction, "value") else str(trend.direction),
            "change_rate": round(trend.change_rate, 3),
        }

    # ── Internal ──────────────────────────────────────────────

    def _rebuild_runtime_query(self) -> None:
        if self._graph and self._stats:
            self._runtime_query = RuntimeAwareQueryEngine(self._graph, self._stats)

    @property
    def is_wired(self) -> bool:
        return self._subscriber is not None

    @property
    def tool_count(self) -> int:
        return len(self._tool_map)

    @property
    def graph(self) -> Optional[CodeGraph]:
        return self._graph
