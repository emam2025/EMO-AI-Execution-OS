"""Phase 5 — MeshNode: a single node in the distributed runtime mesh.

Each MeshNode combines:
  - Local ServiceMesh (handlers + routing)
  - HTTP transport server (accepts remote requests)
  - HTTP transport client (sends remote requests)
  - DistributedRegistry (peer discovery + sync)

Architecture:
  ┌─────────────────────────────────┐
  │           MeshNode               │
  │  ┌───────────┐  ┌────────────┐  │
  │  │  Service  │  │  Remote    │  │
  │  │  Mesh     │◄─┤  Transport │  │
  │  │ (local)   │  │  Server    │  │
  │  └─────┬─────┘  └────────────┘  │
  │        │                        │
  │  ┌─────▼─────┐  ┌────────────┐  │
  │  │  Service  │  │ Distributed│  │
  │  │  Registry │◄─┤ Registry   │  │
  │  └───────────┘  └────────────┘  │
  └─────────────────────────────────┘
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Callable, Dict, List, Optional

from core.runtime.mesh.mesh_protocol import MeshEnvelope, MeshProtocol
from core.runtime.mesh.remote.discovery import DistributedRegistry, PeerNode
from core.runtime.mesh.remote.serialization import envelope_to_dict, dict_to_envelope
from core.runtime.mesh.remote.transport import (
    RemoteTransportClient,
    RemoteTransportServer,
)
from core.runtime.mesh.service_mesh import ServiceMesh
from core.runtime.mesh.service_registry import ServiceInstance, ServiceRegistry

logger = logging.getLogger("emo_ai.mesh.node")


class MeshNode:
    """A single node in the distributed runtime mesh.

    Each node can:
      - Register local service handlers
      - Accept remote dispatch requests via HTTP
      - Discover services from peer registries
      - Announce its services to peers
      - Forward requests to remote nodes when no local handler exists

    Usage:
        node = MeshNode(node_id="worker-1", host="127.0.0.1", port=9001)
        node.register_handler("scheduler", "schedule", my_handler)
        node.add_peer("worker-2", "127.0.0.1", 9002)
        node.start()
        # ...
        node.shutdown()
    """

    def __init__(
        self,
        node_id: str = "",
        host: str = "127.0.0.1",
        port: int = 0,
        mesh: Optional[ServiceMesh] = None,
        registry: Optional[ServiceRegistry] = None,
    ):
        self._node_id = node_id or uuid.uuid4().hex[:12]
        self._host = host
        self._port = port
        self._mesh = mesh or ServiceMesh(registry=registry or ServiceRegistry())
        self._dist_registry = DistributedRegistry(
            local_registry=self._mesh.registry,
            node_id=self._node_id,
        )
        self._server: Optional[RemoteTransportServer] = None
        self._started = False

    @property
    def node_id(self) -> str:
        return self._node_id

    @property
    def host(self) -> str:
        return self._host

    @property
    def port(self) -> int:
        if self._server:
            return self._server.port
        return self._port

    @property
    def mesh(self) -> ServiceMesh:
        return self._mesh

    @property
    def registry(self) -> ServiceRegistry:
        return self._mesh.registry

    @property
    def distributed_registry(self) -> DistributedRegistry:
        return self._dist_registry

    def register_handler(self, service: str, method: str, handler: Callable) -> None:
        """Register a local service handler."""
        self._mesh.register_local_handler(service, method, handler)

    def add_peer(self, node_id: str, host: str, port: int) -> PeerNode:
        """Add a peer node for distributed discovery."""
        return self._dist_registry.register_peer(node_id, host, port)

    def remove_peer(self, node_id: str) -> bool:
        """Remove a peer node."""
        return self._dist_registry.remove_peer(node_id)

    def start(self) -> None:
        """Start the node: HTTP server + peer sync."""
        if self._started:
            return

        self._server = RemoteTransportServer(
            host=self._host,
            port=self._port,
            dispatch_fn=self._handle_remote_request,
            registry=self._mesh.registry,
        )
        self._server.start()

        if self._port == 0:
            self._port = self._server.port

        self._started = True
        logger.info(
            "MeshNode %s started on %s:%d",
            self._node_id, self._host, self.port,
        )

    def shutdown(self) -> None:
        """Shutdown the node."""
        if not self._started:
            return
        if self._server:
            self._server.shutdown()
        self._started = False
        logger.info("MeshNode %s stopped", self._node_id)

    def announce_to_peers(self) -> int:
        """Announce this node's services to all known peers.

        Returns the number of peers successfully notified.
        """
        count = 0
        for service_name in self._mesh.registry.all_services():
            instances = self._mesh.registry.discover(service_name)
            if instances:
                inst = instances[0]
                count += self._dist_registry.announce(
                    service=service_name,
                    instance_id=inst.instance_id,
                    host=self._host,
                    port=self.port,
                )
        return count

    def call_remote(
        self,
        service: str,
        method: str,
        payload: Dict[str, Any],
        peer_id: str,
    ) -> Dict[str, Any]:
        """Call a service method on a specific peer node."""
        peer = self._dist_registry.peers.get(peer_id)
        if peer is None:
            raise ValueError(f"Unknown peer: {peer_id}")

        client = RemoteTransportClient(peer.base_url)
        request = MeshProtocol.create_request(service, method, payload)
        response = client.send_request(request)
        return response.payload

    def discover_remote(self, service: str) -> List[Dict[str, Any]]:
        """Discover a service across all known peers."""
        return self._dist_registry.discover_remote(service)

    def _handle_remote_request(self, envelope: MeshEnvelope) -> MeshEnvelope:
        """Handle an incoming remote request by dispatching locally."""
        try:
            result = self._mesh.call(
                service=envelope.service,
                method=envelope.method,
                payload=envelope.payload,
                trace_id=envelope.trace_id,
            )
            return MeshProtocol.create_response(envelope, result)
        except Exception as e:
            return MeshProtocol.create_error(envelope, str(e))
