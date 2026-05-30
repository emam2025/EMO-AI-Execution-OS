"""
Graph Queries — relational traversal, impact analysis, failure patterns (LAW-6, LAW-11).

Operations:
  - find_failure_patterns: detect recurring FAILS_WITH edges for tool/error
  - trace_impact: return all nodes affected transitively from an entity
  - get_related_context: hybrid graph ↔ semantic embedding lookup
All scoped by tenant_id/project_id.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from releases.memory_os.core.memory.entity_extractor import EdgeType, EntityType
from releases.memory_os.core.memory.graph_store import GraphStore
from releases.memory_os.core.memory.semantic_index import SemanticIndex


class GraphQueries:
    """Relational query operations on the knowledge graph."""

    def __init__(self, graph_store: GraphStore):
        self._graph = graph_store

    def find_failure_patterns(
        self,
        tenant_id: str,
        project_id: str,
        tool_name: str = "",
        error_type: str = "",
        min_occurrences: int = 1,
    ) -> List[dict]:
        """Find recurring failure patterns in the graph.

        Searches for FAILS_WITH edges where source is a tool/function
        and target is an error node. Filters by tool_name or error_type.
        """
        if not tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        failures: List[dict] = []
        tool_nodes = self._graph.find_nodes_by_type(tenant_id, project_id, EntityType.TOOL.value)
        for tool in tool_nodes:
            if tool_name and tool_name.lower() not in tool["name"].lower():
                continue
            neighbors = self._graph.get_neighbors(
                tool["node_id"], tenant_id, project_id, depth=1,
                edge_type=EdgeType.FAILS_WITH.value,
            )
            for n in neighbors:
                if error_type and error_type.lower() not in n["name"].lower():
                    continue
                failures.append({
                    "tool": tool["name"],
                    "tool_id": tool["node_id"],
                    "error": n["name"],
                    "error_id": n["node_id"],
                    "error_type": n.get("entity_type", ""),
                })
        if min_occurrences > 1:
            from collections import Counter
            pair_counts = Counter((f["tool"], f["error"]) for f in failures)
            failures = [f for f in failures if pair_counts[(f["tool"], f["error"])] >= min_occurrences]
        return failures

    def trace_impact(
        self,
        entity_id: str,
        tenant_id: str,
        project_id: str,
        max_depth: int = 3,
    ) -> List[dict]:
        """Return all nodes transitively connected to the given entity."""
        if not tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        return self._graph.get_neighbors(entity_id, tenant_id, project_id, depth=max_depth)

    def get_related_context(
        self,
        entity_id: str,
        tenant_id: str,
        project_id: str,
        semantic_index: Optional[SemanticIndex] = None,
    ) -> dict:
        """Hybrid lookup: graph neighbors + semantic embedding context."""
        if not tenant_id:
            raise ValueError("tenant_id is required (LAW-6)")
        node = self._graph.get_node(entity_id, tenant_id)
        if not node:
            return {"node": None, "neighbors": [], "semantic_context": []}
        neighbors = self._graph.get_neighbors(entity_id, tenant_id, project_id, depth=2)
        semantic_context: List[dict] = []
        if semantic_index:
            all_nodes = [node] + neighbors
            for n in all_nodes:
                eid = n.get("embedding_id", "")
                if eid and eid in semantic_index._metadata:
                    meta = semantic_index._metadata.get(eid, {})
                    if meta.get("tenant_id") == tenant_id:
                        semantic_context.append(meta)
        return {
            "node": dict(node),
            "neighbors": neighbors,
            "semantic_context": semantic_context,
            "tenant_id": tenant_id,
        }
