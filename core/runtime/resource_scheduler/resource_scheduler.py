"""Phase F3 — Resource Scheduler implementation.  # LAW-5 # LAW-8 # LAW-11

Implements IResourceScheduler: match_resources, assign_worker,
preempt_if_needed, release_resources.

Coordinates QuotaArbitrator, FairnessEngine, TopologyMapper,
AllocationStateMachine, and StarvationHandler.

Ref: Canon LAW 5 (Observability), LAW 8 (Fairness), LAW 11 (No global state)
"""

from __future__ import annotations

import logging
import time
from typing import Dict, List, Optional

from core.runtime.models.resource_scheduler_models import (
    AssignmentRecord,
    PriorityTier,
    ResourceOffer,
    ResourceRequest,
    SchedulingDecision,
    SchedulingStatus,
)
from core.runtime.resource_scheduler.allocation_state_machine import (
    AllocationState,
    AllocationStateMachine,
)
from core.runtime.resource_scheduler.fairness_engine import FairnessEngine
from core.runtime.resource_scheduler.quota_arbitrator import QuotaArbitrator
from core.runtime.resource_scheduler.starvation_handler import StarvationHandler
from core.runtime.resource_scheduler.topology_mapper import TopologyMapper

logger = logging.getLogger("emo_ai.resource_scheduler")


class ResourceScheduler:  # ←→ IResourceScheduler
    """Matches resource requests to available workers with fairness.

    LAW 5: All decisions return SchedulingDecision with reason.
    LAW 8: Fair distribution + starvation prevention.
    LAW 11: No global state — per-instance tracking via AssignmentRecord.
    """

    def __init__(
        self,
        quota_arbitrator: Optional[QuotaArbitrator] = None,
        fairness_engine: Optional[FairnessEngine] = None,
        topology_mapper: Optional[TopologyMapper] = None,
        state_machine: Optional[AllocationStateMachine] = None,
        starvation_handler: Optional[StarvationHandler] = None,
    ) -> None:
        self._quota = quota_arbitrator or QuotaArbitrator()
        self._fairness = fairness_engine or FairnessEngine()
        self._topology = topology_mapper or TopologyMapper()
        self._sm = state_machine or AllocationStateMachine()
        self._starvation = starvation_handler or StarvationHandler()
        self._assignments: Dict[str, AssignmentRecord] = {}

    @property
    def quota(self) -> QuotaArbitrator:
        return self._quota

    @property
    def fairness(self) -> FairnessEngine:
        return self._fairness

    @property
    def topology(self) -> TopologyMapper:
        return self._topology

    @property
    def starvation_handler(self) -> StarvationHandler:
        return self._starvation

    @property
    def active_assignments(self) -> Dict[str, AssignmentRecord]:
        return dict(self._assignments)

    # ── match_resources ───────────────────────────────────────

    def match_resources(  # LAW-5, LAW-8, RULE-1
        self,
        request: ResourceRequest,
        available_offers: List[ResourceOffer],
    ) -> SchedulingDecision:
        mapping = self._topology.map_to_hardware(request, available_offers)

        if mapping.worker_id:
            self._sm.transition(AllocationState.MATCHED)
            self._sm.transition(AllocationState.RESERVED, offer_available=True)

            for offer in available_offers:
                if offer.worker_id == mapping.worker_id:
                    return SchedulingDecision(
                        status=SchedulingStatus.ASSIGNED,
                        assigned_worker=mapping.worker_id,
                        reason=(
                            f"Matched worker {mapping.worker_id} "
                            f"(score={mapping.score})"
                        ),
                        timestamp=time.time(),
                    )

        if request.max_wait_sec > 0:
            self._starvation.enqueue(request)
            self._sm.transition(AllocationState.MATCHED)
            self._sm.transition(AllocationState.QUEUED)
            return SchedulingDecision(
                status=SchedulingStatus.QUEUED,
                reason="No matching offer — queued",
                timestamp=time.time(),
            )

        if request.priority in (PriorityTier.CRITICAL, PriorityTier.HIGH):
            preempted = self.preempt_if_needed(request, [
                self._assignments[eid]
                for eid in list(self._assignments.keys())
            ])
            if preempted:
                return preempted

        return SchedulingDecision(
            status=SchedulingStatus.REJECTED,
            reason="No matching offer and cannot wait",
            timestamp=time.time(),
        )

    # ── assign_worker ─────────────────────────────────────────

    def assign_worker(  # RULE-5
        self,
        assignment: SchedulingDecision,
        offer: ResourceOffer,
    ) -> bool:
        if not assignment.assigned_worker:
            logger.debug("No worker in assignment")
            return False

        if assignment.assigned_worker in self._assignments:
            logger.debug("Worker %s already assigned (idempotent)", assignment.assigned_worker)
            return True

        self._sm.transition(AllocationState.ASSIGNED)

        record = AssignmentRecord(
            execution_id=assignment.preempted_id or assignment.assigned_worker,
            worker_id=assignment.assigned_worker,
            resources=ResourceRequest(),
            assigned_at=time.time(),
            preemptible=True,
            checkpoint_available=True,
        )
        self._assignments[assignment.assigned_worker] = record

        logger.info("Assigned worker %s", assignment.assigned_worker)
        return True

    # ── preempt_if_needed ─────────────────────────────────────

    def preempt_if_needed(  # LAW-8, RULE-3
        self,
        request: ResourceRequest,
        active_assignments: List[SchedulingDecision],
    ) -> Optional[SchedulingDecision]:
        candidates: List[AssignmentRecord] = []
        for rec in self._assignments.values():
            ok, _ = self._sm.can_preempt(request, rec)
            if ok:
                candidates.append(rec)

        if not candidates:
            return None

        candidates.sort(key=lambda r: (
            r.resources.priority.value if r.resources else PriorityTier.BATCH.value
        ))

        target = candidates[0]
        self._sm.transition(AllocationState.PREEMPTED,
                            request=request, record=target)
        self._sm.transition(AllocationState.QUEUED, preempted=True)

        if target.execution_id in self._assignments:
            del self._assignments[target.execution_id]

        return SchedulingDecision(
            status=SchedulingStatus.PREEMPTED,
            assigned_worker=target.worker_id,
            preempted_id=target.execution_id,
            reason=(
                f"Preempted {target.execution_id} for {request.execution_id}"
            ),
            timestamp=time.time(),
        )

    # ── release_resources ─────────────────────────────────────

    def release_resources(  # LAW-11, RULE-2
        self,
        execution_id: str,
        assignment: SchedulingDecision,
    ) -> bool:
        if execution_id in self._assignments:
            del self._assignments[execution_id]
            logger.info("Released resources for %s", execution_id)
            return True

        worker_id = assignment.assigned_worker
        if worker_id in self._assignments:
            del self._assignments[worker_id]
            logger.info("Released resources for worker %s", worker_id)
            return True

        logger.debug("No resources to release for %s", execution_id)
        return False
