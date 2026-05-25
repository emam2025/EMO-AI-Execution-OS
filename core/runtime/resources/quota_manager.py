"""Phase 4.4.2 — QuotaManager: per-execution, per-worker, and global quotas.

Enforces resource budgets before and during execution.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger("emo_ai.resources.quota")


@dataclass
class Quota:
    """Resource quota limits."""
    max_cpu: float = 0.0
    max_memory: int = 0
    max_executions: int = 0
    max_wall_time: float = 0.0
    max_io_bytes: int = 0

    def exceeded_by(self, cpu: float = 0, memory: int = 0,
                    executions: int = 0, wall_time: float = 0,
                    io_bytes: int = 0) -> list[str]:
        """Return list of resources that exceed quota."""
        exceeded = []
        if self.max_cpu > 0 and cpu > self.max_cpu:
            exceeded.append(f"cpu ({cpu:.1f}s > {self.max_cpu}s)")
        if self.max_memory > 0 and memory > self.max_memory:
            exceeded.append(f"memory ({memory} > {self.max_memory})")
        if self.max_executions > 0 and executions > self.max_executions:
            exceeded.append(f"executions ({executions} > {self.max_executions})")
        if self.max_wall_time > 0 and wall_time > self.max_wall_time:
            exceeded.append(f"wall_time ({wall_time:.1f}s > {self.max_wall_time}s)")
        if self.max_io_bytes > 0 and io_bytes > self.max_io_bytes:
            exceeded.append(f"io_bytes ({io_bytes} > {self.max_io_bytes})")
        return exceeded


class QuotaExceeded(Exception):
    """Raised when a quota is exceeded."""

    def __init__(self, scope: str, resources: list[str]):
        self.scope = scope
        self.resources = resources
        super().__init__(f"Quota exceeded [{scope}]: {', '.join(resources)}")


class QuotaManager:
    """Manages quotas at execution, worker, and global scope.

    Usage:
        qm = QuotaManager()
        qm.set_global_quota(Quota(max_cpu=60.0, max_executions=100))
        qm.check("execution:123", cpu=5.0)
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._global_quota = Quota()
        self._worker_quotas: Dict[str, Quota] = {}
        self._execution_quotas: Dict[str, Quota] = {}

        # Accumulated usage per scope
        self._usage: Dict[str, Dict[str, float]] = {}

    def set_global_quota(self, quota: Quota) -> None:
        """Set the global resource quota."""
        with self._lock:
            self._global_quota = quota

    def set_worker_quota(self, worker_id: str, quota: Quota) -> None:
        """Set a quota for a specific worker."""
        with self._lock:
            self._worker_quotas[worker_id] = quota

    def set_execution_quota(self, execution_id: str, quota: Quota) -> None:
        """Set a quota for a specific execution."""
        with self._lock:
            self._execution_quotas[execution_id] = quota

    def record_usage(self, scope: str, cpu: float = 0,
                     memory: int = 0, wall_time: float = 0,
                     io_bytes: int = 0) -> None:
        """Record resource usage against a scope."""
        with self._lock:
            if scope not in self._usage:
                self._usage[scope] = {
                    "cpu": 0.0, "memory": 0, "wall_time": 0.0, "io_bytes": 0,
                }
            u = self._usage[scope]
            u["cpu"] += cpu
            u["memory"] += memory
            u["wall_time"] += wall_time
            u["io_bytes"] += io_bytes

    def check(self, scope: str, cpu: float = 0, memory: int = 0,
              wall_time: float = 0, io_bytes: int = 0) -> None:
        """Check if an operation is within quota.

        Checks execution → worker → global (most specific first).

        Raises QuotaExceeded if any quota is breached.
        """
        with self._lock:
            usage = self._usage.get(scope, {})
            used_cpu = usage.get("cpu", 0) + cpu
            used_memory = usage.get("memory", 0) + memory
            used_wall = usage.get("wall_time", 0) + wall_time
            used_io = usage.get("io_bytes", 0) + io_bytes

            execution_quota = self._execution_quotas.get(scope)
            if execution_quota:
                exceeded = execution_quota.exceeded_by(
                    cpu=used_cpu, memory=used_memory,
                    wall_time=used_wall, io_bytes=used_io,
                )
                if exceeded:
                    raise QuotaExceeded(f"execution:{scope}", exceeded)

            worker_id = self._resolve_worker(scope)
            if worker_id and worker_id in self._worker_quotas:
                wq = self._worker_quotas[worker_id]
                w_usage = self._usage.get(f"worker:{worker_id}", {})
                w_cpu = w_usage.get("cpu", 0) + cpu
                w_mem = w_usage.get("memory", 0) + memory
                w_wall = w_usage.get("wall_time", 0) + wall_time
                exceeded = wq.exceeded_by(
                    cpu=w_cpu, memory=w_mem,
                    wall_time=w_wall,
                )
                if exceeded:
                    raise QuotaExceeded(f"worker:{worker_id}", exceeded)

            if self._global_quota:
                g_usage = self._usage.get("_global", {})
                g_cpu = g_usage.get("cpu", 0) + cpu
                g_mem = g_usage.get("memory", 0) + memory
                g_wall = g_usage.get("wall_time", 0) + wall_time
                exceeded = self._global_quota.exceeded_by(
                    cpu=g_cpu, memory=g_mem,
                    wall_time=g_wall,
                )
                if exceeded:
                    raise QuotaExceeded("global", exceeded)

    @staticmethod
    def _resolve_worker(scope: str) -> Optional[str]:
        if scope.startswith("worker:"):
            return scope[7:]
        if scope.startswith("execution:"):
            return None
        return None
