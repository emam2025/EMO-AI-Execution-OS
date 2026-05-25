"""Phase F3 — Resource Scheduler & Quota Arbitration: Formal Protocol Definitions.

This file defines 4 typing.Protocol classes that form the contract
for the Phase F3 Resource Scheduler architecture:

  1. IResourceScheduler   — Resource matching & assignment
  2. IQuotaArbitrator      — Quota enforcement per execution/worker/global
  3. IFairnessEngine       — Fair share, starvation prevention, priority boost
  4. ITopologyMapper       — Hardware topology-aware resource mapping

All protocols follow ROADMAP Phase F3 and DEVELOPER.md §15.9.

Ref: Canon LAW 5 (Observability), LAW 8 (Fairness), LAW 10 (Resource limits),
     LAW 11 (No global state)
Ref: RULE 1 (Determinism), RULE 2 (Reversibility), RULE 3 (Recoverability),
     RULE 4 (Terminal states), RULE 5 (Idempotency)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


# ════════════════════════════════════════════════════════════════════
# Shared types (must match models/02_resource_and_quota_models.py)
# ════════════════════════════════════════════════════════════════════


class PriorityTier(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"
    BATCH = "batch"


class SchedulingStatus(str, Enum):
    ASSIGNED = "assigned"
    QUEUED = "queued"
    PREEMPTED = "preempted"
    REJECTED = "rejected"


class QuotaType(str, Enum):
    EXECUTION = "execution"
    WORKER = "worker"
    GLOBAL = "global"


class HardwareCapability(str, Enum):
    CPU_INTENSIVE = "cpu_intensive"
    MEMORY_INTENSIVE = "memory_intensive"
    GPU_AVAILABLE = "gpu_available"
    HIGH_IO = "high_io"
    NETWORK_LOCAL = "network_local"


@dataclass
class ResourceRequest:
    """Resource requirements for an execution or task."""
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
    """Available resources on a worker node."""
    worker_id: str = ""
    available_cpu: float = 0.0
    available_mem: int = 0
    hardware_topology: List[HardwareCapability] = field(default_factory=list)
    affinity_tags: List[str] = field(default_factory=list)
    total_cpu: float = 0.0
    total_mem: int = 0


@dataclass
class QuotaPolicy:
    """Quota policy for resource consumption control."""
    type: QuotaType = QuotaType.EXECUTION
    limit: float = 100.0
    soft_limit: float = 80.0
    hard_limit: float = 100.0
    cooldown_sec: float = 60.0


@dataclass
class SchedulingDecision:
    """Decision produced by the resource scheduler."""
    status: SchedulingStatus = SchedulingStatus.QUEUED
    reason: str = ""
    assigned_worker: str = ""
    timestamp: float = 0.0
    preempted_id: str = ""


@dataclass
class QuotaUsage:
    """Current quota consumption snapshot."""
    execution_id: str = ""
    cpu_used: float = 0.0
    mem_used: int = 0
    gpu_used: int = 0
    io_used: str = ""
    percentage: float = 0.0


@dataclass
class FairShareSnapshot:
    """Fair share computation result."""
    worker_id: str = ""
    fair_cpu: float = 0.0
    fair_mem: int = 0
    current_cpu: float = 0.0
    current_mem: int = 0
    imbalance_ratio: float = 0.0
    boosted: bool = False


@dataclass
class StarvationReport:
    """Report of a detected starvation condition."""
    execution_id: str = ""
    wait_time_sec: float = 0.0
    priority: PriorityTier = PriorityTier.NORMAL
    boost_applied: bool = False
    new_priority: PriorityTier = PriorityTier.NORMAL
    action_taken: str = ""


@dataclass
class TopologyMapping:
    """Result of hardware topology mapping."""
    worker_id: str = ""
    score: float = 0.0
    matched_capabilities: List[HardwareCapability] = field(default_factory=list)
    fallback_suggested: bool = False
    fallback_worker: str = ""


# ════════════════════════════════════════════════════════════════════
# 1. IResourceScheduler
# ════════════════════════════════════════════════════════════════════


@runtime_checkable
class IResourceScheduler(Protocol):
    """Matches resource requests to available workers.

    LAW 5: All scheduling decisions observable.
    LAW 8: Fair distribution across workers.
    LAW 11: No global state — per-instance resource tracking.
    RULE 1: Deterministic matching (same request + offers → same decision).
    """

    def match_resources(
        self,
        request: ResourceRequest,
        available_offers: List[ResourceOffer],
    ) -> SchedulingDecision:
        """Match a resource request against available offers.

        Algorithm:
          1. Filter offers by minimum resource requirements
          2. Score remaining offers by topology affinity
          3. Select highest-scored offer
          4. If none match → QUEUED or REJECTED

        Args:
            request: Resource requirements.
            available_offers: List of available worker offers.

        Returns:
            SchedulingDecision with status and assigned worker.
        """
        ...

    def assign_worker(
        self,
        assignment: SchedulingDecision,
        offer: ResourceOffer,
    ) -> bool:
        """Assign a worker to an execution.

        Consumes resources from the offer and binds the execution.

        Args:
            assignment: Confirmed scheduling decision.
            offer: The matched resource offer.

        Returns:
            True if assignment succeeded.
        """
        ...

    def preempt_if_needed(
        self,
        request: ResourceRequest,
        active_assignments: List[SchedulingDecision],
    ) -> Optional[SchedulingDecision]:
        """Preempt a lower-priority execution if resources are needed.

        Preemption guards:
          - request.priority >= HIGH
          - Target execution priority <= LOW
          - Target age > 60s
          - Priority difference ≥ 2 tiers
          - Graceful checkpoint available

        Args:
            request: High-priority resource request.
            active_assignments: Currently assigned executions.

        Returns:
            Preemption decision or None.
        """
        ...

    def release_resources(
        self,
        execution_id: str,
        assignment: SchedulingDecision,
    ) -> bool:
        """Release resources assigned to an execution.

        Refunds quota and updates available offers.

        Args:
            execution_id: Execution that completed or was preempted.
            assignment: Original scheduling decision.

        Returns:
            True if resources were released.
        """
        ...


# ════════════════════════════════════════════════════════════════════
# 2. IQuotaArbitrator
# ════════════════════════════════════════════════════════════════════


@runtime_checkable
class IQuotaArbitrator(Protocol):
    """Enforces resource quotas at execution, worker, and global levels.

    LAW 10: Resource limits MUST be enforced.
    LAW 11: No global mutable state — quota state per-instance.
    RULE 5: All quota operations are idempotent.
    """

    def check_quota(
        self,
        execution_id: str,
        request: ResourceRequest,
        policy: QuotaPolicy,
    ) -> bool:
        """Check if an execution has quota available.

        Evaluates against:
          - execution-level soft/hard limit
          - worker-level cumulative usage
          - global pool remaining

        Args:
            execution_id: Target execution.
            request: Resource request to check.
            policy: Active quota policy.

        Returns:
            True if quota is available.
        """
        ...

    def consume_usage(
        self,
        execution_id: str,
        request: ResourceRequest,
    ) -> QuotaUsage:
        """Record resource consumption for an execution.

        Args:
            execution_id: Target execution.
            request: Resources consumed.

        Returns:
            QuotaUsage after consumption.
        """
        ...

    def enforce_limit(
        self,
        execution_id: str,
        usage: QuotaUsage,
        policy: QuotaPolicy,
    ) -> bool:
        """Enforce a quota limit — throttle or reject if exceeded.

        Actions:
          - usage < soft_limit: allow
          - soft_limit <= usage < hard_limit: warn, allow
          - usage >= hard_limit: reject

        Args:
            execution_id: Target execution.
            usage: Current usage snapshot.
            policy: Active quota policy.

        Returns:
            True if limit not exceeded.
        """
        ...

    def refund_on_failure(
        self,
        execution_id: str,
        usage: QuotaUsage,
    ) -> QuotaUsage:
        """Refund quota after a failed execution.

        RULE 2 (Reversibility): Resource consumption is reversible.
        RULE 3 (Recoverability): Failed executions must not leak quota.

        Args:
            execution_id: Failed execution.
            usage: Previously consumed usage.

        Returns:
            Updated QuotaUsage after refund.
        """
        ...


# ════════════════════════════════════════════════════════════════════
# 3. IFairnessEngine
# ════════════════════════════════════════════════════════════════════


@runtime_checkable
class IFairnessEngine(Protocol):
    """Ensures fair resource distribution and prevents starvation.

    LAW 8: Resources MUST be distributed fairly.
    LAW 11: No global state — per-instance fairness tracking.
    RULE 1: Deterministic fair share computation.
    """

    def compute_fair_share(
        self,
        worker_id: str,
        total_resources: ResourceOffer,
        active_executions: int,
    ) -> FairShareSnapshot:
        """Compute the fair share of resources for a worker.

        Formula:
          fair_cpu = total_cpu / max(1, active_executions)
          fair_mem = total_mem / max(1, active_executions)

        Args:
            worker_id: Target worker.
            total_resources: Total available on the worker.
            active_executions: Number of active executions.

        Returns:
            FairShareSnapshot with fair vs current allocation.
        """
        ...

    def detect_starvation(
        self,
        execution_id: str,
        wait_time_sec: float,
        current_priority: PriorityTier,
        starvation_threshold: float = 120.0,
    ) -> StarvationReport:
        """Detect if an execution is being starved.

        Starvation condition:
          wait_time > threshold AND priority is LOW or BATCH

        Args:
            execution_id: Target execution.
            wait_time_sec: Time since request submitted.
            current_priority: Current priority tier.
            starvation_threshold: Max acceptable wait in seconds.

        Returns:
            StarvationReport with boost info.
        """
        ...

    def apply_priority_boost(
        self,
        report: StarvationReport,
    ) -> PriorityTier:
        """Apply a priority boost to a starved execution.

        Boost rules:
          BATCH → LOW
          LOW → NORMAL
          NORMAL → HIGH
          HIGH and CRITICAL → no boost (already high)

        Args:
            report: Starvation report from detect_starvation().

        Returns:
            New priority tier after boost.
        """
        ...

    def balance_load(
        self,
        offers: List[ResourceOffer],
        metrics: List[FairShareSnapshot],
    ) -> List[ResourceOffer]:
        """Suggest load rebalancing across workers.

        Returns offers sorted by imbalance_ratio ascending
        (least loaded first) to guide scheduling toward balance.

        Args:
            offers: Current resource offers per worker.
            metrics: Fair share snapshots per worker.

        Returns:
            Rebalanced offers list, least loaded first.
        """
        ...


# ════════════════════════════════════════════════════════════════════
# 4. ITopologyMapper
# ════════════════════════════════════════════════════════════════════


@runtime_checkable
class ITopologyMapper(Protocol):
    """Maps resource requests to hardware topology-aware workers.

    Considers CPU architecture, GPU availability, memory NUMA,
    IO bandwidth, and network locality.

    LAW 10: Resource constraints MUST be validated.
    RULE 1: Deterministic mapping.
    """

    def map_to_hardware(
        self,
        request: ResourceRequest,
        offers: List[ResourceOffer],
    ) -> TopologyMapping:
        """Map a request to the best hardware match.

        Scoring:
          +1.0 per matched HardwareCapability
          +0.5 per matched affinity_tag
          -1.0 if capability explicitly required but missing

        Args:
            request: Resource requirements.
            offers: Available worker offers.

        Returns:
            TopologyMapping with score and matched capabilities.
        """
        ...

    def check_affinity(
        self,
        request: ResourceRequest,
        offer: ResourceOffer,
    ) -> bool:
        """Check if a request has affinity with a worker.

        Affinity is based on:
          - Previously executed DAG segments on same worker
          - Co-located data dependencies

        Args:
            request: Resource request.
            offer: Resource offer to check.

        Returns:
            True if affinity match.
        """
        ...

    def validate_constraints(
        self,
        request: ResourceRequest,
        offer: ResourceOffer,
    ) -> List[str]:
        """Validate hardware constraints between request and offer.

        Returns list of constraint violation messages.
        Empty list = all constraints satisfied.

        Args:
            request: Resource request.
            offer: Resource offer.

        Returns:
            List of constraint violation messages.
        """
        ...

    def suggest_fallback(
        self,
        request: ResourceRequest,
        offers: List[ResourceOffer],
    ) -> Optional[ResourceOffer]:
        """Suggest a fallback worker when primary mapping fails.

        Fallback relaxes:
          - HardwareCapability requirements (GPU → CPU fallback)
          - Affinity constraints (any worker with enough resources)

        Args:
            request: Resource requirements.
            offers: Available offers.

        Returns:
            Fallback ResourceOffer or None.
        """
        ...
