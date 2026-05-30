from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from .graph import CodeGraph
from .serializer import edges_json, metadata_json, nodes_json, to_json


_CODEGRAPH_DIR = "artifacts/codegraph"


def save(
    graph: CodeGraph,
    output_dir: Optional[str] = None,
) -> str:
    """Stage 5 — Persist CodeGraph to disk.

    Writes:
        graph.json       — full graph
        nodes.json       — node index
        edges.json       — edge index
        metadata.json    — version + checksum

    Returns the output directory path.
    """
    out = Path(output_dir or _CODEGRAPH_DIR)
    out.mkdir(parents=True, exist_ok=True)

    _write(out / "graph.json", to_json(graph))
    _write(out / "nodes.json", nodes_json(graph))
    _write(out / "edges.json", edges_json(graph))
    _write(out / "metadata.json", metadata_json(graph))

    return str(out)


def load(path: str) -> CodeGraph:
    """Load a previously saved CodeGraph from graph.json."""
    graph_path = Path(path) / "graph.json"
    if not graph_path.exists():
        raise FileNotFoundError(f"CodeGraph not found at {graph_path}")

    with open(graph_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return _from_dict(data)


def _write(path: Path, content: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _from_dict(data: dict) -> CodeGraph:
    from .graph import Edge, EdgeType, Node, NodeType

    graph = CodeGraph(
        version=data.get("version", "v1"),
        checksum=data.get("checksum", ""),
        generated_at=data.get("generated_at"),
    )

    for nid, ndata in data.get("nodes", {}).items():
        graph.add_node(Node(
            id=ndata["id"],
            type=NodeType(ndata["type"]),
            name=ndata["name"],
            path=ndata["path"],
            metadata=ndata.get("metadata", {}),
            dependencies=ndata.get("dependencies", []),
            reverse_dependencies=ndata.get("reverse_dependencies", []),
            complexity_score=ndata.get("complexity_score"),
            risk_score=ndata.get("risk_score"),
        ))

    for edata in data.get("edges", []):
        graph.add_edge(Edge(
            from_id=edata["from"],
            to_id=edata["to"],
            type=EdgeType(edata["type"]),
            weight=edata.get("weight", 1.0),
            metadata=edata.get("metadata", {}),
        ))

    return graph
