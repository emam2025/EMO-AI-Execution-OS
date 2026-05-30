"""GAP 2 — WorkerOrchestrator: worker lifecycle management.

Manages the lifecycle of runtime workers — creation, scaling,
health tracking, and shutdown.
"""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from core.security.capabilities import TrustLevel
from core.security.worker_verifier import WorkerVerifier

logger = logging.getLogger("emo_ai.control.orchestrator")


class WorkerState(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    DEGRADED = "degraded"
    SHUTTING_DOWN = "shutting_down"
    TERMINATED = "terminated"


@dataclass
class Worker:
    """A runtime worker instance."""
    worker_id: str
    state: WorkerState = WorkerState.PENDING
    created_at: float = 0.0
    last_heartbeat: float = 0.0
    active_tasks: int = 0
    capacity: int = 5
    metadata: Dict[str, Any] = field(default_factory=dict)
    trust_level: TrustLevel = TrustLevel.TRUSTED


class WorkerOrchestrator:
    """Manages the lifecycle of all runtime workers.

    Responsibilities:
      - Create / destroy workers
      - Track worker health
      - Assign tasks to workers
      - Scale up/down based on load
    """

    def __init__(self, verifier: Optional[WorkerVerifier] = None) -> None:
        self._lock = threading.Lock()
        self._workers: Dict[str, Worker] = {}
        self._counter: int = 0
        import time
        self._start_time = time.time()
        self._verifier = verifier or WorkerVerifier()

    def create_worker(self, capacity: int = 5,
                      trust_level: TrustLevel = TrustLevel.UNVERIFIED,
                      worker_id: Optional[str] = None) -> Worker:
        """Create a new worker.

        If trust_level is UNVERIFIED, issues a challenge for later verification.
        Workers start as UNVERIFIED by default and must be verified to be TRUSTED.

        Args:
            capacity: Max concurrent tasks.
            trust_level: Trust level for the worker.
            worker_id: Optional explicit worker ID. Auto-generated if not provided.
        """
        import time
        with self._lock:
            self._counter += 1
            wid = worker_id or f"worker-{self._counter}"
            worker = Worker(
                worker_id=wid,
                state=WorkerState.ACTIVE,
                created_at=time.time(),
                last_heartbeat=time.time(),
                capacity=capacity,
                trust_level=trust_level,
            )
            self._workers[wid] = worker

        # Issue verification challenge for unverified workers (E4)
        if trust_level == TrustLevel.UNVERIFIED:
            challenge = self._verifier.issue_challenge(worker.worker_id)
            logger.info("Worker created: %s (capacity=%d, trust=UNVERIFIED, challenge=%s...)",
                        worker.worker_id, capacity, challenge[:12])
        else:
            logger.info("Worker created: %s (capacity=%d, trust=%s)",
                        worker.worker_id, capacity, trust_level.value)
        return worker

    def terminate_worker(self, worker_id: str) -> bool:
        """Terminate a worker."""
        with self._lock:
            worker = self._workers.get(worker_id)
            if worker is None:
                return False
            worker.state = WorkerState.TERMINATED
            logger.info("Worker terminated: %s", worker_id)
            return True

    def get_worker(self, worker_id: str) -> Optional[Worker]:
        with self._lock:
            return self._workers.get(worker_id)

    def active_workers(self) -> List[Worker]:
        """Return all active workers."""
        with self._lock:
            return [
                w for w in self._workers.values()
                if w.state == WorkerState.ACTIVE
            ]

    def active_count(self) -> int:
        return len(self.active_workers())

    def scale_up(self, count: int = 1) -> List[Worker]:
        """Add new workers."""
        created = []
        for _ in range(count):
            created.append(self.create_worker())
        return created

    def scale_down(self, count: int = 1) -> int:
        """Remove workers (least loaded first)."""
        with self._lock:
            active = sorted(
                [w for w in self._workers.values()
                 if w.state == WorkerState.ACTIVE],
                key=lambda w: w.active_tasks,
            )
            terminated = 0
            for worker in active[:count]:
                worker.state = WorkerState.TERMINATED
                terminated += 1
            if terminated:
                logger.info("Scaled down: %d workers terminated", terminated)
            return terminated

    def heartbeat(self, worker_id: str) -> bool:
        """Record a worker heartbeat."""
        import time
        with self._lock:
            worker = self._workers.get(worker_id)
            if worker is None:
                return False
            worker.last_heartbeat = time.time()
            return True

    def shutdown_all(self) -> int:
        """Terminate all workers."""
        with self._lock:
            count = 0
            for worker in self._workers.values():
                if worker.state == WorkerState.ACTIVE:
                    worker.state = WorkerState.TERMINATED
                    count += 1
            logger.info("Shutdown: %d workers terminated", count)
            return count

    def assign_task(self, worker_id: str) -> bool:
        """Assign a task to a worker (increment active count)."""
        with self._lock:
            worker = self._workers.get(worker_id)
            if worker is None or worker.state != WorkerState.ACTIVE:
                return False
            if worker.active_tasks >= worker.capacity:
                return False
            worker.active_tasks += 1
            return True

    def complete_task(self, worker_id: str) -> bool:
        """Mark a task as complete on a worker."""
        with self._lock:
            worker = self._workers.get(worker_id)
            if worker is None:
                return False
            worker.active_tasks = max(0, worker.active_tasks - 1)
            return True
