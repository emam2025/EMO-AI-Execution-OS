"""Phase 4.4.1 — ResourceTracker: CPU/memory tracking for executions.

Tracks resource usage per execution and provides telemetry
for quota enforcement.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger("emo_ai.resources.tracker")


@dataclass
class ResourceUsage:
    """Resource usage snapshot for an execution."""
    execution_id: str = ""
    tool: str = ""
    cpu_time: float = 0.0
    memory_bytes: int = 0
    wall_time: float = 0.0
    io_operations: int = 0
    io_bytes: int = 0
    started_at: float = 0.0
    completed_at: float = 0.0


class ResourceTracker:
    """Tracks resource usage across executions.

    Thread-safe. Accumulates telemetry for analytics and enforcement.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._usages: Dict[str, ResourceUsage] = {}
        self._current: Dict[str, ResourceUsage] = {}

    def start_execution(
        self,
        execution_id: str,
        tool: str,
    ) -> None:
        """Record the start of an execution."""
        usage = ResourceUsage(
            execution_id=execution_id,
            tool=tool,
            started_at=time.time(),
        )
        with self._lock:
            self._current[execution_id] = usage

    def update(
        self,
        execution_id: str,
        cpu_time: Optional[float] = None,
        memory_bytes: Optional[int] = None,
        io_operations: Optional[int] = None,
        io_bytes: Optional[int] = None,
    ) -> None:
        """Update resource usage for an active execution."""
        with self._lock:
            usage = self._current.get(execution_id)
            if usage is None:
                return
            if cpu_time is not None:
                usage.cpu_time = cpu_time
            if memory_bytes is not None:
                usage.memory_bytes = memory_bytes
            if io_operations is not None:
                usage.io_operations = io_operations
            if io_bytes is not None:
                usage.io_bytes = io_bytes
            usage.wall_time = time.time() - usage.started_at

    def complete_execution(self, execution_id: str) -> Optional[ResourceUsage]:
        """Finalize and archive execution tracking."""
        with self._lock:
            usage = self._current.pop(execution_id, None)
            if usage is None:
                return None
            usage.completed_at = time.time()
            usage.wall_time = usage.completed_at - usage.started_at
            self._usages[execution_id] = usage
            return usage

    def get_usage(self, execution_id: str) -> Optional[ResourceUsage]:
        """Get resource usage for a completed execution."""
        with self._lock:
            return self._usages.get(execution_id)

    def get_active(self, execution_id: str) -> Optional[ResourceUsage]:
        """Get resource usage for an active execution."""
        with self._lock:
            return self._current.get(execution_id)

    def active_count(self) -> int:
        """Return the number of active executions."""
        with self._lock:
            return len(self._current)

    def total_cpu(self) -> float:
        """Return total CPU time across all completed executions."""
        with self._lock:
            return sum(u.cpu_time for u in self._usages.values())

    def recent_usage(self, limit: int = 100) -> list[ResourceUsage]:
        """Return the most recent completed executions."""
        with self._lock:
            sorted_usages = sorted(
                self._usages.values(),
                key=lambda u: u.completed_at,
                reverse=True,
            )
            return sorted_usages[:limit]
