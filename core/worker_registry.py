"""Worker Registry — manages a pool of distributed worker nodes.

Thread-safe.  Each worker is tracked by its unique *id*.

Architecture:
    WorkerRegistry
        ├── register(worker)        → adds a new worker
        ├── unregister(worker_id)   → removes a worker
        ├── heartbeat(worker_id)    → updates last_heartbeat timestamp
        ├── get(worker_id)          → returns WorkerNode or None
        ├── available_workers(tool) → workers that support a given tool
        └── prune_offline(timeout)  → removes stale workers
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Dict, List, Optional

from .distributed_types import WorkerNode, WORKER_TIMEOUT, WorkerStatus

logger = logging.getLogger("emo_ai.worker_registry")


class WorkerRegistry:
    """Thread-safe registry of distributed worker nodes."""

    def __init__(self):
        self._lock = threading.Lock()
        self._workers: Dict[str, WorkerNode] = {}

    # ── lifecycle ───────────────────────────────────────────────────

    def register(self, worker: WorkerNode) -> None:
        """Register (or re-register) a worker node.

        If a worker with the same *id* already exists, its metadata
        is updated and its heartbeat is refreshed.
        """
        with self._lock:
            worker.status = WorkerStatus.IDLE
            worker.last_heartbeat = time.time()
            self._workers[worker.id] = worker
            logger.info("Worker registered: %s (%d tools)", worker.id, len(worker.tools))

    def unregister(self, worker_id: str) -> Optional[WorkerNode]:
        """Remove a worker from the registry.

        Returns the removed worker, or *None* if not found.
        """
        with self._lock:
            removed = self._workers.pop(worker_id, None)
            if removed:
                logger.info("Worker unregistered: %s", worker_id)
            return removed

    def heartbeat(self, worker_id: str) -> bool:
        """Refresh a worker's liveness timestamp.

        Returns *True* if the worker was found, *False* otherwise.
        """
        with self._lock:
            worker = self._workers.get(worker_id)
            if worker is None:
                return False
            worker.last_heartbeat = time.time()
            worker.status = WorkerStatus.IDLE
            return True

    def get(self, worker_id: str) -> Optional[WorkerNode]:
        """Return the worker node, or *None*."""
        with self._lock:
            return self._workers.get(worker_id)

    def list_workers(self) -> List[WorkerNode]:
        """Return a snapshot of all registered workers."""
        with self._lock:
            return list(self._workers.values())

    def worker_count(self) -> int:
        with self._lock:
            return len(self._workers)

    # ── discovery ───────────────────────────────────────────────────

    def available_workers(self, tool_name: str) -> List[WorkerNode]:
        """Return workers that are available *and* support the given tool.

        A worker is considered available when:
          - status is not OFFLINE
          - it has remaining capacity
          - it supports the tool
        """
        with self._lock:
            return [
                w for w in self._workers.values()
                if w.status != WorkerStatus.OFFLINE
                and w.available_capacity > 0
                and w.supports_tool(tool_name)
            ]

    def any_worker_for(self, tool_name: str) -> Optional[WorkerNode]:
        """Pick the best available worker for a tool (least-loaded first).

        Only returns workers with available capacity and online status.
        """
        with self._lock:
            candidates = [
                w for w in self._workers.values()
                if w.status != WorkerStatus.OFFLINE
                and w.available_capacity > 0
                and w.supports_tool(tool_name)
            ]
            if not candidates:
                return None
            # Least-loaded first, then highest capacity
            return min(candidates, key=lambda w: (
                w.current_load / max(w.capacity, 1),
                -w.capacity,
            ))

    def workers_by_tag(self, key: str, value: str) -> List[WorkerNode]:
        """Return workers matching a specific tag."""
        with self._lock:
            return [
                w for w in self._workers.values()
                if w.tags.get(key) == value
            ]

    # ── health ──────────────────────────────────────────────────────

    def prune_offline(self, timeout: Optional[float] = None) -> int:
        """Remove workers whose heartbeat has expired.

        Args:
            timeout: Seconds since last heartbeat before pruning.
                     Defaults to *WORKER_TIMEOUT*.

        Returns:
            Number of workers pruned.
        """
        timeout = timeout if timeout is not None else WORKER_TIMEOUT
        now = time.time()
        pruned: List[str] = []
        with self._lock:
            for wid, w in list(self._workers.items()):
                if now - w.last_heartbeat > timeout:
                    pruned.append(wid)
                    del self._workers[wid]
        if pruned:
            logger.warning("Pruned %d offline worker(s): %s", len(pruned), pruned)
        return len(pruned)

    def mark_offline(self, worker_id: str) -> bool:
        """Mark a worker as OFFLINE without removing it."""
        with self._lock:
            worker = self._workers.get(worker_id)
            if worker is None:
                return False
            worker.status = WorkerStatus.OFFLINE
            return True

    # ── load tracking ───────────────────────────────────────────────

    def increment_load(self, worker_id: str) -> bool:
        """Increment the current load counter for a worker."""
        with self._lock:
            worker = self._workers.get(worker_id)
            if worker is None:
                return False
            worker.current_load = min(worker.capacity, worker.current_load + 1)
            if worker.current_load >= worker.capacity:
                worker.status = WorkerStatus.BUSY
            return True

    def decrement_load(self, worker_id: str) -> bool:
        """Decrement the current load counter for a worker."""
        with self._lock:
            worker = self._workers.get(worker_id)
            if worker is None:
                return False
            worker.current_load = max(0, worker.current_load - 1)
            if worker.current_load == 0:
                worker.status = WorkerStatus.IDLE
            return True
