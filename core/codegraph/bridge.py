"""3.6.4 — CodeGraph ↔ Runtime Event Bridge.

Translates execution events from IEventBus into CodeGraph
runtime stats, enabling graph-aware runtime execution analysis.

The bridge turns CodeGraph from a snapshot system into a
runtime-derived structural memory system.
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set

from core.codegraph.graph import CodeGraph, Node, NodeType
from core.codegraph.query_engine import CodeGraphQueryEngine
from core.interfaces.event_bus import IEventBus
from core.models.events import ExecutionEvent


class RuntimeStats:
    """Per-tool runtime execution statistics accumulated from events.

    Keyed by **tool name** (not CodeGraph node ID), since execution
    events carry tool names reliably while DAG node IDs are transient.
    """

    def __init__(self) -> None:
        self.execution_count: Dict[str, int] = defaultdict(int)
        self.failure_count: Dict[str, int] = defaultdict(int)
        self.total_duration: Dict[str, float] = defaultdict(float)
        self.last_status: Dict[str, str] = {}
        self.last_executed_at: Dict[str, float] = {}

    def record_node_completed(self, tool: str,
                              duration: float = 0.0) -> None:
        self.execution_count[tool] += 1
        self.total_duration[tool] += duration
        self.last_status[tool] = "completed"
        self.last_executed_at[tool] = time.time()

    def record_node_failed(self, tool: str) -> None:
        self.execution_count[tool] += 1
        self.failure_count[tool] += 1
        self.last_status[tool] = "failed"
        self.last_executed_at[tool] = time.time()

    def get_failure_rate(self, tool: str) -> float:
        total = self.execution_count.get(tool, 0)
        if total == 0:
            return 0.0
        return self.failure_count.get(tool, 0) / total

    def get_avg_duration(self, tool: str) -> float:
        total = self.execution_count.get(tool, 0)
        if total == 0:
            return 0.0
        return self.total_duration.get(tool, 0) / total

    def to_metadata(self, tool: str) -> Dict[str, Any]:
        return {
            "runtime_execution_count": self.execution_count.get(tool, 0),
            "runtime_failure_count": self.failure_count.get(tool, 0),
            "runtime_failure_rate": self.get_failure_rate(tool),
            "runtime_avg_duration": self.get_avg_duration(tool),
            "runtime_last_status": self.last_status.get(tool, ""),
            "runtime_last_executed_at": self.last_executed_at.get(tool, 0.0),
        }

    def snapshot(self) -> Dict[str, Dict[str, Any]]:
        return {
            t: self.to_metadata(t)
            for t in list(self.execution_count.keys())
        }


class CodeGraphEventSubscriber:
    """Subscribes to IEventBus and translates execution events
    into runtime stats for CodeGraph consumption.

    Usage:
        subscriber = CodeGraphEventSubscriber(event_bus)
        # subscriber automatically receives events and accumulates stats
        runtime_graph = subscriber.merge_into(graph)
    """

    def __init__(self, event_bus: IEventBus) -> None:
        self._event_bus = event_bus
        self._stats = RuntimeStats()
        self._event_count: int = 0
        self._session_count: Set[str] = set()
        self._subscribe()

    def _subscribe(self) -> None:
        self._event_bus.subscribe("execution", self._on_event)

    def _on_event(self, event: ExecutionEvent) -> None:
        self._event_count += 1
        if event.session_id:
            self._session_count.add(event.session_id)

        etype = event.event_type
        payload = event.payload

        if etype == "NODE_COMPLETED":
            tool = payload.get("tool", "")
            if tool:
                self._stats.record_node_completed(
                    tool,
                    duration=payload.get("duration", 0.0),
                )

        elif etype == "NODE_FAILED":
            tool = payload.get("tool", "")
            if tool:
                self._stats.record_node_failed(tool)

    def merge_into(self, graph: CodeGraph) -> CodeGraph:
        """Merge runtime stats into a static CodeGraph.

        Matches runtime stats to graph nodes by tool name:
        a tool named ``hybrid_retrieval`` matches a FILE node whose
        path contains ``hybrid_retrieval`` or whose name starts with
        the tool name.

        Runtime metadata is embedded in each matching node's
        ``metadata`` dict, and risk_score is adjusted upward for
        nodes with high failure rates.
        """
        for nid, node in graph.nodes.items():
            # Match: tool name appears in node path or name
            tool = self._find_tool_for_node(node)
            if tool is None:
                continue

            runtime_meta = self._stats.to_metadata(tool)
            if runtime_meta["runtime_execution_count"] == 0:
                continue

            node.metadata.update(runtime_meta)

            # Derive dynamic risk score: static + runtime penalty
            static_risk = node.risk_score or 0.0
            failure_rate = runtime_meta["runtime_failure_rate"]
            runtime_penalty = failure_rate * 0.2  # max 0.2 penalty
            node.risk_score = min(1.0, static_risk + runtime_penalty)

        return graph

    def _find_tool_for_node(self, node: Node) -> Optional[str]:
        """Match a CodeGraph node to a known tool name from runtime stats."""
        if node.type != NodeType.FILE:
            return None
        for tool in self._stats.execution_count:
            # Match: path contains tool name (e.g. .../hybrid_retrieval.py)
            if tool.replace("_", "") in node.path.replace("_", "").replace("-", ""):
                return tool
            # Match: name starts with tool (e.g. tool="hybrid" → name="hybrid_retrieval.py")
            if node.name.startswith(tool):
                return tool
        return None

    def stats_snapshot(self) -> Dict[str, Dict[str, Any]]:
        return self._stats.snapshot()

    @property
    def event_count(self) -> int:
        return self._event_count

    @property
    def session_count(self) -> int:
        return len(self._session_count)


class RuntimeAwareQueryEngine(CodeGraphQueryEngine):
    """Extends CodeGraphQueryEngine with runtime-aware queries.

    Adds the ability to answer questions that require both
    static graph structure and runtime execution data.
    """

    def __init__(self, graph: CodeGraph, stats: RuntimeStats) -> None:
        super().__init__(graph)
        self._stats = stats

    def get_hotspots(self, min_executions: int = 5) -> List[Dict[str, Any]]:
        """Tools with high execution count AND high failure rate."""
        hotspots: List[Dict[str, Any]] = []
        for tool, exec_count in self._stats.execution_count.items():
            if exec_count < min_executions:
                continue
            fail_rate = self._stats.get_failure_rate(tool)
            # Find matching graph node
            path = self._find_path_for_tool(tool)
            hotspots.append({
                "tool": tool,
                "path": path or "unknown",
                "executions": exec_count,
                "failure_rate": fail_rate,
            })
        hotspots.sort(key=lambda h: h["failure_rate"], reverse=True)
        return hotspots

    def get_most_executed(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Top N most-executed tools by runtime count."""
        ranked = sorted(
            self._stats.execution_count.items(),
            key=lambda x: x[1],
            reverse=True,
        )
        result: List[Dict[str, Any]] = []
        for tool, count in ranked[:limit]:
            path = self._find_path_for_tool(tool)
            result.append({
                "tool": tool,
                "path": path or "unknown",
                "executions": count,
            })
        return result

    def _find_path_for_tool(self, tool: str) -> Optional[str]:
        """Find the graph node path that matches a tool name."""
        for node in self._graph.nodes.values():
            if node.type != NodeType.FILE:
                continue
            if tool.replace("_", "") in node.path.replace("_", "").replace("-", ""):
                return node.path
            if node.name.startswith(tool):
                return node.path
        return None
