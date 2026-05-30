"""Worker Runtime Process — emo-worker daemon for distributed execution.

A standalone daemon process that:
    - Registers with the engine's WorkerRegistry
    - Advertises capabilities (tools, contracts, schema versions)
    - Runs a heartbeat loop for lease renewal
    - Executes tasks in a sandboxed environment
    - Supports graceful shutdown (SIGTERM/SIGINT)

Usage:
    python -m core.worker_runtime \\
        --host localhost --port 9100 \\
        --engine-url http://engine:9000 \\
        --tools agent.explain,graph_retrieval.ranked_hotspots \\
        --capacity 4
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from urllib.request import Request, urlopen
from urllib.error import URLError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("emo_ai.worker")

WORKER_RUNTIME_VERSION = "1.0.0"
DEFAULT_HEARTBEAT_INTERVAL = 15.0
DEFAULT_LEASE_DURATION = 60.0
DEFAULT_CAPABILITIES_PATH = Path("worker_capabilities.json")


# ═══════════════════════════════════════════════════════════════════
# Worker Runtime
# ═══════════════════════════════════════════════════════════════════


class WorkerRuntime:
    """Standalone worker daemon.

    Registers with the engine, advertises capabilities, runs
    heartbeat loop, executes tasks, and handles graceful shutdown.
    """

    def __init__(
        self,
        worker_id: str,
        host: str,
        port: int,
        engine_url: str,
        tools: List[Dict[str, Any]],
        contracts: Optional[List[Dict[str, Any]]] = None,
        schema_versions: Optional[List[str]] = None,
        capacity: int = 1,
        tags: Optional[Dict[str, str]] = None,
        heartbeat_interval: float = DEFAULT_HEARTBEAT_INTERVAL,
        lease_duration: float = DEFAULT_LEASE_DURATION,
    ):
        self.worker_id = worker_id
        self.host = host
        self.port = port
        self.url = f"http://{host}:{port}"
        self.engine_url = engine_url.rstrip("/")
        self.tools = tools
        self.contracts = contracts or []
        self.schema_versions = schema_versions or ["1.0.0"]
        self.capacity = capacity
        self.tags = tags or {}
        self.heartbeat_interval = heartbeat_interval
        self.lease_duration = lease_duration

        self._running = False
        self._stop_event = threading.Event()
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._execution_lock = threading.Lock()
        self._active_tasks: Dict[str, Dict[str, Any]] = {}

    @property
    def version(self) -> str:
        return WORKER_RUNTIME_VERSION

    # ── Lifecycle ──────────────────────────────────────────────

    def start(self) -> None:
        """Register with the engine and start the heartbeat loop."""
        self._running = True
        self._stop_event.clear()

        # Register with engine
        self._register()

        # Start heartbeat thread
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            name=f"worker-hb-{self.worker_id}",
            daemon=True,
        )
        self._heartbeat_thread.start()

        logger.info(
            "Worker %s started on %s (engine=%s, capacity=%d, tools=%d)",
            self.worker_id, self.url, self.engine_url,
            self.capacity, len(self.tools),
        )

    def stop(self, timeout: float = 10.0) -> None:
        """Graceful shutdown: release leases, unregister, stop loop."""
        logger.info("Worker %s shutting down...", self.worker_id)

        # Release active leases
        self._release_all()

        # Unregister from engine
        self._unregister()

        # Stop heartbeat loop
        self._stop_event.set()
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=timeout)

        self._running = False
        logger.info("Worker %s stopped", self.worker_id)

    # ── Registration / Capability Advertise ────────────────────

    def _register(self) -> None:
        """POST /register with capabilities payload."""
        payload = {
            "worker_id": self.worker_id,
            "url": self.url,
            "runtime_version": WORKER_RUNTIME_VERSION,
            "tools": self.tools,
            "contracts": self.contracts,
            "schema_versions": self.schema_versions,
            "capacity": self.capacity,
            "tags": self.tags,
        }
        self._post(f"{self.engine_url}/workers/register", payload)
        logger.info("Registered with engine at %s", self.engine_url)

    def _unregister(self) -> None:
        """POST /unregister to leave the cluster gracefully."""
        try:
            self._post(f"{self.engine_url}/workers/unregister", {
                "worker_id": self.worker_id,
            })
            logger.info("Unregistered from engine")
        except Exception as e:
            logger.warning("Unregister failed: %s", e)

    # ── Heartbeat Loop ─────────────────────────────────────────

    def _heartbeat_loop(self) -> None:
        """Periodically send heartbeat to the engine.

        Also renews active leases.
        """
        while not self._stop_event.is_set():
            try:
                self._send_heartbeat()
                self._renew_active_leases()
            except Exception as e:
                logger.warning("Heartbeat cycle failed: %s", e)

            self._stop_event.wait(timeout=self.heartbeat_interval)

    def _send_heartbeat(self) -> None:
        """POST /heartbeat with current status."""
        payload = {
            "worker_id": self.worker_id,
            "status": "busy" if self._active_tasks else "idle",
            "load": len(self._active_tasks),
            "capacity": self.capacity,
            "leased_tasks": list(self._active_tasks.keys()),
            "timestamp": time.time(),
        }
        self._post(f"{self.engine_url}/workers/heartbeat", payload)

    def _renew_active_leases(self) -> None:
        """Renew all active task leases with the engine."""
        for task_id, info in list(self._active_tasks.items()):
            try:
                self._post(f"{self.engine_url}/leases/renew", {
                    "task_id": task_id,
                    "lease_id": info.get("lease_id", ""),
                    "duration": self.lease_duration,
                })
                logger.debug("Renewed lease for task %s", task_id)
            except Exception as e:
                logger.warning(
                    "Failed to renew lease for task %s: %s",
                    task_id, e,
                )

    def _release_all(self) -> None:
        """Release all active leases on shutdown."""
        for task_id, info in list(self._active_tasks.items()):
            try:
                self._post(f"{self.engine_url}/leases/release", {
                    "task_id": task_id,
                    "lease_id": info.get("lease_id", ""),
                })
            except Exception as e:
                logger.warning(
                    "Failed to release lease for task %s: %s",
                    task_id, e,
                )
        self._active_tasks.clear()

    # ── Task Execution (Sandbox) ───────────────────────────────

    def execute_task(
        self,
        task_id: str,
        tool: str,
        inputs: Dict[str, Any],
        lease_id: str = "",
        execution_id: str = "",
    ) -> Dict[str, Any]:
        """Execute a tool call in the worker sandbox.

        Thread-safe. Tracked as active task for lease renewal.

        Args:
            task_id: The task assignment ID.
            tool: Which tool to execute.
            inputs: Tool input parameters.
            lease_id: Lease ID for ownership tracking.
            execution_id: Unique execution attempt ID.

        Returns:
            Execution result dict.
        """
        with self._execution_lock:
            self._active_tasks[task_id] = {
                "tool": tool,
                "inputs": inputs,
                "lease_id": lease_id,
                "execution_id": execution_id,
                "started_at": time.time(),
            }

        try:
            # Execute the tool via the registered function
            result = self._run_tool(tool, inputs)
            output = {"status": "completed", "result": result}
        except Exception as e:
            logger.exception("Task %s failed: %s", task_id, e)
            output = {"status": "failed", "error": str(e)}
        finally:
            with self._execution_lock:
                self._active_tasks.pop(task_id, None)

        # Add task metadata
        output["task_id"] = task_id
        output["tool"] = tool
        output["worker_id"] = self.worker_id
        output["execution_id"] = execution_id
        return output

    def _run_tool(self, tool: str, inputs: Dict[str, Any]) -> Any:
        """Look up and execute a tool function.

        Override this in subclasses to provide custom tool implementations.
        The base implementation returns a stub.
        """
        # In production, this would dispatch to the actual tool function
        raise NotImplementedError(
            f"Tool '{tool}' not implemented in base WorkerRuntime. "
            "Subclass and override _run_tool()."
        )

    # ── HTTP helpers ───────────────────────────────────────────

    @staticmethod
    def _post(url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Send an HTTP POST with JSON body."""
        body = json.dumps(payload).encode("utf-8")
        req = Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            resp = urlopen(req, timeout=10.0)
            data = resp.read().decode("utf-8")
            return json.loads(data) if data else {}
        except URLError as e:
            raise RuntimeError(f"POST {url} failed: {e.reason}")
        except Exception as e:
            raise RuntimeError(f"POST {url} failed: {e}")


# ═══════════════════════════════════════════════════════════════════
# Signal handling
# ═══════════════════════════════════════════════════════════════════


def _signal_handler(worker: WorkerRuntime, signum: int, frame) -> None:
    """Handle SIGTERM/SIGINT for graceful shutdown."""
    sig_name = signal.Signals(signum).name
    logger.info("Received %s, shutting down gracefully...", sig_name)
    worker.stop()
    sys.exit(0)


# ═══════════════════════════════════════════════════════════════════
# CLI entry point
# ═══════════════════════════════════════════════════════════════════


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse CLI arguments for the worker daemon."""
    parser = argparse.ArgumentParser(
        prog="emo-worker",
        description="Emo-AI Distributed Worker Daemon",
    )
    parser.add_argument(
        "--host", default="localhost",
        help="Host to bind the worker HTTP server (default: localhost)",
    )
    parser.add_argument(
        "--port", type=int, default=9100,
        help="Port for the worker HTTP server (default: 9100)",
    )
    parser.add_argument(
        "--engine-url", default="http://localhost:8000",
        help="Engine URL for registration/heartbeat (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--worker-id",
        help="Unique worker ID (default: auto-generated)",
    )
    parser.add_argument(
        "--tools", default="",
        help="Comma-separated list of tool names this worker supports",
    )
    parser.add_argument(
        "--capacity", type=int, default=2,
        help="Max parallel tasks (default: 2)",
    )
    parser.add_argument(
        "--heartbeat-interval", type=float, default=DEFAULT_HEARTBEAT_INTERVAL,
        help=f"Seconds between heartbeats (default: {DEFAULT_HEARTBEAT_INTERVAL})",
    )
    parser.add_argument(
        "--lease-duration", type=float, default=DEFAULT_LEASE_DURATION,
        help=f"Lease duration in seconds (default: {DEFAULT_LEASE_DURATION})",
    )
    parser.add_argument(
        "--capabilities-file",
        help="Path to JSON file with tool capabilities/contracts",
    )
    parser.add_argument(
        "--tags", default="",
        help="Comma-separated key=value tags (e.g. pool=gpu,region=us-east)",
    )
    return parser.parse_args(argv)


def build_capabilities(args: argparse.Namespace) -> tuple:
    """Build tools and contracts lists from CLI args + file."""
    tools: List[Dict[str, Any]] = []
    contracts: List[Dict[str, Any]] = []

    # Parse --tools
    if args.tools:
        for name in args.tools.split(","):
            name = name.strip()
            if name:
                tools.append({"name": name, "version": "1.0.0"})

    # Parse --tags
    tags: Dict[str, str] = {}
    if args.tags:
        for pair in args.tags.split(","):
            pair = pair.strip()
            if "=" in pair:
                k, v = pair.split("=", 1)
                tags[k.strip()] = v.strip()

    # Load capabilities file
    if args.capabilities_file:
        path = Path(args.capabilities_file)
        if path.exists():
            with open(path) as f:
                data = json.load(f)
            tools = data.get("tools", tools)
            contracts = data.get("contracts", contracts)
        else:
            logger.warning("Capabilities file not found: %s", path)

    return tools, contracts, tags


def main(argv: Optional[List[str]] = None) -> None:
    """Entry point for the worker daemon."""
    args = parse_args(argv)

    # Build worker ID
    worker_id = args.worker_id or f"worker-{os.uname().nodename}-{args.port}"

    # Build capabilities
    tools, contracts, tags = build_capabilities(args)

    if not tools:
        logger.warning("No tools specified. Worker will register with no capabilities.")

    # Create and start worker
    worker = WorkerRuntime(
        worker_id=worker_id,
        host=args.host,
        port=args.port,
        engine_url=args.engine_url,
        tools=tools,
        contracts=contracts,
        capacity=args.capacity,
        tags=tags,
        heartbeat_interval=args.heartbeat_interval,
        lease_duration=args.lease_duration,
    )

    # Register signal handlers for graceful shutdown
    signal.signal(
        signal.SIGTERM,
        lambda s, f: _signal_handler(worker, s, f),
    )
    signal.signal(
        signal.SIGINT,
        lambda s, f: _signal_handler(worker, s, f),
    )

    # Start the worker (blocks until signal)
    worker.start()
    logger.info("Worker %s running. Press Ctrl+C to stop.", worker_id)

    # Keep alive
    try:
        signal.pause()
    except AttributeError:
        # signal.pause() not available on all platforms
        while worker._running:
            time.sleep(1)


if __name__ == "__main__":
    main()
