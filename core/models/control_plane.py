"""F2 — Control Plane Models.

Pure frozen dataclasses and Enums for the Control Plane.
No business logic, no execution.

Ref: DEVELOPER.md §15.10
Ref: Canon LAW 10, LAW 23
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List


class WorkerStatus(Enum):
    """Worker health status."""

    ONLINE = "online"
    OFFLINE = "offline"
    DRAINING = "draining"
    UNHEALTHY = "unhealthy"


@dataclass(frozen=True)
class ClusterState:
    """Immutable snapshot of cluster state."""

    active_workers: int
    pending_tasks: int
    total_capacity: int


@dataclass(frozen=True)
class ReconciliationAction:
    """Immutable action to reconcile desired vs actual state."""

    action_type: str
    target_id: str
    reason: str
