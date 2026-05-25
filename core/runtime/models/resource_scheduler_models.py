"""Phase F3 — Resource Scheduler & Quota Arbitration: Runtime Models.

Mirrors artifacts/design/f3/models/02_resource_and_quota_models.py
for runtime importability.

Ref: Canon LAW 5, LAW 8, LAW 10, LAW 11
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class PriorityTier(str, Enum):  # LAW-8
    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"
    BATCH = "batch"


class SchedulingStatus(str, Enum):  # LAW-8
    ASSIGNED = "assigned"
    QUEUED = "queued"
    PREEMPTED = "preempted"
    REJECTED = "rejected"


class QuotaType(str, Enum):  # LAW-10
    EXECUTION = "execution"
    WORKER = "worker"
    GLOBAL = "global"


class HardwareCapability(str, Enum):  # LAW-10
    CPU_INTENSIVE = "cpu_intensive"
    MEMORY_INTENSIVE = "memory_intensive"
    GPU_AVAILABLE = "gpu_available"
    HIGH_IO = "high_io"
    NETWORK_LOCAL = "network_local"


@dataclass
class ResourceRequest:  # LAW-5
    execution_id: str = ""
    dag_id: str = ""
    cpu_cores: float = 1.0
    memory_mb: int = 512
    gpu_memory_mb: int = 0
    io_bandwidth: str = "standard"
    network_access: bool = False
    priority: PriorityTier = PriorityTier.NORMAL
    preemptible: bool = False
    max_wait_sec: float = 300.0


@dataclass
class ResourceOffer:  # LAW-11
    worker_id: str = ""
    available_cpu: float = 0.0
    available_mem: int = 0
    hardware_topology: List[HardwareCapability] = field(default_factory=list)
    affinity_tags: List[str] = field(default_factory=list)
    total_cpu: float = 0.0
    total_mem: int = 0


@dataclass
class QuotaPolicy:  # LAW-10
    type: QuotaType = QuotaType.EXECUTION
    limit: float = 100.0
    soft_limit: float = 80.0
    hard_limit: float = 100.0
    cooldown_sec: float = 60.0


@dataclass
class SchedulingDecision:  # LAW-8
    status: SchedulingStatus = SchedulingStatus.QUEUED
    reason: str = ""
    assigned_worker: str = ""
    timestamp: float = 0.0
    preempted_id: str = ""


@dataclass
class QuotaUsage:  # LAW-5
    execution_id: str = ""
    cpu_used: float = 0.0
    mem_used: int = 0
    gpu_used: int = 0
    io_used: str = ""
    percentage: float = 0.0


@dataclass
class FairShareSnapshot:  # LAW-8
    worker_id: str = ""
    fair_cpu: float = 0.0
    fair_mem: int = 0
    current_cpu: float = 0.0
    current_mem: int = 0
    imbalance_ratio: float = 0.0
    boosted: bool = False


@dataclass
class StarvationReport:  # LAW-8
    execution_id: str = ""
    wait_time_sec: float = 0.0
    priority: PriorityTier = PriorityTier.NORMAL
    boost_applied: bool = False
    new_priority: PriorityTier = PriorityTier.NORMAL
    action_taken: str = ""


@dataclass
class TopologyMapping:  # LAW-10
    worker_id: str = ""
    score: float = 0.0
    matched_capabilities: List[HardwareCapability] = field(default_factory=list)
    fallback_suggested: bool = False
    fallback_worker: str = ""


@dataclass
class AssignmentRecord:  # LAW-11
    execution_id: str = ""
    worker_id: str = ""
    resources: Optional[ResourceRequest] = None
    assigned_at: float = 0.0
    preemptible: bool = False
    checkpoint_available: bool = False
