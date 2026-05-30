"""F2 — ClusterManager: node cluster management and grouping.

Manages:
  - Node clusters (logical groups of nodes)
  - Cluster health aggregation
  - Cluster-level auto-remediation
  - Cross-cluster load balancing hints
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("emo_ai.control_plane.cluster_manager")


@dataclass
class Cluster:
    name: str
    node_ids: Set[str] = field(default_factory=set)
    labels: Dict[str, str] = field(default_factory=dict)
    created_at: float = 0.0
    health_status: str = "unknown"
    healthy_node_count: int = 0
    total_node_count: int = 0


class ClusterManager:
    """Manages logical node clusters and their health.

    Clusters group nodes by region, purpose, or other labels.
    The reconciler and scheduler use cluster info for smarter decisions.
    """

    def __init__(self):
        self._clusters: Dict[str, Cluster] = {}

    def create_cluster(self, name: str,
                       labels: Optional[Dict[str, str]] = None) -> Cluster:
        cluster = Cluster(
            name=name,
            labels=labels or {},
            created_at=time.time(),
        )
        self._clusters[name] = cluster
        logger.info("Cluster created: %s", name)
        return cluster

    def delete_cluster(self, name: str) -> bool:
        if name in self._clusters:
            del self._clusters[name]
            logger.info("Cluster deleted: %s", name)
            return True
        return False

    def add_node_to_cluster(self, cluster_name: str, node_id: str) -> bool:
        cluster = self._clusters.get(cluster_name)
        if not cluster:
            return False
        cluster.node_ids.add(node_id)
        return True

    def remove_node_from_cluster(self, cluster_name: str, node_id: str) -> bool:
        cluster = self._clusters.get(cluster_name)
        if not cluster:
            return False
        cluster.node_ids.discard(node_id)
        return True

    def get_cluster(self, name: str) -> Optional[Cluster]:
        return self._clusters.get(name)

    def list_clusters(self) -> List[str]:
        return list(self._clusters.keys())

    def clusters_for_node(self, node_id: str) -> List[Cluster]:
        return [c for c in self._clusters.values() if node_id in c.node_ids]

    def update_cluster_health(self, cluster_name: str,
                               healthy_nodes: int, total_nodes: int) -> None:
        cluster = self._clusters.get(cluster_name)
        if not cluster:
            return
        cluster.healthy_node_count = healthy_nodes
        cluster.total_node_count = total_nodes
        if total_nodes == 0:
            cluster.health_status = "empty"
        elif healthy_nodes == total_nodes:
            cluster.health_status = "healthy"
        elif healthy_nodes > 0:
            cluster.health_status = "degraded"
        else:
            cluster.health_status = "down"

    def recommend_node(self, cluster_name: str,
                       preferred_node_ids: Optional[List[str]] = None) -> Optional[str]:
        """Recommend a node in the cluster for workload placement."""
        cluster = self._clusters.get(cluster_name)
        if not cluster or not cluster.node_ids:
            return None
        candidates = list(cluster.node_ids)
        if preferred_node_ids:
            for nid in preferred_node_ids:
                if nid in candidates:
                    return nid
        return candidates[0]

    def cluster_summary(self) -> Dict[str, Any]:
        return {
            name: {
                "node_count": len(c.node_ids),
                "health": c.health_status,
                "labels": c.labels,
                "healthy": c.healthy_node_count,
                "total": c.total_node_count,
            }
            for name, c in self._clusters.items()
        }
