"""3.8.2.3 — Runtime Drift Detector.

Compares static CodeGraph vs RuntimeExecutionGraph to detect:
  - hidden runtime dependencies
  - boundary violations
  - coupling explosions

This is the runtime ↔ static reconciliation engine (LAW 18).
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from core.codegraph.drift.drift_classifier import DriftClassifier, DriftEvent, DriftReport
from core.codegraph.drift.runtime_graph_builder import RuntimeExecutionGraph
from core.codegraph.graph import CodeGraph


@dataclass
class RuntimeDriftResult:
    hidden_dependencies: List[DriftEvent] = field(default_factory=list)
    boundary_violations: List[DriftEvent] = field(default_factory=list)
    coupling_explosions: List[DriftEvent] = field(default_factory=list)
    report: Optional[DriftReport] = None

    @property
    def total_events(self) -> int:
        return (len(self.hidden_dependencies)
                + len(self.boundary_violations)
                + len(self.coupling_explosions))

    @property
    def is_blocking(self) -> bool:
        return self.report is not None and self.report.is_blocking

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hidden_dependencies": [
                {"severity": e.severity, "message": e.message}
                for e in self.hidden_dependencies
            ],
            "boundary_violations": [
                {"severity": e.severity, "message": e.message}
                for e in self.boundary_violations
            ],
            "coupling_explosions": [
                {"severity": e.severity, "message": e.message,
                 "delta": round(e.delta, 4)}
                for e in self.coupling_explosions
            ],
            "total_events": self.total_events,
            "is_blocking": self.is_blocking,
        }


class RuntimeDriftDetector:
    """Detects drift between static CodeGraph and runtime execution graph.

    Usage:
        detector = RuntimeDriftDetector(static_graph, runtime_graph)
        result = detector.detect()
        if result.is_blocking:
            # architecture is actively degrading
    """

    ALLOWED_BOUNDARIES = {
        "interfaces": {"core.interfaces"},
        "adapters": {"core.adapters"},
        "models": {"core.models"},
    }

    def __init__(
        self,
        static_graph: Optional[CodeGraph] = None,
        runtime_graph: Optional[RuntimeExecutionGraph] = None,
    ):
        self._static = static_graph
        self._runtime = runtime_graph
        self._classifier = DriftClassifier()

    def detect(
        self,
        static_graph: Optional[CodeGraph] = None,
        runtime_graph: Optional[RuntimeExecutionGraph] = None,
    ) -> RuntimeDriftResult:
        static = static_graph or self._static
        runtime = runtime_graph or self._runtime

        if static is None or runtime is None:
            return RuntimeDriftResult()

        static_tools = self._extract_static_tools(static)
        runtime_tools = self._extract_runtime_tools(runtime)

        result = RuntimeDriftResult()

        for tool in runtime_tools:
            is_hidden = tool not in static_tools
            is_boundary = self._is_boundary_violation(tool, runtime)
            static_coupling = static_tools.get(tool, 0.0)
            runtime_coupling = self._estimate_runtime_coupling(tool, runtime)

            event = self._classifier.classify_node_drift(
                tool=tool,
                static_coupling=static_coupling,
                runtime_coupling=runtime_coupling,
                is_hidden=is_hidden,
                is_boundary=is_boundary,
            )

            if is_hidden:
                result.hidden_dependencies.append(event)
            elif is_boundary:
                result.boundary_violations.append(event)
            elif event.severity != "INFO":
                result.coupling_explosions.append(event)

        all_events = (
            result.hidden_dependencies
            + result.boundary_violations
            + result.coupling_explosions
        )
        result.report = self._classifier.classify_session(all_events)
        return result

    def _extract_static_tools(self, graph: CodeGraph) -> Dict[str, float]:
        tools: Dict[str, float] = {}
        for _nid, node in graph.nodes.items():
            if node.type.name == "FILE":
                name = getattr(node, "name", node.path.split("/")[-1])
                coupling = getattr(node, "coupling_score", 0.0) or 0.0
                tools[name.replace(".py", "")] = coupling
                tools[node.path] = coupling
        return tools

    def _extract_runtime_tools(self, graph: RuntimeExecutionGraph) -> Set[str]:
        tools: Set[str] = set()
        for _eid, node in graph.nodes.items():
            if node.tool:
                tools.add(node.tool)
        return tools

    def _is_boundary_violation(
        self,
        tool: str,
        runtime: RuntimeExecutionGraph,
    ) -> bool:
        for node in runtime.nodes.values():
            if node.tool != tool:
                continue
            if not node.dependencies:
                continue
            for dep in node.dependencies:
                if self._crosses_boundary(tool, dep):
                    return True
        return False

    def _crosses_boundary(self, tool: str, dependency: str) -> bool:
        allowed = {"interfaces", "adapters", "models"}
        tool_prefix = tool.split(".")[0] if "." in tool else tool
        dep_prefix = dependency.split(".")[0] if "." in dependency else dependency

        if tool_prefix in allowed and dep_prefix not in allowed:
            return True
        return False

    @staticmethod
    def _estimate_runtime_coupling(tool: str, runtime: RuntimeExecutionGraph) -> float:
        related = 0
        total = len(runtime.nodes)
        if total == 0:
            return 0.0
        for node in runtime.nodes.values():
            if node.tool == tool:
                continue
            if tool in node.dependencies or node.tool in node.dependencies:
                related += 1
        return related / total
