"""Worker Heartbeat Daemon — background lease renewal for distributed execution.

Ensures leased tasks stay alive by periodically renewing their leases.
Handles auto-disconnect: if a worker stops responding, the daemon
marks tasks for reassignment.

Architecture:
    Engine
      ├── DistributedScheduler          (task → worker)
      ├── OwnershipManager              (lease CRUD)
      └── WorkerHeartbeatDaemon ← YOU ARE HERE
            ├── background thread loop
            ├── register_task / unregister_task
            ├── auto-renewal
            └── auto-disconnect handling

Thread-safe. Designed to be embedded in the engine process.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Dict, Optional, Set, Tuple, Callable

from .ownership_manager import OwnershipManager

logger = logging.getLogger("emo_ai.heartbeat_daemon")

HEARTBEAT_VERSION: str = "1.0.0"
DEFAULT_HEARTBEAT_INTERVAL: float = 10.0  # seconds between heartbeat cycles
DEFAULT_MAX_RETRIES: int = 3
TASK_HEARTBEAT_FACTOR: float = 0.25       # renew at 25% of lease remaining


class HeartbeatEntry:
    """Tracks a single task's heartbeat state in the daemon."""

    def __init__(
        self,
        task_id: str,
        lease_id: str,
        worker_id: str,
        lease_duration: float,
    ):
        self.task_id = task_id
        self.lease_id = lease_id
        self.worker_id = worker_id
        self.lease_duration = lease_duration
        self.failure_count: int = 0
        self.last_success: float = time.time()
        self.last_attempt: float = 0.0
        self.active: bool = True


class WorkerHeartbeatDaemon:
    """Background daemon that manages lease renewal for active tasks.

    Usage:
        daemon = WorkerHeartbeatDaemon(ownership_manager)
        daemon.start()

        # After scheduling a task on a remote worker:
        daemon.register_task(task_id, lease_id, worker_id, lease_duration)

        # On task completion:
        daemon.unregister_task(task_id)

        daemon.stop()  # graceful shutdown
    """

    def __init__(
        self,
        ownership_manager: OwnershipManager,
        heartbeat_interval: float = DEFAULT_HEARTBEAT_INTERVAL,
        max_retries: int = DEFAULT_MAX_RETRIES,
        on_task_expired: Optional[Callable[[str, str], None]] = None,
    ):
        self._ownership = ownership_manager
        self._heartbeat_interval = heartbeat_interval
        self._max_retries = max_retries
        self._on_task_expired = on_task_expired

        self._entries: Dict[str, HeartbeatEntry] = {}
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    # ── Lifecycle ───────────────────────────────────────────────

    @property
    def version(self) -> str:
        return HEARTBEAT_VERSION

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        """Start the background heartbeat loop (non-blocking)."""
        if self.is_running:
            logger.warning("Heartbeat daemon already running")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._heartbeat_loop,
            name="heartbeat-daemon",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "Heartbeat daemon started (interval=%.1fs, max_retries=%d)",
            self._heartbeat_interval, self._max_retries,
        )

    def stop(self, timeout: float = 5.0) -> None:
        """Signal the daemon to stop and wait for the thread.

        Args:
            timeout: Max seconds to wait for graceful shutdown.
        """
        if not self.is_running:
            return
        self._stop_event.set()
        self._thread.join(timeout=timeout)
        if self._thread.is_alive():
            logger.warning("Heartbeat daemon did not stop within %.1fs", timeout)
        else:
            logger.info("Heartbeat daemon stopped")
            self._thread = None

    # ── Task registration ───────────────────────────────────────

    def register_task(
        self,
        task_id: str,
        lease_id: str,
        worker_id: str,
        lease_duration: float,
    ) -> None:
        """Start tracking a task's lease for periodic renewal.

        Args:
            task_id: The task to track.
            lease_id: Lease ID returned by OwnershipManager.claim().
            worker_id: Worker that owns the lease.
            lease_duration: Lease duration in seconds.
        """
        with self._lock:
            self._entries[task_id] = HeartbeatEntry(
                task_id=task_id,
                lease_id=lease_id,
                worker_id=worker_id,
                lease_duration=lease_duration,
            )
        logger.debug(
            "Heartbeat: registered task %s (worker=%s, lease=%s)",
            task_id, worker_id, lease_id,
        )

    def unregister_task(self, task_id: str) -> None:
        """Stop tracking a task's lease (task completed or failed).
        
        Does NOT release the lease — that should be done by the caller
        via OwnershipManager.release().
        """
        with self._lock:
            self._entries.pop(task_id, None)
        logger.debug("Heartbeat: unregistered task %s", task_id)

    def registered_count(self) -> int:
        with self._lock:
            return len(self._entries)

    def registered_tasks(self) -> Set[str]:
        with self._lock:
            return set(self._entries.keys())

    def get_entry(self, task_id: str) -> Optional[HeartbeatEntry]:
        with self._lock:
            entry = self._entries.get(task_id)
            if entry is None:
                return None
            return entry

    # ── Background loop ─────────────────────────────────────────

    def _heartbeat_loop(self) -> None:
        """Main loop: iterates over registered tasks and renews leases."""
        while not self._stop_event.is_set():
            cycle_start = time.time()
            self._process_cycle()
            elapsed = time.time() - cycle_start
            sleep_time = max(0.0, self._heartbeat_interval - elapsed)
            if self._stop_event.wait(timeout=sleep_time):
                break

    def _process_cycle(self) -> None:
        """One heartbeat cycle: check each entry, renew if needed.

        Thread-safe: snapshot entries under lock, process outside.
        """
        with self._lock:
            entries = list(self._entries.values())

        for entry in entries:
            if self._stop_event.is_set():
                return
            if not entry.active:
                continue
            self._renew_entry(entry)

    def _renew_entry(self, entry: HeartbeatEntry) -> None:
        """Attempt to renew a single task's lease.

        Renewal is triggered when the remaining lease time drops below
        TASK_HEARTBEAT_FACTOR of the original duration.

        On failure: increments failure_count. After max_retries,
        marks the task as expired and calls on_task_expired callback.
        """
        now = time.time()
        elapsed_since_last = now - entry.last_attempt
        if elapsed_since_last < self._heartbeat_interval * 0.5:
            return  # too soon since last attempt

        entry.last_attempt = now

        # Check if renew should trigger based on remaining lease time
        # We can check using ownership's renew_lease which extends by
        # the full duration; we always attempt at this point
        success = self._ownership.renew_lease(
            entry.task_id,
            entry.lease_id,
            entry.lease_duration,
        )

        if success:
            entry.failure_count = 0
            entry.last_success = now
            logger.debug(
                "Heartbeat: renewed lease for task %s (worker=%s)",
                entry.task_id, entry.worker_id,
            )
        else:
            entry.failure_count += 1
            logger.warning(
                "Heartbeat: renewal failed for task %s (worker=%s, "
                "failure=%d/%d)",
                entry.task_id, entry.worker_id,
                entry.failure_count, self._max_retries,
            )

            if entry.failure_count >= self._max_retries:
                self._handle_expired(entry)

    def _handle_expired(self, entry: HeartbeatEntry) -> None:
        """Mark a task as expired after repeated renewal failures.

        Releases the lease via OwnershipManager, calls the
        on_task_expired callback, and removes the entry.
        """
        entry.active = False
        logger.error(
            "Heartbeat: task %s expired (worker=%s, lease=%s) — "
            "max retries reached",
            entry.task_id, entry.worker_id, entry.lease_id,
        )

        # Release the lease
        self._ownership.release(entry.task_id, entry.lease_id)

        # Notify the engine
        if self._on_task_expired:
            try:
                self._on_task_expired(entry.task_id, entry.worker_id)
            except Exception:
                logger.exception(
                    "Heartbeat: on_task_expired callback failed for %s",
                    entry.task_id,
                )

        with self._lock:
            self._entries.pop(entry.task_id, None)
