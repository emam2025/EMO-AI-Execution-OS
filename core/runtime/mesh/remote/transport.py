"""Phase 5 — Distributed Runtime HTTP transport.

MeshEnvelope transport over HTTP using httpx (client) and
the standard library http.server (server).

Architecture:
  MeshNode A                MeshNode B
     |                          |
     |--- HTTP POST /call ---->|
     |    MeshEnvelope JSON     |  → local handler lookup
     |<--- HTTP 200 response ---|  → MeshEnvelope response
     |                          |
"""
from __future__ import annotations

import json
import logging
import socketserver
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

import httpx

from typing import Any, Callable, Dict, Optional

from core.runtime.mesh.remote.serialization import (
    json_to_envelope,
    envelope_to_json,
)
from core.runtime.mesh.service_registry import ServiceRegistry, ServiceInstance, ServiceStatus

logger = logging.getLogger("emo_ai.mesh.remote")

DEFAULT_TIMEOUT = 10.0


class RemoteTransportError(Exception):
    """Raised when remote transport fails."""


# Thread-safe HTTP server
class ThreadingHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    """Handle requests in separate threads."""
    allow_reuse_address = True
    daemon_threads = True


class RemoteTransportClient:
    """HTTP client for sending MeshEnvelopes to remote nodes.

    Uses httpx for async-capable HTTP transport.
    """

    def __init__(self, base_url: str, timeout: float = DEFAULT_TIMEOUT):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def send_request(self, envelope: MeshEnvelope) -> MeshEnvelope:
        """Send a request envelope to a remote node and get the response."""
        url = f"{self._base_url}/mesh/call"
        payload = envelope_to_json(envelope)
        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.post(
                    url,
                    content=payload,
                    headers={"Content-Type": "application/json"},
                )
                resp.raise_for_status()
                return json_to_envelope(resp.text)
        except httpx.HTTPError as e:
            raise RemoteTransportError(f"HTTP transport failed: {e}") from e

    def send_heartbeat(self, envelope: MeshEnvelope) -> bool:
        """Send a heartbeat to a remote node."""
        url = f"{self._base_url}/mesh/heartbeat"
        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.post(
                    url,
                    content=envelope_to_json(envelope),
                    headers={"Content-Type": "application/json"},
                )
                return resp.status_code == 200
        except httpx.HTTPError:
            return False

    def register_remote(self, service: str, instance_id: str, host: str, port: int) -> bool:
        """Register this node's service with a remote registry."""
        url = f"{self._base_url}/mesh/register"
        payload = json.dumps({
            "service": service,
            "instance_id": instance_id,
            "host": host,
            "port": port,
        })
        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.post(
                    url,
                    content=payload,
                    headers={"Content-Type": "application/json"},
                )
                return resp.status_code == 200
        except httpx.HTTPError:
            return False


def _make_handler(dispatch_fn: Optional[Callable] = None,
                  registry: Optional[ServiceRegistry] = None):
    """Factory: create a MeshRequestHandler class with dispatch_fn and registry."""

    class _MeshRequestHandler(BaseHTTPRequestHandler):
        """HTTP request handler for the remote mesh server."""

        def log_message(self, fmt, *args):
            logger.debug("HTTP %s", fmt % args)

        def _read_body(self):
            length = int(self.headers.get("Content-Length", 0))
            return self.rfile.read(length).decode() if length > 0 else ""

        def _send_json(self, status, data):
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(data.encode())

        def _send_error(self, status, message):
            self._send_json(status, json.dumps({"error": message}))

        def _handle_call(self):
            body = self._read_body()
            try:
                envelope = json_to_envelope(body)
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                self._send_error(400, f"Invalid envelope: {e}")
                return

            if dispatch_fn is None:
                self._send_error(500, "No dispatch function configured")
                return

            try:
                response = dispatch_fn(envelope)
                self._send_json(200, envelope_to_json(response))
            except Exception as e:
                self._send_error(500, str(e))

        def _handle_register(self):
            body = self._read_body()
            try:
                data = json.loads(body)
            except json.JSONDecodeError as e:
                self._send_error(400, f"Invalid registration body: {e}")
                return

            if registry is None:
                self._send_json(200, json.dumps({"status": "registered_noop"}))
                return

            instance = ServiceInstance(
                service_name=data.get("service_name", "unknown"),
                instance_id=data.get("instance_id", ""),
                host=data.get("host", self.client_address[0]),
                port=int(data.get("port", 0)),
                capabilities=data.get("capabilities", []),
                metadata=data.get("metadata", {}),
            )
            registry.register(instance)
            logger.info(
                "Remote registration: %s/%s at %s:%d",
                instance.service_name, instance.instance_id,
                instance.host, instance.port,
            )
            self._send_json(200, json.dumps({
                "status": "registered",
                "instance_id": instance.instance_id,
            }))

        def do_POST(self):
            if self.path == "/mesh/call":
                self._handle_call()
            elif self.path == "/mesh/heartbeat":
                self._send_json(200, json.dumps({"status": "ok"}))
            elif self.path == "/mesh/register":
                self._handle_register()
            else:
                self._send_error(404, f"Unknown path: {self.path}")

    return _MeshRequestHandler


class RemoteTransportServer:
    """HTTP server that accepts remote mesh requests.

    Runs in a background thread so it doesn't block the main thread.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 0,
        dispatch_fn: Optional[Callable] = None,
        registry: Optional[ServiceRegistry] = None,
    ):
        self._host = host
        self._port = port
        self._dispatch_fn = dispatch_fn
        self._registry = registry
        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def host(self) -> str:
        return self._host

    @property
    def port(self) -> int:
        if self._server:
            return self._server.server_address[1]
        return self._port

    def start(self):
        """Start the HTTP server in a background thread."""
        handler_class = _make_handler(self._dispatch_fn, self._registry)
        self._server = ThreadingHTTPServer(
            (self._host, self._port),
            handler_class,
        )
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            daemon=True,
        )
        self._thread.start()
        actual_port = self._server.server_address[1]
        logger.info(
            "Remote mesh server started on %s:%d",
            self._host, actual_port,
        )

    def shutdown(self):
        """Shutdown the HTTP server."""
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._thread = None
            self._server = None
            logger.info("Remote mesh server stopped")
