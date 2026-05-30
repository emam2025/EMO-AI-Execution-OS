"""Distributed Execution Types — worker node model for the DAG runtime.

Architecture:
    WorkerRegistry
        └── WorkerNode (self-describing compute node)
                ├── id, url, status
                ├── tools: List[ToolSpec]  (capability advertisement)
                ├── capacity, current_load (scheduling inputs)
                └── last_heartbeat         (liveness)

    DistributedScheduler
        └── TaskAssignment (one unit of work on one worker)
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from .models.dag import ToolSpec

# ═══════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════

WORKER_HEARTBEAT_INTERVAL: float = 30.0  # seconds between heartbeats
WORKER_TIMEOUT: float = 90.0            # seconds before considered offline
DISTRIBUTED_VERSION: str = "1.0.0"


# ═══════════════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════════════

class WorkerStatus(str, Enum):
    IDLE = "idle"
    BUSY = "busy"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


# ═══════════════════════════════════════════════════════════════════
# Data models
# ═══════════════════════════════════════════════════════════════════

@dataclass
class WorkerNode:
    """A self-describing compute node in the distributed cluster.

    Each worker advertises:
      - which tools it can execute (capabilities)
      - its current capacity and load (for scheduling)
      - its health status and version (for compatibility)
    """
    id: str
    url: str                              # base URL for remote execution
    status: WorkerStatus = WorkerStatus.IDLE
    tools: List[ToolSpec] = field(default_factory=list)
    capacity: int = 1                     # max parallel tasks
    current_load: int = 0                 # currently running tasks
    version: str = DISTRIBUTED_VERSION
    last_heartbeat: float = field(default_factory=time.time)
    tags: Dict[str, str] = field(default_factory=dict)

    @property
    def available_capacity(self) -> int:
        return max(0, self.capacity - self.current_load)

    @property
    def is_available(self) -> bool:
        return (
            self.status == WorkerStatus.IDLE
            and self.available_capacity > 0
        )

    def supports_tool(self, tool_name: str) -> bool:
        return any(spec.name == tool_name for spec in self.tools)

    def can_execute(self, tool_name: str, tool_version: str = "") -> bool:
        """Check capability *and* version compatibility."""
        return any(
            spec.name == tool_name
            and (not tool_version or getattr(spec.contract, "version", "") == tool_version)
            for spec in self.tools
        )


@dataclass
class TaskAssignment:
    """One unit of work scheduled on a specific worker."""
    task_id: str
    tool: str
    inputs: Dict[str, Any]
    worker_id: str
    status: TaskStatus = TaskStatus.PENDING

    # ── Lease / Ownership ──────────────────────────────────────
    lease_id: str = ""
    leased_until: Optional[float] = None       # UNIX timestamp
    heartbeat_deadline: Optional[float] = None

    # ── Idempotent execution ───────────────────────────────────
    execution_id: str = ""                       # unique per attempt
    attempt_number: int = 0                     # 0 = first attempt

    # ── Results ────────────────────────────────────────────────
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    started_at: Optional[float] = None
    completed_at: Optional[float] = None

    @property
    def is_leased(self) -> bool:
        return self.lease_id != "" and (
            self.leased_until is None or time.time() < self.leased_until
        )

    @property
    def is_expired(self) -> bool:
        return (
            self.lease_id != ""
            and self.leased_until is not None
            and time.time() >= self.leased_until
        )
