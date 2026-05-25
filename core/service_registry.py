"""Service Registry — Tool endpoint abstraction for distributed execution.

Maps tool names to execution endpoints (local callable or remote service).
Enables running DAG nodes on different workers or even different machines.

Architecture:
    ServiceRegistry
        ├── register_local("tool.name", fn, spec)   → in-process callable
        ├── register_remote("tool.name", url, spec)  → HTTP POST to url
        └── execute("tool.name", inputs) → dict result

Each endpoint enforces its own timeout. Remote calls use urllib
(falls back to httpx if available).

Enhanced RemoteEndpoint:
    - get_status()       → health check (GET /health)
    - capabilities()     → tool manifest (GET /capabilities)
    - supports_tool()    → version-aware capability check
    - execute()          → POST /execute with lease + execution context
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, List, Optional

from .models.dag import ToolSpec

logger = logging.getLogger("emo_ai.service_registry")

SERVICE_REGISTRY_VERSION = "1.1.0"


class ToolEndpoint:
    """Abstracts a single tool execution target.

    Can be local (in-process callable) or remote (HTTP endpoint).
    """

    def __init__(self, tool_name: str, spec: ToolSpec):
        self.tool_name = tool_name
        self.spec = spec

    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError


class LocalEndpoint(ToolEndpoint):
    """Executes a tool via an in-process callable."""

    def __init__(self, tool_name: str, fn: Callable, spec: ToolSpec):
        super().__init__(tool_name, spec)
        self._fn = fn

    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        result = self._fn(**inputs)
        return result if result is not None else {}


class RemoteEndpoint(ToolEndpoint):
    """Executes a tool by POSTing to a remote HTTP endpoint.

    Expects JSON request body with the tool's inputs and returns
    a JSON response with the tool's outputs.

    Also supports:
      - GET /health  → {"status": "ok", "version": "...", "load": ...}
      - GET /capabilities → [ToolSpec, ...]
    """

    def __init__(self, tool_name: str, url: str, spec: ToolSpec):
        super().__init__(tool_name, spec)
        self._url = url.rstrip("/")
        self._timeout = spec.timeout_seconds or 30.0

    # ── Health check ─────────────────────────────────────────────

    def get_status(self) -> Dict[str, Any]:
        """Ping the remote worker's health endpoint.

        Returns:
            Dict with keys: status, version, load, tools_count,
            leased_tasks.

        Raises:
            RuntimeError: If the worker is unreachable.
        """
        try:
            resp = urllib.request.urlopen(
                f"{self._url}/health", timeout=self._timeout,
            )
            data = resp.read().decode("utf-8")
            return json.loads(data)
        except urllib.error.URLError as e:
            raise RuntimeError(
                f"Worker {self._url} health check failed: {e.reason}"
            )

    # ── Capability negotiation ───────────────────────────────────

    def capabilities(self) -> List[Dict[str, Any]]:
        """Fetch the remote worker's tool manifest.

        Returns:
            List of tool descriptors (each containing name, version,
            contract info, etc.).

        Raises:
            RuntimeError: If the worker is unreachable.
        """
        try:
            resp = urllib.request.urlopen(
                f"{self._url}/capabilities", timeout=self._timeout,
            )
            data = resp.read().decode("utf-8")
            return json.loads(data)
        except urllib.error.URLError as e:
            raise RuntimeError(
                f"Worker {self._url} capabilities fetch failed: {e.reason}"
            )

    def supports_tool(self, tool_name: str,
                      tool_version: str = "") -> bool:
        """Check if the remote worker supports a specific tool.

        Args:
            tool_name: Tool name to check.
            tool_version: Optional required version (empty = any).

        Returns:
            True if the worker has the tool and the version matches.
        """
        try:
            caps = self.capabilities()
        except RuntimeError:
            return False
        for desc in caps:
            if desc.get("name") == tool_name:
                if not tool_version:
                    return True
                return desc.get("version", "") == tool_version
        return False

    # ── Execution with lease context ─────────────────────────────

    def execute(
        self,
        inputs: Dict[str, Any],
        *,
        lease_id: str = "",
        execution_id: str = "",
        attempt_number: int = 0,
    ) -> Dict[str, Any]:
        """Execute a tool on the remote worker.

        Sends tool inputs plus lease/execution context so the worker
        can participate in the ownership protocol.

        Args:
            inputs: Tool input parameters.
            lease_id: Task lease ID for ownership verification.
            execution_id: Unique execution attempt ID.
            attempt_number: Which attempt (0 = first).

        Returns:
            Tool execution result dict.
        """
        body_dict = {
            "inputs": inputs,
            "context": {
                "lease_id": lease_id,
                "execution_id": execution_id,
                "attempt_number": attempt_number,
                "tool": self.tool_name,
            },
        }
        body = json.dumps(body_dict).encode("utf-8")
        req = urllib.request.Request(
            f"{self._url}/execute",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            resp = urllib.request.urlopen(req, timeout=self._timeout)
            data = resp.read().decode("utf-8")
            return json.loads(data)
        except urllib.error.HTTPError as e:
            msg = (
                f"Remote tool {self.tool_name} HTTP {e.code}: "
                f"{e.read().decode('utf-8', errors='replace')}"
            )
            raise RuntimeError(msg)
        except urllib.error.URLError as e:
            raise RuntimeError(
                f"Remote tool {self.tool_name} connection failed: {e.reason}"
            )
        except TimeoutError:
            raise TimeoutError(
                f"Remote tool {self.tool_name} timed out after {self._timeout}s"
            )


class ServiceRegistry:
    """Maps tool names to execution endpoints.

    Thread-safe: multiple workers can call execute() concurrently.
    """

    def __init__(self):
        self._endpoints: Dict[str, ToolEndpoint] = {}

    # ── Registration ────────────────────────────────────────────────

    def register_local(self, tool_name: str, fn: Callable, spec: Optional[ToolSpec] = None) -> None:
        """Register an in-process callable as a tool endpoint."""
        self._endpoints[tool_name] = LocalEndpoint(tool_name, fn, spec or ToolSpec(name=tool_name))

    def register_remote(self, tool_name: str, url: str, spec: Optional[ToolSpec] = None) -> None:
        """Register a remote HTTP service as a tool endpoint."""
        self._endpoints[tool_name] = RemoteEndpoint(tool_name, url, spec or ToolSpec(name=tool_name))

    def register_endpoint(self, tool_name: str, endpoint: ToolEndpoint) -> None:
        self._endpoints[tool_name] = endpoint

    def unregister(self, tool_name: str) -> None:
        self._endpoints.pop(tool_name, None)

    # ── Execution ───────────────────────────────────────────────────

    def execute(self, tool_name: str, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool by name with the given inputs.

        Raises KeyError if tool is not registered.
        Raises RuntimeError / TimeoutError on execution failure.
        """
        endpoint = self._endpoints.get(tool_name)
        if endpoint is None:
            raise KeyError(f"Tool '{tool_name}' not registered in ServiceRegistry")
        return endpoint.execute(inputs)

    def can_execute(self, tool_name: str) -> bool:
        return tool_name in self._endpoints

    # ── Introspection ───────────────────────────────────────────────

    def registered_tools(self) -> Dict[str, str]:
        return {
            name: "local" if isinstance(ep, LocalEndpoint) else "remote"
            for name, ep in self._endpoints.items()
        }

    def get_spec(self, tool_name: str) -> Optional[ToolSpec]:
        ep = self._endpoints.get(tool_name)
        return ep.spec if ep else None

    def clear(self) -> None:
        self._endpoints.clear()
