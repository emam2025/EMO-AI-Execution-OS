"""TrustScheduler — Trust-Aware Task Scheduling.

Routes tasks to workers based on trust level.
Critical tasks require TRUSTED workers.
Unverified workers can only execute safe tasks.

Ref: Phase E.4 — Trust-Aware Scheduling
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Dict, List, Optional

from core.models.trust import TrustPolicy, WorkerTrustLevel

if TYPE_CHECKING:
    from core.interfaces.event_bus import IEventBus

logger = logging.getLogger(__name__)

_TRUST_ORDER = {
    WorkerTrustLevel.UNVERIFIED: 0,
    WorkerTrustLevel.VERIFIED: 1,
    WorkerTrustLevel.TRUSTED: 2,
}


class TrustScheduler:
    """Trust-aware task scheduler.

    Routes tasks to workers based on trust level.
    Critical tasks require TRUSTED workers.
    Unverified workers can only execute safe tasks.
    """

    def __init__(self, event_bus: Optional[IEventBus] = None) -> None:
        self._event_bus = event_bus
        self._workers: Dict[str, WorkerTrustLevel] = {}
        self._policies: Dict[str, TrustPolicy] = {}
        self._audit_log: List[Dict[str, str]] = []

    def register_worker(self, worker_id: str, trust_level: WorkerTrustLevel) -> None:
        """Register a worker with its trust level."""
        self._workers[worker_id] = trust_level

    def register_policy(self, task_type: str, policy: TrustPolicy) -> None:
        """Register a trust policy for a task type."""
        self._policies[task_type] = policy

    def get_worker_trust(self, worker_id: str) -> Optional[WorkerTrustLevel]:
        """Get the trust level of a registered worker."""
        return self._workers.get(worker_id)

    def schedule_task(self, task_type: str, worker_id: str) -> bool:
        """Schedule a task to a worker. Returns True if allowed.

        Checks:
        1. Worker is registered (Default Deny for unregistered).
        2. Worker trust level meets policy minimum.
        3. Policy enforcement (approval requirement recorded).
        """
        trust_level = self._workers.get(worker_id)
        if trust_level is None:
            self._record_decision(task_type, worker_id, "denied", "unregistered_worker")
            return False

        policy = self._policies.get(task_type)
        if policy is not None:
            worker_rank = _TRUST_ORDER.get(trust_level, -1)
            required_rank = _TRUST_ORDER.get(policy.min_trust_level, -1)

            if worker_rank < required_rank:
                self._record_decision(
                    task_type, worker_id, "denied",
                    f"trust_level_insufficient: {trust_level.value} < {policy.min_trust_level.value}",
                )
                return False

        self._record_decision(task_type, worker_id, "allowed", "policy_satisfied")
        return True

    def list_workers(self) -> Dict[str, WorkerTrustLevel]:
        """Return all registered workers."""
        return dict(self._workers)

    def list_policies(self) -> Dict[str, TrustPolicy]:
        """Return all registered policies."""
        return dict(self._policies)

    def get_audit_log(self) -> List[Dict[str, str]]:
        """Return the scheduling audit log."""
        return list(self._audit_log)

    def _record_decision(
        self, task_type: str, worker_id: str, decision: str, reason: str
    ) -> None:
        """Record a scheduling decision and publish audit event."""
        entry = {
            "task_type": task_type,
            "worker_id": worker_id,
            "decision": decision,
            "reason": reason,
        }
        self._audit_log.append(entry)
        self._publish_audit_event(task_type, worker_id, decision, reason)

    def _publish_audit_event(
        self, task_type: str, worker_id: str, decision: str, reason: str
    ) -> None:
        """Publish scheduling decision as audit event."""
        if self._event_bus is None:
            return

        from core.models.event import EventTopic, ExecutionEvent

        event = ExecutionEvent(
            topic=EventTopic.SECURITY_VIOLATION,
            payload={
                "task_type": task_type,
                "worker_id": worker_id,
                "decision": decision,
                "reason": reason,
                "requested_capability": "trust_scheduling",
                "action_taken": "audited",
            },
            trace_id=f"trust-{worker_id}-{task_type}",
        )
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(
                self._event_bus.publish(EventTopic.SECURITY_VIOLATION, event)
            )
        except RuntimeError:
            pass
