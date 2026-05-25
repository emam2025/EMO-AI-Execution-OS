from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set


class NodeType(Enum):
    FILE = "FILE"
    MODULE = "MODULE"
    CLASS = "CLASS"
    FUNCTION = "FUNCTION"
    INTERFACE = "INTERFACE"
    MODEL = "MODEL"


class EdgeType(Enum):
    IMPORTS = "IMPORTS"
    CALLS = "CALLS"
    IMPLEMENTS = "IMPLEMENTS"
    DEPENDS_ON = "DEPENDS_ON"
    INJECTS = "INJECTS"
    OWNS_STATE = "OWNS_STATE"


@dataclass
class Node:
    id: str
    type: NodeType
    name: str
    path: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)
    reverse_dependencies: List[str] = field(default_factory=list)
    complexity_score: Optional[float] = None
    risk_score: Optional[float] = None


@dataclass(unsafe_hash=True)
class Edge:
    from_id: str
    to_id: str
    type: EdgeType
    weight: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict, compare=False, hash=False)

    def sort_key(self) -> tuple:
        return (self.from_id, self.to_id, self.type.value)


@dataclass
class CodeGraph:
    nodes: Dict[str, Node] = field(default_factory=dict)
    edges: Set[Edge] = field(default_factory=set)
    version: str = "v1"
    checksum: str = ""
    generated_at: Optional[float] = None

    def add_node(self, node: Node) -> None:
        self.nodes[node.id] = node

    def add_edge(self, edge: Edge) -> None:
        self.edges.add(edge)

    def get_node(self, node_id: str) -> Optional[Node]:
        return self.nodes.get(node_id)

    def has_node(self, node_id: str) -> bool:
        return node_id in self.nodes

    def sorted_edges(self) -> List[Edge]:
        return sorted(self.edges, key=lambda e: e.sort_key())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "checksum": self.checksum,
            "generated_at": self.generated_at,
            "nodes": {
                nid: {
                    "id": n.id,
                    "type": n.type.value,
                    "name": n.name,
                    "path": n.path,
                    "metadata": n.metadata,
                    "dependencies": sorted(n.dependencies),
                    "reverse_dependencies": sorted(n.reverse_dependencies),
                    "complexity_score": n.complexity_score,
                    "risk_score": n.risk_score,
                }
                for nid, n in sorted(self.nodes.items())
            },
            "edges": [
                {
                    "from": e.from_id,
                    "to": e.to_id,
                    "type": e.type.value,
                    "weight": e.weight,
                    "metadata": e.metadata,
                }
                for e in self.sorted_edges()
            ],
        }
