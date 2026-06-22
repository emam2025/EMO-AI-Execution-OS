"""F4 — DAGVisualizer: DAG structure + execution path visualization backend.

Provides:
  - DAG structure in graph format (nodes + edges)
  - Execution path highlighting (which nodes ran, which failed)
  - Critical path analysis
  - Node status overlay (pending, running, completed, failed)

AD-004: DAGs exceeding DAG_VIZ_MAX_NODES get a truncated summary view
instead of full node/edge detail.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from core.models.dag import DependencyGraph, PlanNode

logger = logging.getLogger("emo_ai.observability.dag_viz")

DAG_VIZ_MAX_NODES = 500


class DAGVisualizer:
    """Visualization backend for DAG structures and execution paths.

    Converts DependencyGraph + execution status into a format
    suitable for rendering by a UI or CLI.
    """

    @staticmethod
    def graph_structure(dag: DependencyGraph) -> Dict[str, Any]:
        """Convert a DAG to a graph structure for visualization.

        AD-004: DAGs with more than DAG_VIZ_MAX_NODES nodes return a
        truncated summary with node_count, edge_count, and a limited
        sample rather than the full node/edge list.

        Returns:
            Dict with 'nodes' and 'edges' arrays (or truncated summary).
        """
        n_nodes = len(dag.nodes)
        if n_nodes > DAG_VIZ_MAX_NODES:
            logger.warning(
                "DAG has %d nodes, truncating to first %d for visualization",
                n_nodes, DAG_VIZ_MAX_NODES,
            )
            truncated = []
            for node in list(dag.nodes)[:DAG_VIZ_MAX_NODES]:
                truncated.append({
                    "id": node.id,
                    "label": node.label or node.id,
                    "tool": node.tool,
                    "type": node.node_type.value if hasattr(node, "node_type") else "task",
                    "status": "pending",
                })
            return {
                "nodes": truncated,
                "edges": [],
                "truncated": True,
                "total_node_count": n_nodes,
                "edge_count": sum(len(n.depends_on) for n in dag.nodes),
            }

        nodes = []
        for node in dag.nodes:
            nodes.append({
                "id": node.id,
                "label": node.label or node.id,
                "tool": node.tool,
                "type": node.node_type.value if hasattr(node, "node_type") else "task",
                "status": "pending",
            })

        edges = []
        for node in dag.nodes:
            for dep_id in node.depends_on:
                edges.append({
                    "source": dep_id,
                    "target": node.id,
                    "type": "dependency",
                })

        return {"nodes": nodes, "edges": edges}

    @staticmethod
    def execution_path(dag: DependencyGraph,
                       execution_status: Dict[str, str]) -> Dict[str, Any]:
        """Build the execution path with status overlays.

        Args:
            dag: The DAG that was executed.
            execution_status: Map of node_id → status string.

        Returns:
            Graph with status overlays and critical path.
        """
        graph = DAGVisualizer.graph_structure(dag)

        # Overlay execution status
        for node in graph["nodes"]:
            nid = node["id"]
            node["status"] = execution_status.get(nid, "pending")
            if node["status"] == "failed":
                node["error"] = True

        # Compute critical path (longest chain of completed nodes)
        critical_path = DAGVisualizer._critical_path(dag, execution_status)
        for node in graph["nodes"]:
            node["critical"] = node["id"] in critical_path

        graph["critical_path"] = critical_path
        return graph

    @staticmethod
    def _critical_path(dag: DependencyGraph,
                        execution_status: Dict[str, str]) -> List[str]:
        """Find the critical path through the DAG.

        Longest path from any root to any leaf where all nodes
        along the path are completed.
        """
        completed = {
            nid for nid, status in execution_status.items()
            if status == "completed"
        }

        memo: Dict[str, List[str]] = {}

        def longest_path(node_id: str) -> List[str]:
            if node_id in memo:
                return memo[node_id]
            if node_id not in completed:
                memo[node_id] = []
                return []
            node = dag.get_node(node_id)
            if not node or not node.depends_on:
                memo[node_id] = [node_id]
                return [node_id]

            best_path: List[str] = []
            for dep_id in node.depends_on:
                path = longest_path(dep_id)
                if len(path) > len(best_path):
                    best_path = path
            result = best_path + [node_id]
            memo[node_id] = result
            return result

        critical: List[str] = []
        for node in dag.nodes:
            path = longest_path(node.id)
            if len(path) > len(critical):
                critical = path
        return critical

    @staticmethod
    def timeline_view(dag: DependencyGraph,
                       node_timings: Dict[str, Dict[str, float]]) -> Dict[str, Any]:
        """Build a timeline view of node execution.

        Args:
            dag: The DAG.
            node_timings: Map of node_id → {started_at, completed_at, duration_ms}.

        Returns:
            Timeline visualization data.
        """
        items = []
        for node in dag.nodes:
            timing = node_timings.get(node.id, {})
            started = timing.get("started_at", 0.0)
            completed = timing.get("completed_at", 0.0)
            duration = timing.get("duration_ms", 0.0)

            items.append({
                "id": node.id,
                "label": node.label or node.id,
                "start": started,
                "end": completed,
                "duration_ms": duration,
                "dependencies": list(node.depends_on),
                "level": DAGVisualizer._node_level(dag, node.id),
            })

        return {
            "items": items,
            "total_duration_ms": max(
                (t.get("completed_at", 0) for t in node_timings.values()),
                default=0,
            ) - min(
                (t.get("started_at", time.time()) for t in node_timings.values()),
                default=0,
            ) * 1000 if node_timings else 0,
        }

    @staticmethod
    def _node_level(dag: DependencyGraph, node_id: str) -> int:
        """Compute the topological level of a node (0 = root)."""
        visited: set[str] = set()
        memo: Dict[str, int] = {}

        def level(nid: str) -> int:
            if nid in memo:
                return memo[nid]
            if nid in visited:
                return 0
            visited.add(nid)
            node = dag.get_node(nid)
            if not node or not node.depends_on:
                memo[nid] = 0
                return 0
            max_dep = max(level(d) for d in node.depends_on)
            memo[nid] = max_dep + 1
            return max_dep + 1

        return level(node_id)
