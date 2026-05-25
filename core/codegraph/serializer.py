from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from .graph import CodeGraph, EdgeType, Node, NodeType


def to_json(graph: CodeGraph, indent: int = 2) -> str:
    """Serialize the full CodeGraph to JSON."""
    return json.dumps(graph.to_dict(), indent=indent, ensure_ascii=False)


def to_llm_context(
    graph: CodeGraph,
    target_path: Optional[str] = None,
    max_nodes: int = 50,
) -> str:
    """Render a deterministic LLM-compressed context view.

    Rules:
    - stable ordering
    - no duplicates
    - sorted dependencies
    """
    lines: List[str] = []
    lines.append("# CodeGraph — LLM Context View")
    lines.append(f"version: {graph.version}  checksum: {graph.checksum}")
    lines.append("")

    nodes = sorted(graph.nodes.values(), key=lambda n: n.path)

    if target_path:
        nodes = [n for n in nodes if target_path in n.path]

    for node in nodes[:max_nodes]:
        lines.append("[FILE]")
        lines.append(f"path: {node.path}")
        lines.append(f"type: {_node_type_label(node)}")

        # Imports (outgoing deps)
        deps = _get_outgoing_deps(graph, node, EdgeType.IMPORTS)
        if deps:
            lines.append("")
            lines.append("IMPORTS:")
            for dep in deps:
                lines.append(f"- {dep}")

        # Depends on
        depends = _get_outgoing_deps(graph, node, EdgeType.DEPENDS_ON)
        if depends:
            lines.append("")
            lines.append("DEPENDS_ON:")
            for dep in depends:
                lines.append(f"- {dep}")

        # Calls
        calls = _get_outgoing_deps(graph, node, EdgeType.CALLS)
        if calls:
            lines.append("")
            lines.append("CALLS:")
            for call in calls:
                lines.append(f"- {call}")

        # Role
        role = _classify_role(node)
        lines.append("")
        lines.append(f"ROLE:")
        lines.append(role)

        # Risk score
        if node.risk_score is not None:
            level = "LOW" if node.risk_score < 0.3 else "MEDIUM" if node.risk_score < 0.6 else "HIGH"
            lines.append("")
            lines.append(f"RISK:")
            lines.append(f"{level} COUPLING ({node.risk_score:.2f})")

        lines.append("")

    return "\n".join(lines)


def nodes_json(graph: CodeGraph) -> str:
    return json.dumps(
        [
            {"id": n.id, "type": n.type.value, "name": n.name, "path": n.path}
            for n in sorted(graph.nodes.values(), key=lambda x: x.id)
        ],
        indent=2,
    )


def edges_json(graph: CodeGraph) -> str:
    return json.dumps(
        [
            {"from": e.from_id, "to": e.to_id, "type": e.type.value, "weight": e.weight}
            for e in graph.sorted_edges()
        ],
        indent=2,
    )


def metadata_json(graph: CodeGraph) -> str:
    return json.dumps(
        {
            "version": graph.version,
            "checksum": graph.checksum,
            "generated_at": graph.generated_at,
            "node_count": len(graph.nodes),
            "edge_count": len(graph.edges),
        },
        indent=2,
    )


# ── Helpers ──────────────────────────────────────────────────────────────────


def _get_outgoing_deps(graph: CodeGraph, node: Node, etype: EdgeType) -> List[str]:
    result: List[str] = []
    for edge in graph.sorted_edges():
        if edge.from_id == node.id and edge.type == etype:
            target = graph.get_node(edge.to_id)
            if target:
                result.append(target.name)
    return result


def _node_type_label(node: Node) -> str:
    mapping = {
        NodeType.FILE: "source",
        NodeType.MODULE: "module",
        NodeType.CLASS: "class",
        NodeType.FUNCTION: "function",
        NodeType.INTERFACE: "interface",
        NodeType.MODEL: "model",
    }
    return mapping.get(node.type, "unknown")


def _classify_role(node: Node) -> str:
    path = node.path.lower()
    if "interface" in path or node.type == NodeType.INTERFACE:
        return "Interface Definition"
    if "model" in path or node.type == NodeType.MODEL:
        return "Domain Model"
    if "adapter" in path:
        return "Adapter Layer"
    if "test_" in path or "/tests/" in path:
        return "Test"
    if "execution_engine" in path:
        return "Execution Kernel (Control Plane)"
    if "orchestrator" in path:
        return "Orchestration Layer"
    if "composition" in path:
        return "Bootstrap / Dependency Wiring"
    if "contract" in path or "governance" in path:
        return "Governance Layer"
    return "Runtime Module"
