"""Ownership Manager — distributed execution authority layer.

Prevents split-brain execution by enforcing:
  - Exactly one owner per task at any time
  - Time-bound leases with heartbeat renewal
  - Automatic expiration and reassignment
  - Idempotent execution tracking

Architecture:
    ExecutionEngine
        ↓
    DistributedScheduler
        ↓
    OwnershipManager   ← YOU ARE HERE
        ↓
    WorkerRegistry
        ↓
    Workers

Storage:
    SQLite with WAL mode (swappable to Redis/Postgres later).

Protocol:
    claim(task_id, worker_id, lease_duration) → lease_id
        - Fails if task is already owned by another active worker

    renew_lease(task_id, lease_id) → bool
        - Extends lease; returns False if lease expired or wrong worker

    release(task_id, lease_id) → bool
        - Voluntarily releases ownership

    reassign_expired() → List[task_id]
        - Finds expired leases and marks them available

    owner_of(task_id) → Optional[str]
        - Returns current owner worker_id or None
"""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from .distributed_types import TaskAssignment, TaskStatus

logger = logging.getLogger("emo_ai.ownership_manager")

LEASE_DEFAULT_DURATION: float = 60.0        # seconds before lease expires
LEASE_HEARTBEAT_INTERVAL: float = 15.0      # seconds between heartbeats
OWNERSHIP_VERSION: str = "1.0.0"
_DEFAULT_DB_PATH = Path(".ai/index/ownership.db")


class LeaseStore:
    """SQLite-backed lease persistence.

    Thread-safe. Uses WAL journal mode for concurrent access.
    """

    def __init__(self, db_path: Optional[Path] = None):
        self._db_path = db_path or _DEFAULT_DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        with self._lock:
            with sqlite3.connect(str(self._db_path)) as conn:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=NORMAL")
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS leases (
                        task_id TEXT PRIMARY KEY,
                        lease_id TEXT NOT NULL,
                        worker_id TEXT NOT NULL,
                        execution_id TEXT NOT NULL DEFAULT '',
                        attempt_number INTEGER NOT NULL DEFAULT 0,
                        status TEXT NOT NULL DEFAULT 'pending',
                        leased_until REAL,
                        created_at REAL NOT NULL DEFAULT (julianday('now'))
                    )
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_leases_worker
                    ON leases(worker_id)
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_leases_expired
                    ON leases(leased_until)
                """)
                conn.commit()

    # ── CRUD ────────────────────────────────────────────────────

    def insert(
        self,
        task_id: str,
        lease_id: str,
        worker_id: str,
        execution_id: str,
        attempt_number: int,
        leased_until: float,
    ) -> bool:
        """Insert a new lease. Returns False if task_id already exists."""
        with self._lock:
            with sqlite3.connect(str(self._db_path)) as conn:
                try:
                    conn.execute(
                        """INSERT INTO leases
                           (task_id, lease_id, worker_id, execution_id,
                            attempt_number, status, leased_until)
                           VALUES (?, ?, ?, ?, ?, 'active', ?)""",
                        (task_id, lease_id, worker_id, execution_id,
                         attempt_number, leased_until),
                    )
                    conn.commit()
                    return True
                except sqlite3.IntegrityError:
                    return False

    def get(self, task_id: str) -> Optional[dict]:
        with self._lock:
            with sqlite3.connect(str(self._db_path)) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT * FROM leases WHERE task_id = ?",
                    (task_id,),
                ).fetchone()
                return dict(row) if row else None

    def update_heartbeat(self, task_id: str, lease_id: str,
                         new_deadline: float) -> bool:
        """Update leased_until if lease_id matches, lease is active,
        and has not yet expired (leased_until > now).

        Returns False if the lease doesn't exist, has a different
        lease_id, is no longer active, or has already expired.
        """
        with self._lock:
            with sqlite3.connect(str(self._db_path)) as conn:
                cur = conn.execute(
                    """UPDATE leases SET leased_until = ?
                       WHERE task_id = ? AND lease_id = ?
                       AND status = 'active' AND leased_until > ?""",
                    (new_deadline, task_id, lease_id, time.time()),
                )
                conn.commit()
                return cur.rowcount > 0

    def release(self, task_id: str, lease_id: str) -> bool:
        """Mark a lease as released. Returns False if not found or
        lease_id doesn't match."""
        with self._lock:
            with sqlite3.connect(str(self._db_path)) as conn:
                cur = conn.execute(
                    """UPDATE leases SET status = 'released'
                       WHERE task_id = ? AND lease_id = ?
                       AND status = 'active'""",
                    (task_id, lease_id),
                )
                conn.commit()
                return cur.rowcount > 0

    def find_expired(self) -> List[dict]:
        """Return all active leases past their deadline."""
        with self._lock:
            with sqlite3.connect(str(self._db_path)) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    """SELECT * FROM leases
                       WHERE status = 'active' AND leased_until <= ?""",
                    (time.time(),),
                ).fetchall()
                return [dict(r) for r in rows]

    def expire(self, task_id: str) -> bool:
        """Force-expire a lease (for reassignment)."""
        with self._lock:
            with sqlite3.connect(str(self._db_path)) as conn:
                cur = conn.execute(
                    """UPDATE leases SET status = 'expired'
                       WHERE task_id = ? AND status = 'active'""",
                    (task_id,),
                )
                conn.commit()
                return cur.rowcount > 0

    def owner_of(self, task_id: str) -> Optional[str]:
        """Return the worker_id that currently owns this task's lease,
        or None if not leased."""
        row = self.get(task_id)
        if row is None:
            return None
        if row["status"] != "active":
            return None
        if row["leased_until"] and time.time() >= row["leased_until"]:
            return None
        return row["worker_id"]

    def execution_attempt(self, task_id: str) -> Tuple[str, int]:
        """Return (execution_id, attempt_number) for a task.

        Returns ("", 0) if not found.
        """
        row = self.get(task_id)
        if row is None:
            return ("", 0)
        return (row.get("execution_id", ""), row.get("attempt_number", 0))

    def clear(self) -> None:
        """Remove all leases (for testing)."""
        with self._lock:
            with sqlite3.connect(str(self._db_path)) as conn:
                conn.execute("DELETE FROM leases")
                conn.commit()

    def delete(self, task_id: str) -> bool:
        """Delete a lease row entirely (for re-claiming)."""
        with self._lock:
            with sqlite3.connect(str(self._db_path)) as conn:
                cur = conn.execute(
                    "DELETE FROM leases WHERE task_id = ?",
                    (task_id,),
                )
                conn.commit()
                return cur.rowcount > 0

    def lease_count(self) -> int:
        with self._lock:
            with sqlite3.connect(str(self._db_path)) as conn:
                row = conn.execute("SELECT COUNT(*) AS cnt FROM leases").fetchone()
                return row[0] if row else 0

    def active_count(self) -> int:
        with self._lock:
            with sqlite3.connect(str(self._db_path)) as conn:
                row = conn.execute(
                    "SELECT COUNT(*) AS cnt FROM leases WHERE status = 'active'",
                ).fetchone()
                return row[0] if row else 0


class OwnershipManager:
    """Enforces distributed execution ownership.

    Thread-safe. Delegates persistence to LeaseStore.
    """

    def __init__(
        self,
        lease_store: Optional[LeaseStore] = None,
        default_lease_duration: float = LEASE_DEFAULT_DURATION,
    ):
        self._store = lease_store or LeaseStore()
        self._default_lease_duration = default_lease_duration

    @property
    def version(self) -> str:
        return OWNERSHIP_VERSION

    # ── Core API ────────────────────────────────────────────────

    def claim(
        self,
        task_id: str,
        worker_id: str,
        lease_duration: Optional[float] = None,
        execution_id: str = "",
        attempt_number: int = 0,
    ) -> Optional[str]:
        """Claim exclusive ownership of a task for a worker.

        Args:
            task_id: The task to claim.
            worker_id: The worker claiming the task.
            lease_duration: How long the lease is valid (seconds).
            execution_id: Unique ID for this execution attempt.
            attempt_number: Which attempt (0 = first).

        Returns:
            lease_id (str) on success, or None if already owned.
        """
        duration = lease_duration if lease_duration is not None else self._default_lease_duration
        leased_until = time.time() + duration
        lease_id = str(uuid.uuid4())

        existing = self._store.get(task_id)
        if existing is not None and existing["status"] == "active":
            # Check if existing lease is still valid
            if existing["leased_until"] and time.time() < existing["leased_until"]:
                logger.warning(
                    "Claim failed: task %s already owned by %s (lease %s)",
                    task_id, existing["worker_id"], existing["lease_id"],
                )
                return None
            # Existing lease is expired — expire and remove for re-insert
            self._store.expire(task_id)
            self._store.delete(task_id)
        elif existing is not None:
            # Previously released or expired — remove for re-insert
            self._store.delete(task_id)

        success = self._store.insert(
            task_id=task_id,
            lease_id=lease_id,
            worker_id=worker_id,
            execution_id=execution_id or str(uuid.uuid4()),
            attempt_number=attempt_number,
            leased_until=leased_until,
        )
        if not success:
            # Race condition: another worker claimed it first
            return None
        logger.info(
            "Claimed task %s → worker %s (lease %s, until %.1f)",
            task_id, worker_id, lease_id, leased_until,
        )
        return lease_id

    def renew_lease(self, task_id: str, lease_id: str,
                    lease_duration: Optional[float] = None) -> bool:
        """Extend a lease.

        Returns False if the lease doesn't exist, has expired,
        or the lease_id doesn't match (wrong owner).
        """
        duration = lease_duration if lease_duration is not None else self._default_lease_duration
        new_deadline = time.time() + duration
        return self._store.update_heartbeat(task_id, lease_id, new_deadline)

    def release(self, task_id: str, lease_id: str) -> bool:
        """Voluntarily release ownership.

        Returns False if the task isn't leased by the given lease_id.
        """
        return self._store.release(task_id, lease_id)

    def reassign_expired(
        self, max_tasks: int = 0,
    ) -> List[str]:
        """Find and expire all leases past their deadline.

        Args:
            max_tasks: Max tasks to reassign (0 = unlimited).

        Returns:
            List of task_ids whose leases have been expired.
        """
        expired = self._store.find_expired()
        if max_tasks > 0:
            expired = expired[:max_tasks]
        task_ids = [e["task_id"] for e in expired]
        for task_id in task_ids:
            self._store.expire(task_id)
            logger.info("Reassigned (expired): task %s", task_id)
        return task_ids

    def owner_of(self, task_id: str) -> Optional[str]:
        """Return the current owner worker_id, or None."""
        return self._store.owner_of(task_id)

    def execution_attempt(self, task_id: str) -> Tuple[str, int]:
        """Return (execution_id, attempt_number) for a task."""
        return self._store.execution_attempt(task_id)

    # ── For testing ─────────────────────────────────────────────

    def active_count(self) -> int:
        return self._store.active_count()

    def lease_count(self) -> int:
        return self._store.lease_count()
