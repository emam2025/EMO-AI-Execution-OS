"""Phase 5 — Distributed Registry with peer discovery.

Extends the local ServiceRegistry with network-aware peer discovery.
Nodes can discover and communicate with remote peer registries.

Architecture:
  LocalRegistry ←→ PeerRegistry (syncs via HTTP)
       |
       v
  ServiceRegistry (in-memory)
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, List, Optional

from core.runtime.mesh.remote.transport import (
    RemoteTransportClient,
    RemoteTransportError,
)
from core.runtime.mesh.service_registry import (
    ServiceInstance,
    ServiceRegistry,
)

logger = logging.getLogger("emo_ai.mesh.remote.discovery")


class PeerNode:
    """Represents a known peer in the distributed mesh."""
    def __init__(self, node_id: str, host: str, port: int):
        self.node_id = node_id
        self.host = host
        self.port = port
        self.last_seen: float = time.time()
        self.status: str = "unknown"

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def __repr__(self):
        return f"PeerNode({self.node_id}, {self.host}:{self.port}, {self.status})"


class DistributedRegistry:
    """Registry that combines local services + discovered remote peers.

    Features:
      - Local service registration (delegates to ServiceRegistry)
      - Peer node discovery and tracking
      - Remote service lookup via peer transport
      - Periodic peer health checks
      - Peer gossip: discovered peers share their known peers
    """

    def __init__(
        self,
        local_registry: Optional[ServiceRegistry] = None,
        node_id: str = "",
    ):
        self._local = local_registry or ServiceRegistry()
        self._node_id = node_id
        self._peers: Dict[str, PeerNode] = {}
        self._lock = threading.Lock()

    @property
    def local(self) -> ServiceRegistry:
        return self._local

    @property
    def peers(self) -> Dict[str, PeerNode]:
        with self._lock:
            return dict(self._peers)

    def register_peer(self, node_id: str, host: str, port: int) -> PeerNode:
        """Register a peer node for discovery."""
        peer = PeerNode(node_id=node_id, host=host, port=port)
        with self._lock:
            self._peers[node_id] = peer
        logger.info("Peer registered: %s @ %s:%d", node_id, host, port)
        return peer

    def remove_peer(self, node_id: str) -> bool:
        """Remove a peer node."""
        with self._lock:
            if node_id in self._peers:
                del self._peers[node_id]
                return True
        return False

    def discover_remote(
        self,
        service: str,
        _exclude_local: bool = False,
    ) -> List[Dict[str, Any]]:
        """Discover services across all known peers.

        Queries each peer's registry for the given service.
        Returns list of discovered instance info dicts.
        """
        results: List[Dict[str, Any]] = []
        with self._lock:
            peers = dict(self._peers)

        for peer_id, peer in peers.items():
            try:
                client = RemoteTransportClient(peer.base_url)
                envelope = client.send_request(
                    MeshEnvelope(
                        service="registry",
                        method="discover",
                        payload={"service": service},
                    )
                )
                if envelope.payload.get("instances"):
                    for inst in envelope.payload["instances"]:
                        inst["peer_id"] = peer_id
                        results.append(inst)
            except Exception as e:
                logger.debug("Peer %s discover failed: %s", peer_id, e)

        return results

    def sync_peers(self) -> int:
        """Sync peer list with all known peers (gossip protocol).

        Returns the total number of unique peers after sync.
        """
        with self._lock:
            current_peers = dict(self._peers)

        discovered_nodes: Dict[str, PeerNode] = {}

        for peer_id, peer in current_peers.items():
            try:
                client = RemoteTransportClient(peer.base_url)
                envelope = client.send_request(
                    MeshEnvelope(
                        service="registry",
                        method="peers",
                        payload={"node_id": self._node_id},
                    )
                )
                remote_peers = envelope.payload.get("peers", [])
                for rp in remote_peers:
                    pid = rp.get("node_id")
                    if pid and pid != self._node_id and pid not in current_peers:
                        discovered_nodes[pid] = PeerNode(
                            node_id=pid,
                            host=rp.get("host", peer.host),
                            port=rp.get("port", peer.port),
                        )
            except Exception as e:
                logger.debug("Peer %s sync failed: %s", peer_id, e)

        with self._lock:
            for pid, pnode in discovered_nodes.items():
                if pid not in self._peers:
                    self._peers[pid] = pnode

        with self._lock:
            return len(self._peers)

    def check_peer_health(self) -> Dict[str, str]:
        """Check health of all known peers.

        Returns dict of {node_id: status}.
        """
        results: Dict[str, str] = {}
        with self._lock:
            peers = dict(self._peers)

        for peer_id, peer in peers.items():
            try:
                client = RemoteTransportClient(peer.base_url)
                alive = client.send_heartbeat(
                    MeshEnvelope(
                        msg_type="heartbeat",
                        service="_health",
                    )
                )
                status = "healthy" if alive else "unreachable"
            except Exception:
                status = "unreachable"

            results[peer_id] = status
            with self._lock:
                if peer_id in self._peers:
                    self._peers[peer_id].status = status
                    if status == "healthy":
                        self._peers[peer_id].last_seen = time.time()

        return results

    def announce(
        self,
        service: str,
        instance_id: str,
        host: str,
        port: int,
    ) -> int:
        """Announce this node's service to all known peers.

        Returns the number of peers successfully notified.
        """
        count = 0
        with self._lock:
            peers = dict(self._peers)

        for peer_id, peer in peers.items():
            try:
                client = RemoteTransportClient(peer.base_url)
                if client.register_remote(service, instance_id, host, port):
                    count += 1
            except Exception as e:
                logger.debug("Announce to %s failed: %s", peer_id, e)

        return count


# Import at bottom to avoid circular imports
from core.runtime.mesh.mesh_protocol import MeshEnvelope
