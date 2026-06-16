"""F3 — Resource Scheduler Models.

Pure frozen dataclasses and Enums for the Resource Scheduler.
No business logic, no execution.

Ref: DEVELOPER.md §15.10
Ref: Canon LAW 10, LAW 23
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List


class AllocationStatus(Enum):
    """Resource allocation status."""

    PENDING = "pending"
    ALLOCATED = "allocated"
    REJECTED = "rejected"


@dataclass(frozen=True)
class ResourceRequest:
    """Request for compute resources."""

    execution_id: str
    cpu_cores: float
    memory_mb: int
    priority: int


@dataclass(frozen=True)
class ResourceAllocation:
    """Result of resource allocation."""

    execution_id: str
    worker_id: str
    allocated_cpu: float
    allocated_memory: int
    status: AllocationStatus


@dataclass(frozen=True)
class WorkerQuota:
    """Worker resource quota limits."""

    worker_id: str
    max_cpu: float
    max_memory: int
    current_cpu: float
    current_memory: int
