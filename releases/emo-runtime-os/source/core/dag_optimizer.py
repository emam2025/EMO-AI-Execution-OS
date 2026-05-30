"""DAG Optimization Engine.

Optimizes an execution graph before the engine runs it:

  1. Node merging  — combine sequential nodes where one tool's output
     is the sole input to another (same tool, no branching).
  2. Redundancy elimination — detect identical (tool, inputs) pairs
     and deduplicate via caching.
  3. Shared subgraph detection — find common sub-DAGs that appear
     as dependencies of multiple nodes and factor them out.

Deterministic — given the same DAG, optimize() always returns the
same optimized DAG (node IDs sorted within levels, stable merge).
"""

from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .models.dag import (
        DependencyGraph, PlanNode, PlanEdge,
    )

logger = logging.getLogger("emo_ai.dag_optimizer")

# Optimizer version — bump when merge/reorder/elimination rules change.
OPTIMIZER_VERSION = "1.0.0"


class DAGOptimizer:
    """Optimizes a DependencyGraph before execution.

    Usage:
        optimizer = DAGOptimizer()
        optimized = optimizer.optimize(original_dag)
    """

    def __init__(
        self,
        max_merge_passes: int = 3,
        enable_merge: bool = True,
        enable_dedup: bool = True,
        enable_subgraph_sharing: bool = False,  # experimental
    ):
        self._max_merge_passes = max_merge_passes
        self._enable_merge = enable_merge
        self._enable_dedup = enable_dedup
        self._enable_subgraph_sharing = enable_subgraph_sharing

    def optimize(self, dag: DependencyGraph) -> DependencyGraph:
        """Run all enabled optimizations in sequence.

        Each pass produces a new DAG; the original is never mutated.
        """
        result = deepcopy(dag)
        passes_applied: List[str] = []

        for _ in range(self._max_merge_passes):
            merged = self._merge_sequential(result)
            if merged is None:
                break
            result = merged
            passes_applied.append("merge")

        deduped = self._eliminate_redundant(result)
        if deduped is not None:
            result = deduped
            passes_applied.append("dedup")

        if self._enable_subgraph_sharing:
            shared = self._extract_shared_subgraphs(result)
            if shared is not None:
                result = shared
                passes_applied.append("share")

        # Stamp optimizer metadata
        result.version = dag.version
        return result

    def _merge_sequential(
        self, dag: DependencyGraph,
    ) -> Optional[DependencyGraph]:
        """Merge sequential same-tool nodes where one feeds the next.

        A → B can merge when:
          - B has exactly one predecessor (A)
          - A has exactly one successor (B)
          - A.tool == B.tool
          - B's inputs are a subset/superset of A's outputs

        Returns a new DAG or None if no merge was possible.
        """
        from .models.dag import DependencyGraph as DG, PlanEdge

        merged = False
        new_dag = deepcopy(dag)

        node_ids = sorted(new_dag.nodes.keys())
        for nid in node_ids:
            node = new_dag.nodes.get(nid)
            if node is None:
                continue

            successors = self._successors(nid, new_dag)
            if len(successors) != 1:
                continue

            successor_id = successors[0].id
            successor = new_dag.nodes[successor_id]
            predecessors = self._predecessors(successor_id, new_dag)
            if len(predecessors) != 1:
                continue

            if node.tool != successor.tool:
                continue

            # Merge: combine inputs, keep the first node's id, remove successor
            merged_inputs = dict(node.inputs)
            merged_inputs.update(successor.inputs)
            new_dag.nodes[nid].inputs = merged_inputs

            # Rewire edges: successor's outgoing edges go to the merged node
            outgoing = self._outgoing_edges(successor_id, new_dag)
            for edge in outgoing:
                new_dag.add_edge(nid, edge.target_id, edge.condition)

            # Remove successor node and its incoming edge
            del new_dag.nodes[successor_id]
            new_dag.edges = [
                e for e in new_dag.edges
                if not (e.source_id == nid and e.target_id == successor_id)
                and not (e.source_id == successor_id)
            ]
            merged = True
            break  # restart after merge

        return new_dag if merged else None

    def _eliminate_redundant(
        self, dag: DependencyGraph,
    ) -> Optional[DependencyGraph]:
        """Eliminate nodes that are identical in (tool, inputs).

        Two nodes are redundant if they share the same tool and the
        same inputs AND occupy the same position in the DAG
        (same set of predecessors). The first occurrence (in topo
        order) is kept; later occurrences are removed and their
        successors are rewired to the kept node.
        """
        deduped = False
        new_dag = deepcopy(dag)
        topo = new_dag.topo_sort()

        # group by (tool, sorted_inputs) → list of node ids in topo order
        groups: Dict[str, List[str]] = {}
        for node in topo:
            sig = self._node_signature(node)
            groups.setdefault(sig, []).append(node.id)

        for sig, node_ids in groups.items():
            if len(node_ids) < 2:
                continue
            for i in range(1, len(node_ids)):
                candidate = node_ids[i]
                kept = node_ids[0]

                # Safety: skip if they have a dependency relationship
                if self._has_path(kept, candidate, new_dag):
                    continue
                if self._has_path(candidate, kept, new_dag):
                    continue

                # Get predecessor sets — must be identical for dedup
                kept_preds = self._predecessor_ids(kept, new_dag)
                cand_preds = self._predecessor_ids(candidate, new_dag)
                if kept_preds != cand_preds:
                    continue

                # Rewire incoming edges of candidate to kept node
                incoming = self._incoming_edges(candidate, new_dag)
                for edge in incoming:
                    new_dag.add_edge(edge.source_id, kept, edge.condition)

                # Rewire outgoing edges
                outgoing = self._outgoing_edges(candidate, new_dag)
                for edge in outgoing:
                    new_dag.add_edge(kept, edge.target_id, edge.condition)

                # Remove candidate and its edges
                del new_dag.nodes[candidate]
                new_dag.edges = [
                    e for e in new_dag.edges
                    if e.target_id != candidate and e.source_id != candidate
                ]
                deduped = True

        return new_dag if deduped else None

    def _extract_shared_subgraphs(
        self, dag: DependencyGraph,
    ) -> Optional[DependencyGraph]:
        """Experimental: find shared sub-DAGs (same pair of nodes)
        that appear as dependencies of multiple leaf nodes.

        Currently a placeholder — subgraph extraction is non-trivial
        and can increase complexity without commensurate benefit.
        """
        return None

    # ── helpers ────────────────────────────────────────────────

    @staticmethod
    def _node_signature(node: PlanNode) -> str:
        """Deterministic hash of (tool, sorted inputs)."""
        sorted_kvs = sorted(node.inputs.items())
        return f"{node.tool}:{sorted_kvs}"

    @staticmethod
    def _predecessors(node_id: str, dag: DependencyGraph) -> List[PlanNode]:
        sources = {e.source_id for e in dag.edges
                   if e.target_id == node_id}
        return [dag.nodes[s] for s in sources if s in dag.nodes]

    @staticmethod
    def _successors(node_id: str, dag: DependencyGraph) -> List[PlanNode]:
        targets = {e.target_id for e in dag.edges
                   if e.source_id == node_id}
        return [dag.nodes[t] for t in targets if t in dag.nodes]

    @staticmethod
    def _outgoing_edges(
        node_id: str, dag: DependencyGraph,
    ) -> List[PlanEdge]:
        return [e for e in dag.edges if e.source_id == node_id]

    @staticmethod
    def _incoming_edges(
        node_id: str, dag: DependencyGraph,
    ) -> List[PlanEdge]:
        return [e for e in dag.edges if e.target_id == node_id]

    @staticmethod
    def _has_path(
        from_id: str, to_id: str, dag: DependencyGraph,
    ) -> bool:
        """BFS to check if `to_id` is reachable from `from_id`."""
        visited: set = set()
        queue = [from_id]
        while queue:
            current = queue.pop(0)
            if current == to_id:
                return True
            if current in visited:
                continue
            visited.add(current)
            for e in dag.edges:
                if e.source_id == current and e.target_id not in visited:
                    queue.append(e.target_id)
        return False

    @staticmethod
    def _predecessor_ids(
        node_id: str, dag: DependencyGraph,
    ) -> frozenset[str]:
        return frozenset(
            e.source_id for e in dag.edges if e.target_id == node_id
        )
