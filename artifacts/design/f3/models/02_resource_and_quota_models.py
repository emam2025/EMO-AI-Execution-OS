"""Phase F3 — Resource Scheduler & Quota Arbitration: Resource & Policy Models.

This file defines all data models and enums referenced by the four
F3 protocols in protocols/01_resource_protocols.py:

  - ResourceRequest:     CPU, memory, GPU, IO bandwidth, network
  - ResourceOffer:       Worker-side available capacity + topology
  - QuotaPolicy:         Execution/Worker/Global limits with soft/hard
  - PriorityTier:        CRITICAL, HIGH, NORMAL, LOW, BATCH
  - SchedulingDecision:  ASSIGNED / QUEUED / PREEMPTED / REJECTED
  - FairShareSnapshot, StarvationReport, TopologyMapping, etc.

Ref: Canon LAW 5, LAW 8, LAW 10, LAW 11
Ref: DEVELOPER.md §15.9
Ref: ROADMAP Phase F3 — Resource Scheduler Models
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# ════════════════════════════════════════════════════════════════════
# Enums
# ════════════════════════════════════════════════════════════════════


class PriorityTier(str, Enum):
    """Priority tiers for resource scheduling.

    CRITICAL: System-level operations — highest priority, can preempt.
    HIGH:     User-facing operations with SLAs.
    NORMAL:   Standard operations.
    LOW:      Background operations — preemptible.
    BATCH:    Bulk processing — lowest priority, preemptible by default.
    """
    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"
    BATCH = "batch"


class SchedulingStatus(str, Enum):
    """Status of a scheduling decision."""
    ASSIGNED = "assigned"
    QUEUED = "queued"
    PREEMPTED = "preempted"
    REJECTED = "rejected"


class QuotaType(str, Enum):
    """Scope of a quota policy."""
    EXECUTION = "execution"
    WORKER = "worker"
    GLOBAL = "global"


class HardwareCapability(str, Enum):
    """Hardware capability tags for topology-aware mapping."""
    CPU_INTENSIVE = "cpu_intensive"
    MEMORY_INTENSIVE = "memory_intensive"
    GPU_AVAILABLE = "gpu_available"
    HIGH_IO = "high_io"
    NETWORK_LOCAL = "network_local"


class ResourceContentionLevel(str, Enum):
    """Resource contention classification."""
    NONE = "none"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


# ════════════════════════════════════════════════════════════════════
# Resource Request & Offer Models
# ════════════════════════════════════════════════════════════════════


@dataclass
class ResourceRequest:
    """Resource requirements for an execution or task.

    Fields:
      execution_id:   Unique execution identifier.
      dag_id:         DAG identifier for the execution.
      cpu_cores:      Required CPU cores (fractional allowed).
      memory_mb:      Required memory in megabytes.
      gpu_memory_mb:  Required GPU memory in megabytes (0 = no GPU).
      io_bandwidth:   IO bandwidth class: "standard", "high", "dedicated".
      network_access: Whether dedicated network access is required.
      priority:       Priority tier for scheduling.
      preemptible:    True if execution can be preempted.
      max_wait_sec:   Maximum time the request can wait in queue.
    """
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
class ResourceOffer:
    """Available resources on a worker node.

    Fields:
      worker_id:          Unique worker identifier.
      available_cpu:      Currently available CPU cores.
      available_mem:      Currently available memory in MB.
      hardware_topology:  List of hardware capabilities on this worker.
      affinity_tags:      Tags for affinity matching.
      total_cpu:          Total CPU cores on the worker.
      total_mem:          Total memory on the worker in MB.
    """
    worker_id: str = ""
    available_cpu: float = 0.0
    available_mem: int = 0
    hardware_topology: List[HardwareCapability] = field(default_factory=list)
    affinity_tags: List[str] = field(default_factory=list)
    total_cpu: float = 0.0
    total_mem: int = 0


# ════════════════════════════════════════════════════════════════════
# Quota & Policy Models
# ════════════════════════════════════════════════════════════════════


@dataclass
class QuotaPolicy:
    """Quota policy for resource consumption control.

    Fields:
      type:         Scope: EXECUTION, WORKER, or GLOBAL.
      limit:        Absolute resource limit.
      soft_limit:   Threshold for warning (as percentage of limit).
      hard_limit:   Hard enforcement threshold (as percentage of limit).
      cooldown_sec: Seconds to enforce cooldown after hard limit hit.
    """
    type: QuotaType = QuotaType.EXECUTION
    limit: float = 100.0
    soft_limit: float = 80.0
    hard_limit: float = 100.0
    cooldown_sec: float = 60.0


@dataclass
class QuotaUsage:
    """Snapshot of current quota consumption.

    Fields:
      execution_id: Execution identifier.
      cpu_used:     CPU cores consumed.
      mem_used:     Memory in MB consumed.
      gpu_used:     GPU memory in MB consumed.
      io_used:      IO bandwidth class consumed.
      percentage:   Usage as percentage of hard_limit.
    """
    execution_id: str = ""
    cpu_used: float = 0.0
    mem_used: int = 0
    gpu_used: int = 0
    io_used: str = ""
    percentage: float = 0.0


@dataclass
class QuotaPool:
    """Global or per-worker quota pool state.

    Fields:
      pool_id:           Unique pool identifier.
      type:              Pool scope.
      total_reserved:    Total resources reserved.
      total_consumed:    Total resources consumed.
      soft_limit_usage:  Usage at soft limit threshold.
      cooldown_active:   True if cooldown is active.
      cooldown_until:    Timestamp when cooldown expires.
    """
    pool_id: str = ""
    type: QuotaType = QuotaType.GLOBAL
    total_reserved: float = 0.0
    total_consumed: float = 0.0
    soft_limit_usage: float = 0.0
    cooldown_active: bool = False
    cooldown_until: float = 0.0


# ════════════════════════════════════════════════════════════════════
# Scheduling Decision Models
# ════════════════════════════════════════════════════════════════════


@dataclass
class SchedulingDecision:
    """Decision produced by the resource scheduler after matching.

    Fields:
      status:           ASSIGNED, QUEUED, PREEMPTED, or REJECTED.
      reason:           Human-readable reason for the decision.
      assigned_worker:  Worker assigned (empty if not assigned).
      timestamp:        Decision timestamp.
      preempted_id:     Execution ID that was preempted (if any).
    """
    status: SchedulingStatus = SchedulingStatus.QUEUED
    reason: str = ""
    assigned_worker: str = ""
    timestamp: float = 0.0
    preempted_id: str = ""


@dataclass
class AssignmentRecord:
    """Record of an active resource assignment.

    Fields:
      execution_id:  Execution identifier.
      worker_id:     Assigned worker identifier.
      resources:     ResourceRequest that was fulfilled.
      assigned_at:   Assignment timestamp.
      preemptible:   Whether this assignment can be preempted.
      checkpoint_available: Whether a graceful checkpoint exists.
    """
    execution_id: str = ""
    worker_id: str = ""
    resources: Optional[ResourceRequest] = None
    assigned_at: float = 0.0
    preemptible: bool = False
    checkpoint_available: bool = False


# ════════════════════════════════════════════════════════════════════
# Fairness & Starvation Models
# ════════════════════════════════════════════════════════════════════


@dataclass
class FairShareSnapshot:
    """Result of a fair share computation for a worker.

    Fields:
      worker_id:       Worker identifier.
      fair_cpu:        Fair share of CPU for each execution.
      fair_mem:        Fair share of memory for each execution.
      current_cpu:     Current CPU allocated.
      current_mem:     Current memory allocated.
      imbalance_ratio: Ratio of current / fair (>1 = overallocated).
      boosted:         True if this worker received a priority boost.
    """
    worker_id: str = ""
    fair_cpu: float = 0.0
    fair_mem: int = 0
    current_cpu: float = 0.0
    current_mem: int = 0
    imbalance_ratio: float = 0.0
    boosted: bool = False


@dataclass
class StarvationReport:
    """Report produced when an execution is detected as starved.

    Fields:
      execution_id:   Starved execution identifier.
      wait_time_sec:  Time the execution has been waiting.
      priority:       Current priority tier.
      boost_applied:  Whether a priority boost has been applied.
      new_priority:   Priority tier after boost.
      action_taken:   Description of the action taken.
    """
    execution_id: str = ""
    wait_time_sec: float = 0.0
    priority: PriorityTier = PriorityTier.NORMAL
    boost_applied: bool = False
    new_priority: PriorityTier = PriorityTier.NORMAL
    action_taken: str = ""


# ════════════════════════════════════════════════════════════════════
# Topology Mapping Models
# ════════════════════════════════════════════════════════════════════


@dataclass
class TopologyMapping:
    """Result of topology-aware resource mapping.

    Fields:
      worker_id:            Mapped worker.
      score:                Mapping score (higher = better match).
      matched_capabilities: List of capabilities that matched.
      fallback_suggested:   True if fallback was used.
      fallback_worker:      Fallback worker identifier (if any).
    """
    worker_id: str = ""
    score: float = 0.0
    matched_capabilities: List[HardwareCapability] = field(default_factory=list)
    fallback_suggested: bool = False
    fallback_worker: str = ""


@dataclass
class ConstraintViolation:
    """A single constraint violation during topology validation.

    Fields:
      constraint:  Name of the violated constraint.
      requested:   Value that was requested.
      available:   Value that is available.
      severity:    Severity of the violation.
    """
    constraint: str = ""
    requested: str = ""
    available: str = ""
    severity: ResourceContentionLevel = ResourceContentionLevel.NONE
