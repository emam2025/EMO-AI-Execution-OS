"""Phase F3 — Resource Scheduler & Quota Arbitration.  # LAW-5 # LAW-8 # LAW-10 # LAW-11

Exports:
  - ResourceScheduler:  Resource matching & assignment (←→ IResourceScheduler)
  - QuotaArbitrator:    Quota enforcement (←→ IQuotaArbitrator)
  - FairnessEngine:     Fair share & starvation prevention (←→ IFairnessEngine)
  - TopologyMapper:     Hardware topology mapping (←→ ITopologyMapper)
  - AllocationStateMachine: 8-state allocation machine
  - StarvationHandler:  Priority boost & fallback

Legacy ControlPlane API (merged from the old monolithic scheduler):
  - Priority, ResourceRequirements, SchedulingResult
  - WorkerResource, UserQuota

Ref: Canon LAW 5, LAW 8, LAW 10, LAW 11, RULE 1-5  # RULE-1 # RULE-2 # RULE-3 # RULE-4 # RULE-5
Ref: DEVELOPER.md §15.9
"""

from core.runtime.resource_scheduler.resource_scheduler import (
    FairnessModel,
    Priority,
    PriorityScheduler,
    ResourceRequirements,
    ResourceScheduler,
    SchedulingResult,
    UserQuota,
    WorkerResource,
)
from core.runtime.resource_scheduler.quota_arbitrator import QuotaArbitrator
from core.runtime.resource_scheduler.fairness_engine import FairnessEngine
from core.runtime.resource_scheduler.topology_mapper import TopologyMapper
from core.runtime.resource_scheduler.allocation_state_machine import (
    AllocationStateMachine,
    AllocationState,
)
from core.runtime.resource_scheduler.starvation_handler import StarvationHandler

__all__ = [
    "ResourceScheduler",
    "QuotaArbitrator",
    "FairnessEngine",
    "TopologyMapper",
    "AllocationStateMachine",
    "AllocationState",
    "StarvationHandler",
    "FairnessModel",
    "Priority",
    "PriorityScheduler",
    "ResourceRequirements",
    "SchedulingResult",
    "UserQuota",
    "WorkerResource",
]
