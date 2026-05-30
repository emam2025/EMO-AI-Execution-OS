"""Phase G3 — DAG Topology Optimizer.  # LAW-14 RULE-1

Concrete implementation of IDAGTopologyOptimizer.

Detects redundant nodes, merges parallel paths, rebalances dependencies,
and validates DAG integrity. All methods are deterministic (RULE 1).

Ref: Canon LAW 14 (Resource Governance), RULE 1 (Determinism)
Ref: artifacts/design/g3/protocols/01_optimizer_protocols.py
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("emo_ai.optimizer.dag_topology_optimizer")


class DAGTopologyOptimizer:  # LAW-14 RULE-1
    """Analyses DAG structure for optimisation opportunities.

    All methods are deterministic — same DAG always produces same results.
    """

    def detect_redundant_nodes(  # LAW-14
        self,
        nodes: List[Dict[str, Any]],
        dag: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        redundant: List[Dict[str, Any]] = []

        referenced: Set[str] = set()
        for edge in dag:
            if isinstance(edge, dict):
                referenced.add(edge.get("from", ""))
                referenced.add(edge.get("to", ""))

        for node in nodes:
            if isinstance(node, dict):
                nid = node.get("node_id", "")
                if nid and nid not in referenced:
                    redundant.append({
                        "node_id": nid,
                        "reason": "orphan_node",
                        "estimated_waste": node.get("estimated_cost", 0.0),
                    })

        node_ids = {n.get("node_id") for n in nodes if isinstance(n, dict)}
        for edge in dag:
            if isinstance(edge, dict):
                frm = edge.get("from", "")
                to = edge.get("to", "")
                if frm not in node_ids or to not in node_ids:
                    redundant.append({
                        "node_id": f"{frm}->{to}",
                        "reason": "dangling_edge",
                        "estimated_waste": 0.0,
                    })

        return redundant

    def merge_parallel_paths(  # LAW-14
        self,
        nodes: List[Dict[str, Any]],
        dag: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        merge_candidates: List[Dict[str, Any]] = []
        predecessors: Dict[str, List[str]] = {}
        successors: Dict[str, List[str]] = {}

        for edge in dag:
            if isinstance(edge, dict):
                frm = edge.get("from", "")
                to = edge.get("to", "")
                predecessors.setdefault(to, []).append(frm)
                successors.setdefault(frm, []).append(to)

        for node_id, preds in predecessors.items():
            if len(preds) >= 2:
                merge_candidates.append({
                    "source_node": preds[0],
                    "target_node": node_id,
                    "merge_strategy": "join_predecessors",
                    "cost_savings": (len(preds) - 1) * 0.05,
                })

        return merge_candidates

    def rebalance_dependencies(  # RULE-1
        self,
        nodes: List[Dict[str, Any]],
        dag: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        suggestions: List[Dict[str, Any]] = []
        node_tools: Dict[str, str] = {}

        for node in nodes:
            if isinstance(node, dict):
                nid = node.get("node_id", "")
                tool = node.get("tool_name", "")
                if nid:
                    node_tools[nid] = tool

        predecessors: Dict[str, List[str]] = {}
        for edge in dag:
            if isinstance(edge, dict):
                frm = edge.get("from", "")
                to = edge.get("to", "")
                predecessors.setdefault(to, []).append(frm)

        for nid, preds in sorted(predecessors.items()):
            if len(preds) > 3:
                suggestions.append({
                    "node_id": nid,
                    "current_deps": preds,
                    "suggested_deps": preds[:2],
                    "rationale": f"Reduce {len(preds)} deps to 2 for parallelism",
                })

        return suggestions

    def validate_dag_integrity(  # LAW-14
        self,
        nodes: List[Dict[str, Any]],
        dag: List[Dict[str, Any]],
    ) -> bool:
        node_ids = {n.get("node_id") for n in nodes if isinstance(n, dict)}
        if not node_ids:
            return False

        for edge in dag:
            if isinstance(edge, dict):
                if edge.get("from") not in node_ids:
                    return False
                if edge.get("to") not in node_ids:
                    return False

        visited: Set[str] = set()
        path: Set[str] = set()

        def has_cycle(nid: str) -> bool:
            if nid in path:
                return True
            if nid in visited:
                return False
            path.add(nid)
            visited.add(nid)
            for edge in dag:
                if isinstance(edge, dict) and edge.get("from") == nid:
                    if has_cycle(edge.get("to", "")):
                        return True
            path.discard(nid)
            return False

        for nid in node_ids:
            if has_cycle(nid):
                return False

        return True
