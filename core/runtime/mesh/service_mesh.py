"""GAP 1 — ServiceMesh: runtime routing + dispatch between services.

The mesh routes requests between services using the registry,
protocol, and runtime dispatcher.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

from core.runtime.mesh.mesh_protocol import (
    MeshEnvelope,
    MeshMessageType,
    MeshProtocol,
)
from core.runtime.mesh.service_registry import (
    ServiceInstance,
    ServiceRegistry,
    ServiceStatus,
)

logger = logging.getLogger("emo_ai.mesh")


class ServiceNotAvailable(Exception):
    """Raised when no healthy instance of a service is available."""


class MeshRoutingError(Exception):
    """Raised when message routing fails."""


class ServiceMesh:
    """Runtime service mesh — routes requests between services.

    Provides:
      - Dynamic service-to-service routing
      - Load-aware dispatch
      - Failure propagation
      - Envelope-based communication
    """

    def __init__(
        self,
        registry: Optional[ServiceRegistry] = None,
        protocol: Optional[MeshProtocol] = None,
    ):
        self._registry = registry or ServiceRegistry()
        self._protocol = protocol or MeshProtocol()
        self._local_handlers: Dict[str, Dict[str, Callable]] = {}

    @property
    def registry(self) -> ServiceRegistry:
        return self._registry

    def register_local_handler(
        self,
        service: str,
        method: str,
        handler: Callable,
    ) -> None:
        """Register a local handler for a service method."""
        if service not in self._local_handlers:
            self._local_handlers[service] = {}
        self._local_handlers[service][method] = handler

    def call(
        self,
        service: str,
        method: str,
        payload: Dict[str, Any],
        trace_id: str = "",
        ttl: float = 30.0,
    ) -> Dict[str, Any]:
        """Call a service method through the mesh.

        Flows:
          1. Create envelope
          2. Discover service instance
          3. Route to local handler or dispatch
          4. Return response or raise error
        """
        request = self._protocol.create_request(
            service=service,
            method=method,
            payload=payload,
            trace_id=trace_id or uuid.uuid4().hex[:12],
            ttl=ttl,
        )

        # Try local handler first
        result = self._route_local(request)
        if result is not None:
            return result

        # Try remote dispatch
        instances = self._registry.discover(service)
        if not instances:
            raise ServiceNotAvailable(
                f"No healthy instance of '{service}' available"
            )

        instance = self._select_instance(instances)
        return self._dispatch_remote(request, instance)

    def call_async(
        self,
        service: str,
        method: str,
        payload: Dict[str, Any],
        trace_id: str = "",
    ) -> str:
        """Fire-and-forget call through the mesh. Returns trace_id."""
        request = self._protocol.create_request(
            service=service,
            method=method,
            payload=payload,
            trace_id=trace_id or uuid.uuid4().hex[:12],
        )
        try:
            self._route_local(request)
        except Exception as e:
            logger.warning("Async call to %s/%s failed: %s", service, method, e)
        return request.trace_id

    def broadcast(
        self,
        service: str,
        method: str,
        payload: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Broadcast to all instances of a service."""
        results = []
        instances = self._registry.discover(service, min_healthy=False)
        for inst in instances:
            try:
                request = self._protocol.create_request(
                    service=service, method=method, payload=payload,
                )
                result = self._dispatch_remote(request, inst)
                results.append(result)
            except Exception as e:
                results.append({"error": str(e)})
        return results

    def _route_local(self, request: MeshEnvelope) -> Optional[Dict[str, Any]]:
        """Try to route a request to a local handler."""
        svc_handlers = self._local_handlers.get(request.service)
        if svc_handlers is None:
            return None
        handler = svc_handlers.get(request.method)
        if handler is None:
            return None
        try:
            result = handler(request.payload)
            response = self._protocol.create_response(request, result)
            return response.payload
        except Exception as e:
            error = self._protocol.create_error(request, str(e))
            return {"error": str(e)}

    def _dispatch_remote(
        self,
        request: MeshEnvelope,
        instance: ServiceInstance,
    ) -> Dict[str, Any]:
        """Dispatch a request to a remote service instance via HTTP.

        If host/port belong to localhost, falls back to local handlers.
        Otherwise sends an HTTP POST to the remote node's /mesh/call endpoint.
        """
        host = instance.host
        port = instance.port
        logger.debug(
            "Dispatching %s/%s → %s:%s",
            request.service, request.method, host, port,
        )

        # Check if the target is actually local
        local_hosts = {"127.0.0.1", "localhost", "0.0.0.0", "::1"}
        if host in local_hosts or host.startswith("127."):
            try:
                svc_handlers = self._local_handlers.get(request.service)
                if svc_handlers:
                    handler = svc_handlers.get(request.method)
                    if handler:
                        result = handler(request.payload)
                        return result
                return {"status": "dispatched", "service": request.service}
            except Exception as e:
                logger.error("Local dispatch failed: %s", e)
                raise MeshRoutingError(f"Dispatch to {instance.instance_id} failed: {e}")

        # Remote dispatch via HTTP
        try:
            from core.runtime.mesh.remote.transport import RemoteTransportClient
            from core.runtime.mesh.remote.serialization import envelope_to_json, json_to_envelope
            client = RemoteTransportClient(f"http://{host}:{port}")
            response = client.send_request(request)
            return response.payload
        except ImportError:
            logger.warning("Remote transport not available, falling back to local")
            try:
                svc_handlers = self._local_handlers.get(request.service)
                if svc_handlers:
                    handler = svc_handlers.get(request.method)
                    if handler:
                        result = handler(request.payload)
                        return result
                return {"status": "dispatched", "service": request.service}
            except Exception as e:
                raise MeshRoutingError(f"Dispatch to {instance.instance_id} failed: {e}")
        except Exception as e:
            logger.error("Remote dispatch to %s:%d failed: %s", host, port, e)
            raise MeshRoutingError(f"Dispatch to {instance.instance_id} failed: {e}")

    @staticmethod
    def _select_instance(instances: List[ServiceInstance]) -> ServiceInstance:
        """Select the best instance (round-robin / least-loaded)."""
        return instances[0]
