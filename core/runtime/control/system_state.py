"""GAP 2 — SystemState: global system state controller.

Maintains the authoritative view of the entire runtime system.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class SystemPhase(str, Enum):
    BOOTING = "booting"
    ACTIVE = "active"
    DEGRADED = "degraded"
    RECONCILING = "reconciling"
    SHUTTING_DOWN = "shutting_down"
    FAILED = "failed"


@dataclass
class SystemState:
    """Global system state — the single source of truth for runtime state.

    Thread-safe. Accessed by control plane, health monitor, and orchestrator.
    """
    phase: SystemPhase = SystemPhase.BOOTING
    workers: int = 0
    active_executions: int = 0
    completed_executions: int = 0
    failed_executions: int = 0
    pending_tasks: int = 0
    uptime: float = 0.0
    version: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def __post_init__(self) -> None:
        self._started_at = time.time()

    def get(self, key: str, default: Any = None) -> Any:
        """Get a state attribute by name."""
        return getattr(self, key, default)

    def set(self, key: str, value: Any) -> None:
        """Set a state attribute by name."""
        with self._lock:
            if hasattr(self, key):
                setattr(self, key, value)

    def set_phase(self, phase: SystemPhase) -> None:
        with self._lock:
            self.phase = phase

    def snapshot(self) -> Dict[str, Any]:
        """Return a snapshot of the current system state."""
        with self._lock:
            return {
                "phase": self.phase.value,
                "workers": self.workers,
                "active_executions": self.active_executions,
                "completed_executions": self.completed_executions,
                "failed_executions": self.failed_executions,
                "pending_tasks": self.pending_tasks,
                "uptime": time.time() - self._started_at,
                "version": self.version,
            }

    def increment(self, key: str, amount: int = 1) -> None:
        """Atomically increment a counter attribute."""
        with self._lock:
            current = getattr(self, key, 0)
            setattr(self, key, current + amount)
