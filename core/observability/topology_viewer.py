"""F4 — TopologyViewer: worker/node/service topology visualization.

Provides a graph representation of all workers, nodes, services,
and their connections. Useful for understanding the system's
physical and logical layout.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("emo_ai.observability.topology")


@dataclass
class TopologyNode:
    node_id: str
    node_type: str  # "node", "worker", "service"
    label: str
    status: str = "unknown"
    properties: Dict[str, Any] = field(default_factory=dict)
    tags: Dict[str, str] = field(default_factory=dict)


@dataclass
class TopologyEdge:
    source_id: str
    target_id: str
    edge_type: str  # "hosts", "connects_to", "routes_to", "depends_on"
    label: str = ""
    properties: Dict[str, Any] = field(default_factory=dict)


class TopologyViewer:
    """Builds and maintains a topology graph of the system.

    Tracks:
      - Nodes (physical/virtual machines)
      - Workers (execution units on nodes)
      - Services (logical services)
      - Connections between them
    """

    def __init__(self):
        self._nodes: Dict[str, TopologyNode] = {}
        self._edges: List[TopologyEdge] = []
        self._last_updated: float = time.time()

    # ── Node Management ───────────────────────────────────────

    def add_node(self, node_id: str, label: str = "",
                 status: str = "unknown",
                 properties: Optional[Dict[str, Any]] = None,
                 tags: Optional[Dict[str, str]] = None) -> TopologyNode:
        node = TopologyNode(
            node_id=node_id,
            node_type="node",
            label=label or node_id,
            status=status,
            properties=properties or {},
            tags=tags or {},
        )
        self._nodes[node_id] = node
        self._last_updated = time.time()
        return node

    def add_worker(self, worker_id: str, node_id: str,
                   label: str = "", status: str = "unknown",
                   properties: Optional[Dict[str, Any]] = None,
                   tags: Optional[Dict[str, str]] = None) -> TopologyNode:
        worker = TopologyNode(
            node_id=worker_id,
            node_type="worker",
            label=label or worker_id,
            status=status,
            properties=properties or {},
            tags=tags or {},
        )
        self._nodes[worker_id] = worker
        self._add_edge(node_id, worker_id, "hosts",
                       f"Node {node_id} hosts worker {worker_id}")
        self._last_updated = time.time()
        return worker

    def add_service(self, service_id: str, label: str = "",
                    status: str = "unknown",
                    properties: Optional[Dict[str, Any]] = None,
                    tags: Optional[Dict[str, str]] = None) -> TopologyNode:
        if service_id in self._nodes:
            existing = self._nodes[service_id]
            existing.status = status
            if properties:
                existing.properties.update(properties)
            if tags:
                existing.tags.update(tags)
            return existing
        service = TopologyNode(
            node_id=service_id,
            node_type="service",
            label=label or service_id,
            status=status,
            properties=properties or {},
            tags=tags or {},
        )
        self._nodes[service_id] = service
        self._last_updated = time.time()
        return service

    def update_status(self, node_id: str, status: str) -> None:
        node = self._nodes.get(node_id)
        if node:
            node.status = status
            self._last_updated = time.time()

    def remove_node(self, node_id: str) -> None:
        self._nodes.pop(node_id, None)
        self._edges = [
            e for e in self._edges
            if e.source_id != node_id and e.target_id != node_id
        ]
        self._last_updated = time.time()

    # ── Edge Management ───────────────────────────────────────

    def connect(self, source_id: str, target_id: str,
                edge_type: str = "connects_to", label: str = "",
                properties: Optional[Dict[str, Any]] = None) -> TopologyEdge:
        edge = TopologyEdge(
            source_id=source_id,
            target_id=target_id,
            edge_type=edge_type,
            label=label,
            properties=properties or {},
        )
        self._edges.append(edge)
        self._last_updated = time.time()
        return edge

    def _add_edge(self, source_id: str, target_id: str,
                  edge_type: str, label: str = "") -> None:
        for e in self._edges:
            if e.source_id == source_id and e.target_id == target_id:
                return
        self._edges.append(TopologyEdge(
            source_id=source_id, target_id=target_id,
            edge_type=edge_type, label=label,
        ))

    # ── Query ─────────────────────────────────────────────────

    def get_node(self, node_id: str) -> Optional[TopologyNode]:
        return self._nodes.get(node_id)

    def nodes_by_type(self, node_type: str) -> List[TopologyNode]:
        return [n for n in self._nodes.values() if n.node_type == node_type]

    def nodes_by_status(self, status: str) -> List[TopologyNode]:
        return [n for n in self._nodes.values() if n.status == status]

    def workers_on_node(self, node_id: str) -> List[TopologyNode]:
        worker_ids = {
            e.target_id for e in self._edges
            if e.source_id == node_id and e.edge_type == "hosts"
        }
        return [self._nodes[wid] for wid in worker_ids if wid in self._nodes]

    def connections_from(self, node_id: str) -> List[TopologyEdge]:
        return [e for e in self._edges if e.source_id == node_id]

    def connections_to(self, node_id: str) -> List[TopologyEdge]:
        return [e for e in self._edges if e.target_id == node_id]

    # ── Export ─────────────────────────────────────────────────

    def to_graph(self) -> Dict[str, Any]:
        """Export as a graph (nodes + edges) for visualization."""
        return {
            "nodes": [
                {
                    "id": n.node_id,
                    "type": n.node_type,
                    "label": n.label,
                    "status": n.status,
                    "properties": n.properties,
                    "tags": n.tags,
                }
                for n in self._nodes.values()
            ],
            "edges": [
                {
                    "source": e.source_id,
                    "target": e.target_id,
                    "type": e.edge_type,
                    "label": e.label,
                }
                for e in self._edges
            ],
            "last_updated": self._last_updated,
        }

    def summary(self) -> Dict[str, Any]:
        nodes_by_type = defaultdict(list)
        for n in self._nodes.values():
            nodes_by_type[n.node_type].append(n.node_id)
        return {
            "total_nodes": len(self._nodes),
            "total_edges": len(self._edges),
            "by_type": {k: len(v) for k, v in nodes_by_type.items()},
            "nodes_by_status": {
                s: len(self.nodes_by_status(s))
                for s in set(n.status for n in self._nodes.values())
            },
            "last_updated": self._last_updated,
        }

    def clear(self) -> None:
        self._nodes.clear()
        self._edges.clear()
