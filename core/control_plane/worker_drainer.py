"""F2 — WorkerDrainer: graceful worker shutdown.

When a worker needs to be removed (scale down, maintenance, failure),
the drainer ensures:
  1. Worker is marked "draining" — no new tasks assigned
  2. Active tasks are migrated to healthy workers
  3. Worker is removed only after all tasks complete or timeout
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

from core.control_plane.state.system_state import SystemStateBrain

logger = logging.getLogger("emo_ai.control_plane.worker_drainer")


class DrainState(Enum):
    IDLE = "idle"
    DRAINING = "draining"
    DRAINED = "drained"
    FAILED = "failed"


@dataclass
class DrainOperation:
    worker_id: str
    state: DrainState = DrainState.IDLE
    started_at: float = 0.0
    completed_at: float = 0.0
    active_tasks: int = 0
    migrated_tasks: int = 0
    failed_tasks: int = 0
    timeout_seconds: float = 120.0
    error: str = ""


class WorkerDrainer:
    """Manages graceful worker drain operations.

    Coordinates task migration and worker removal.
    Integrates with the Reconciler and HealthManager.
    """

    def __init__(self, state: SystemStateBrain,
                 task_migrator: Optional[Callable] = None):
        self._state = state
        self._task_migrator = task_migrator
        self._drains: Dict[str, DrainOperation] = {}
        self._draining_workers: Set[str] = set()

    def start_drain(self, worker_id: str,
                    timeout_seconds: float = 120.0) -> DrainOperation:
        """Start draining a worker.

        Marks the worker as draining and begins task migration.
        """
        op = DrainOperation(
            worker_id=worker_id,
            state=DrainState.DRAINING,
            started_at=time.time(),
            timeout_seconds=timeout_seconds,
        )
        self._drains[worker_id] = op
        self._draining_workers.add(worker_id)

        worker = self._state.get_worker(worker_id)
        if worker:
            op.active_tasks = worker.active_tasks
            worker.status = "draining"

        logger.info("Drain started: worker=%s, tasks=%d, timeout=%.0fs",
                     worker_id, op.active_tasks, timeout_seconds)
        return op

    def drain_status(self, worker_id: str) -> Optional[DrainOperation]:
        return self._drains.get(worker_id)

    def is_draining(self, worker_id: str) -> bool:
        return worker_id in self._draining_workers

    def list_draining(self) -> List[str]:
        return list(self._draining_workers)

    def tick(self) -> List[DrainOperation]:
        """Process all active drain operations.

        Migrates tasks from draining workers.
        Completes workers whose tasks are all migrated.

        Returns:
            List of completed drain operations.
        """
        completed: List[DrainOperation] = []
        now = time.time()

        for wid, op in list(self._drains.items()):
            if op.state != DrainState.DRAINING:
                continue

            worker = self._state.get_worker(wid)
            active = worker.active_tasks if worker else 0

            if active == 0:
                op.state = DrainState.DRAINED
                op.completed_at = now
                op.migrated_tasks = op.active_tasks
                self._draining_workers.discard(wid)
                logger.info("Drain completed: worker=%s", wid)
                completed.append(op)
                continue

            if now - op.started_at > op.timeout_seconds:
                op.state = DrainState.FAILED
                op.completed_at = now
                op.failed_tasks = active
                op.error = f"Timeout after {op.timeout_seconds}s"
                self._draining_workers.discard(wid)
                logger.warning("Drain timeout: worker=%s, remaining=%d",
                               wid, active)
                completed.append(op)
                continue

            if self._task_migrator and active > 0:
                try:
                    self._task_migrator(wid)
                    op.migrated_tasks = op.active_tasks - active
                except Exception as e:
                    logger.error("Drain migration failed for %s: %s", wid, e)

        return completed

    def complete_drain(self, worker_id: str) -> bool:
        """Force-complete a drain operation."""
        op = self._drains.get(worker_id)
        if not op:
            return False
        op.state = DrainState.DRAINED
        op.completed_at = time.time()
        self._draining_workers.discard(worker_id)
        return True

    def cancel_drain(self, worker_id: str) -> bool:
        """Cancel a drain and mark the worker as available again."""
        self._draining_workers.discard(worker_id)
        op = self._drains.pop(worker_id, None)
        if op:
            worker = self._state.get_worker(worker_id)
            if worker:
                worker.status = "active"
        return op is not None

    def drain_summary(self) -> Dict[str, Any]:
        active = sum(1 for o in self._drains.values() if o.state == DrainState.DRAINING)
        drained = sum(1 for o in self._drains.values() if o.state == DrainState.DRAINED)
        failed = sum(1 for o in self._drains.values() if o.state == DrainState.FAILED)
        return {
            "active_drains": active,
            "completed": drained,
            "failed": failed,
            "draining_workers": len(self._draining_workers),
        }
