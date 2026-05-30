"""3.8.1.1 — Hotspot Analyzer.

Detects high-frequency runtime nodes from execution events.
Combines execution count, failure rate, avg duration, and retry
density into a single RuntimeHotspot score.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.codegraph.bridge import RuntimeStats
from core.codegraph.graph import CodeGraph


@dataclass
class RuntimeHotspot:
    node_id: str = ""
    tool: str = ""
    execution_count: int = 0
    failure_rate: float = 0.0
    avg_duration: float = 0.0
    retry_density: float = 0.0
    score: float = 0.0


class HotspotAnalyzer:
    """Combines RuntimeStats + CodeGraph to find execution hotspots.

    A hotspot is a node that has high runtime impact — either through
    frequency, failure rate, or both. The score is a weighted sum:
      0.4 × normalized(execution_count)
    + 0.3 × failure_rate
    + 0.2 × normalized(avg_duration)
    + 0.1 × retry_density
    """

    HOTSPOT_WEIGHTS = {
        "execution_weight": 0.4,
        "failure_weight": 0.3,
        "duration_weight": 0.2,
        "retry_weight": 0.1,
    }

    def __init__(self, stats: RuntimeStats, graph: Optional[CodeGraph] = None):
        self._stats = stats
        self._graph = graph

    def analyze(self, min_executions: int = 1) -> List[RuntimeHotspot]:
        tools = list(self._stats.execution_count.keys())
        if not tools:
            return []

        max_count = max(self._stats.execution_count.values()) or 1
        max_duration = max(self._stats.total_duration.values()) or 1.0

        hotspots: List[RuntimeHotspot] = []
        for tool in tools:
            exec_count = self._stats.execution_count.get(tool, 0)
            if exec_count < min_executions:
                continue

            failure_rate = self._stats.get_failure_rate(tool)
            avg_duration = self._stats.get_avg_duration(tool)

            retry_density = self._compute_retry_density(tool)
            node_id = self._find_node_id(tool)

            score = (
                self.HOTSPOT_WEIGHTS["execution_weight"] * (exec_count / max_count)
                + self.HOTSPOT_WEIGHTS["failure_weight"] * failure_rate
                + self.HOTSPOT_WEIGHTS["duration_weight"] * (avg_duration / max_duration)
                + self.HOTSPOT_WEIGHTS["retry_weight"] * retry_density
            )

            hotspots.append(RuntimeHotspot(
                node_id=node_id,
                tool=tool,
                execution_count=exec_count,
                failure_rate=failure_rate,
                avg_duration=avg_duration,
                retry_density=retry_density,
                score=round(score, 4),
            ))

        hotspots.sort(key=lambda h: h.score, reverse=True)
        return hotspots

    def _compute_retry_density(self, tool: str) -> float:
        total = self._stats.execution_count.get(tool, 0)
        if total == 0:
            return 0.0
        failures = self._stats.failure_count.get(tool, 0)
        return failures / total if total > 0 else 0.0

    def _find_node_id(self, tool: str) -> str:
        if self._graph is None:
            return tool
        for nid, node in self._graph.nodes.items():
            if node.type.name == "FILE":
                if tool.replace("_", "") in node.path.replace("_", "").replace("-", ""):
                    return nid
                if getattr(node, "name", "").startswith(tool):
                    return nid
        return tool
