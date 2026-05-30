from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from .graph import CodeGraph, EdgeType, Node, NodeType


class CodeGraphQueryEngine:
    """Query interface for CodeGraph analysis.

    Supports dependency, architecture, and intelligence queries.
    """

    def __init__(self, graph: CodeGraph):
        self._graph = graph

    # ── Dependency Queries ────────────────────────────────────────

    def get_dependencies(self, file_path: str) -> List[Node]:
        """Direct dependencies (outgoing DEPENDS_ON edges)."""
        node = self._find_file_node(file_path)
        if node is None:
            return []
        return self._get_outgoing(node.id, EdgeType.DEPENDS_ON)

    def get_dependents(self, file_path: str) -> List[Node]:
        """Reverse dependents (incoming DEPENDS_ON edges)."""
        node = self._find_file_node(file_path)
        if node is None:
            return []
        return self._get_incoming(node.id, EdgeType.DEPENDS_ON)

    # ── Architecture Queries ──────────────────────────────────────

    def get_upstream(self, node_id: str) -> List[Node]:
        """All nodes reachable via outgoing edges (transitive)."""
        visited: Set[str] = set()
        self._dfs_forward(node_id, visited)
        return [self._graph.nodes[nid] for nid in visited if nid in self._graph.nodes]

    def get_downstream(self, node_id: str) -> List[Node]:
        """All nodes that depend on the given node (transitive)."""
        visited: Set[str] = set()
        self._dfs_backward(node_id, visited)
        return [self._graph.nodes[nid] for nid in visited if nid in self._graph.nodes]

    def get_execution_boundary(self, file_path: str) -> Dict[str, Any]:
        """Compute the execution boundary for a given file.

        Returns:
            - entry_points: files that depend on this file
            - exit_points: files this file depends on
            - isolated: whether the file has zero dependencies in either direction
        """
        node = self._find_file_node(file_path)
        if node is None:
            return {"entry_points": [], "exit_points": [], "isolated": True}

        deps = self.get_dependencies(file_path)
        dependents = self.get_dependents(file_path)

        return {
            "entry_points": [n.path for n in dependents],
            "exit_points": [n.path for n in deps],
            "isolated": len(deps) == 0 and len(dependents) == 0,
            "dependency_count": len(deps),
            "dependent_count": len(dependents),
        }

    # ── Intelligence Queries ──────────────────────────────────────

    def get_coupling_score(self, file_path: str) -> float:
        """Coupling score based on dependency + dependent ratio."""
        node = self._find_file_node(file_path)
        if node is None:
            return 0.0
        total = float(len(self._graph.nodes))
        if total == 0:
            return 0.0
        deps = len(self._graph.nodes) - len(self.get_dependencies(file_path))
        return deps / total

    def get_risk_profile(self, file_path: str) -> Dict[str, Any]:
        """Risk analysis for a given file."""
        node = self._find_file_node(file_path)
        if node is None:
            return {"risk_score": 0.0, "complexity_score": 0.0, "coupling": 0.0}

        return {
            "risk_score": node.risk_score or 0.0,
            "complexity_score": node.complexity_score or 0.0,
            "coupling": self.get_coupling_score(file_path),
            "dependency_count": len(node.dependencies),
            "dependent_count": len(node.reverse_dependencies),
        }

    def get_injection_graph(self, module_path: str) -> List[Dict[str, str]]:
        """DI injection edges for a given module."""
        node = self._find_file_node(module_path)
        if node is None:
            return []

        injections: List[Dict[str, str]] = []
        for edge in self._graph.sorted_edges():
            if edge.from_id == node.id and edge.type == EdgeType.INJECTS:
                target = self._graph.get_node(edge.to_id)
                injections.append({
                    "from": node.name,
                    "to": target.name if target else edge.to_id,
                    "weight": str(edge.weight),
                })
        return injections

    # ── Helpers ───────────────────────────────────────────────────

    def _find_file_node(self, path: str) -> Optional[Node]:
        for node in self._graph.nodes.values():
            if node.path == path and node.type == NodeType.FILE:
                return node
        return None

    def _get_outgoing(self, node_id: str, etype: EdgeType) -> List[Node]:
        result: List[Node] = []
        for edge in self._graph.edges:
            if edge.from_id == node_id and edge.type == etype:
                target = self._graph.get_node(edge.to_id)
                if target:
                    result.append(target)
        return result

    def _get_incoming(self, node_id: str, etype: EdgeType) -> List[Node]:
        result: List[Node] = []
        for edge in self._graph.edges:
            if edge.to_id == node_id and edge.type == etype:
                source = self._graph.get_node(edge.from_id)
                if source:
                    result.append(source)
        return result

    def _dfs_forward(self, node_id: str, visited: Set[str]) -> None:
        if node_id in visited:
            return
        visited.add(node_id)
        for edge in self._graph.edges:
            if edge.from_id == node_id and edge.to_id not in visited:
                self._dfs_forward(edge.to_id, visited)

    def _dfs_backward(self, node_id: str, visited: Set[str]) -> None:
        if node_id in visited:
            return
        visited.add(node_id)
        for edge in self._graph.edges:
            if edge.to_id == node_id and edge.from_id not in visited:
                self._dfs_backward(edge.from_id, visited)
