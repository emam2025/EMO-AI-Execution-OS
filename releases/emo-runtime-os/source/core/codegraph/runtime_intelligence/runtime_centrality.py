"""3.8.1.4 — Runtime Centrality Engine.

Measures runtime importance of nodes — not just static coupling.
A node with low static coupling but high execution frequency is
runtime-critical.

Centrality = f(execution_count, failure_rate, dependency_count)
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.codegraph.bridge import RuntimeStats
from core.codegraph.graph import CodeGraph


@dataclass
class RuntimeCentralityScore:
    node_id: str = ""
    tool: str = ""
    path: str = ""
    execution_frequency: float = 0.0
    failure_impact: float = 0.0
    dependency_count: int = 0
    static_coupling: float = 0.0
    runtime_centrality: float = 0.0


class RuntimeCentrality:
    """Computes runtime centrality — execution importance.

    Contrast:
      - Static risk: CodeGraph risk_score (coupling + complexity).
      - Runtime centrality: actual execution frequency + failure impact.

    A node with low static risk but high runtime centrality is
    "silently critical" — it looks safe on paper but is vital at runtime.
    """

    def __init__(self, stats: RuntimeStats, graph: Optional[CodeGraph] = None):
        self._stats = stats
        self._graph = graph

    def compute(self) -> List[RuntimeCentralityScore]:
        tools = list(self._stats.execution_count.keys())
        if not tools:
            return []

        max_count = max(self._stats.execution_count.values()) or 1

        scores: List[RuntimeCentralityScore] = []
        for tool in tools:
            exec_count = self._stats.execution_count.get(tool, 0)
            if exec_count == 0:
                continue

            node_id = self._find_node_id(tool)
            path = self._find_path(tool)
            static_info = self._get_static_info(node_id)

            execution_frequency = exec_count / max_count
            failure_impact = self._stats.get_failure_rate(tool)
            dependency_count = static_info.get("dependency_count", 0)
            static_coupling = static_info.get("coupling", 0.0)

            runtime_centrality = round(
                0.5 * execution_frequency
                + 0.3 * failure_impact
                + 0.2 * (min(dependency_count, 10) / 10.0),
                4,
            )

            scores.append(RuntimeCentralityScore(
                node_id=node_id,
                tool=tool,
                path=path,
                execution_frequency=execution_frequency,
                failure_impact=failure_impact,
                dependency_count=dependency_count,
                static_coupling=static_coupling,
                runtime_centrality=runtime_centrality,
            ))

        scores.sort(key=lambda s: s.runtime_centrality, reverse=True)
        return scores

    def silently_critical(self, threshold: float = 0.7) -> List[RuntimeCentralityScore]:
        """Nodes with high runtime centrality but low static coupling.

        These are the hidden critical paths — not visible in static analysis.
        """
        all_scores = self.compute()
        return [
            s for s in all_scores
            if s.runtime_centrality >= threshold and s.static_coupling < 0.3
        ]

    def _find_node_id(self, tool: str) -> str:
        if self._graph is None:
            return tool
        for nid, node in self._graph.nodes.items():
            if node.type.name == "FILE":
                if tool.replace("_", "") in node.path.replace("_", "").replace("-", ""):
                    return nid
        return tool

    def _find_path(self, tool: str) -> str:
        if self._graph is None:
            return f"core/{tool}.py"
        for node in self._graph.nodes.values():
            if node.type.name == "FILE":
                if tool.replace("_", "") in node.path.replace("_", "").replace("-", ""):
                    return node.path
        return ""

    def _get_static_info(self, node_id: str) -> Dict[str, Any]:
        if self._graph is None or node_id not in self._graph.nodes:
            return {"dependency_count": 0, "coupling": 0.0}
        node = self._graph.nodes[node_id]
        metrics = getattr(node, "metrics", None) or {}
        coupling = getattr(node, "coupling_score", 0.0)
        deps = len(getattr(node, "dependencies", []))
        return {
            "dependency_count": deps,
            "coupling": coupling or 0.0,
        }
