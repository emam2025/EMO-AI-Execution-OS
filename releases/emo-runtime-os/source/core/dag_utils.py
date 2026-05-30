"""DAG algorithms — extracted from models/dag.py for architectural purity.

These functions operate on DependencyGraph using only its public API
(nodes, edges, predecessors, successors). They do NOT require access
to ExecutionCore or ExecutionRuntime.

Phase 3.7: Behavior extracted from models/dag.py to eliminate domain
leakage. DependencyGraph is now purely structural; all algorithms
live here and in ExecutionCore.
"""

from __future__ import annotations

from collections import deque
from typing import Dict, List

from .models.dag import DependencyGraph, PlanNode


def topo_sort(dag: DependencyGraph) -> List[PlanNode]:
    """Kahn's algorithm. Raises ValueError on cycle."""
    in_degree: Dict[str, int] = {nid: 0 for nid in dag.nodes}
    for e in dag.edges:
        if e.target_id in in_degree:
            in_degree[e.target_id] += 1

    queue = deque([nid for nid, deg in in_degree.items() if deg == 0])
    result: List[PlanNode] = []

    while queue:
        nid = queue.popleft()
        result.append(dag.nodes[nid])
        for e in dag.edges:
            if e.source_id == nid and e.target_id in in_degree:
                in_degree[e.target_id] -= 1
                if in_degree[e.target_id] == 0:
                    queue.append(e.target_id)

    if len(result) != len(dag.nodes):
        raise ValueError("Cycle detected in dependency graph")
    return result


def independent_branches(dag: DependencyGraph) -> List[List[PlanNode]]:
    """Find groups of nodes that can run in parallel."""
    topo = topo_sort(dag)
    depth: Dict[str, int] = {}
    for node in topo:
        preds = dag.predecessors(node.id)
        depth[node.id] = max((depth[p.id] for p in preds), default=0) + 1

    groups: Dict[int, List[PlanNode]] = {}
    for node in topo:
        d = depth[node.id]
        groups.setdefault(d, []).append(node)
    return [
        sorted(nodes, key=lambda n: n.id)
        for _, nodes in sorted(groups.items())
    ]


def validate(dag: DependencyGraph) -> List[str]:
    """Return list of validation errors (empty = valid)."""
    errors: List[str] = []
    for edge in dag.edges:
        if edge.source_id not in dag.nodes:
            errors.append(f"Edge source '{edge.source_id}' not in nodes")
        if edge.target_id not in dag.nodes:
            errors.append(f"Edge target '{edge.target_id}' not in nodes")
        if edge.source_id == edge.target_id:
            errors.append(f"Self-loop on '{edge.source_id}'")
    try:
        topo_sort(dag)
    except ValueError as e:
        errors.append(str(e))
    return errors
