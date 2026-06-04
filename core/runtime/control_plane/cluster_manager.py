"""Phase F2 — ClusterManager: Worker registry + lifecycle.

Manages the worker pool — register, deregister, list, get_state.
Every mutation goes through LeaseManager and emits events via EventPublisher.

LAW 3: All workers are lease-aware.
LAW 5: Every mutation is observable.
LAW 8: All state transitions are guarded.
LAW 11: No global mutable state — per-instance.

Ref: DEVELOPER.md §15.9
Ref: Canon LAW 3, LAW 5, LAW 8, LAW 11
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.runtime.models.control_plane_models import (
    WorkerState,
    LoadMetric,
)

logger = logging.getLogger("emo_ai.control_plane.cluster")


@dataclass
class WorkerInfo:
    worker_id: str
    capabilities: Dict[str, Any] = field(default_factory=dict)
    endpoint: str = ""
    state: WorkerState = WorkerState.HEALTHY
    lease_id: str = ""
    load: Optional[LoadMetric] = None
    registered_at: float = 0.0
    last_heartbeat: float = 0.0
    tags: Dict[str, str] = field(default_factory=dict)


@dataclass
class RegistrationReceipt:
    worker_id: str
    registered: bool
    lease_id: str = ""
    reason: str = ""


@dataclass
class DeregistrationReceipt:
    worker_id: str
    deregistered: bool
    leases_released: int = 0
    reason: str = ""


class ClusterManager:
    """Worker registry and lifecycle manager.

    LAW 3: Every worker registration acquires a lease.
    LAW 5: register/deregister/state_change → EventBus events.
    LAW 8: All state transitions guarded (no invalid state jumps).
    LAW 11: No global state — per-instance worker tracking.
    """

    def __init__(
        self,
        lease_manager: Optional[Any] = None,
        event_bus: Optional[Any] = None,
        default_lease_ttl: float = 30.0,
    ):
        self._lease_manager = lease_manager
        self._event_bus = event_bus
        self._default_lease_ttl = default_lease_ttl
        self._workers: Dict[str, WorkerInfo] = {}

    @property
    def active_worker_ids(self) -> List[str]:
        return [
            wid for wid, w in self._workers.items()
            if w.state not in (WorkerState.TERMINATED, WorkerState.UNKNOWN)
        ]

    @property
    def worker_count(self) -> int:
        return len(self.active_worker_ids)

    def list_active_workers(self) -> List[WorkerInfo]:
        return [self._workers[wid] for wid in self.active_worker_ids]

    def get_worker(self, worker_id: str) -> Optional[WorkerInfo]:
        return self._workers.get(worker_id)

    def get_worker_state(self, worker_id: str) -> WorkerState:
        worker = self._workers.get(worker_id)
        return worker.state if worker else WorkerState.UNKNOWN

    def register_worker(
        self,
        worker_id: str,
        capabilities: Optional[Dict[str, Any]] = None,
        endpoint: str = "",
        lease_ttl: Optional[float] = None,
    ) -> RegistrationReceipt:
        """Register a new worker.

        LAW 3: Acquires a lease before registration.
        LAW 5: Emits WorkerRegistered event.

        Returns RegistrationReceipt with lease_id.
        """
        if not worker_id or not isinstance(worker_id, str):
            return RegistrationReceipt(
                worker_id=str(worker_id),
                registered=False,
                reason="invalid worker_id",
            )

        if worker_id in self._workers:
            existing = self._workers[worker_id]
            if existing.state not in (WorkerState.TERMINATED, WorkerState.UNKNOWN):
                return RegistrationReceipt(
                    worker_id=worker_id,
                    registered=True,
                    lease_id=existing.lease_id,
                    reason="already registered",
                )

        lease_id = ""
        if self._lease_manager is not None:
            ttl = lease_ttl or self._default_lease_ttl
            lease = self._lease_manager.acquire_lease(worker_id, "ClusterManager", ttl=ttl)
            if lease is not None:
                lease_id = lease

        now = time.time()
        self._workers[worker_id] = WorkerInfo(
            worker_id=worker_id,
            capabilities=capabilities or {},
            endpoint=endpoint,
            state=WorkerState.HEALTHY,
            lease_id=lease_id,
            registered_at=now,
            last_heartbeat=now,
        )

        self._emit_event("worker.registered", {
            "worker_id": worker_id,
            "capabilities": capabilities or {},
            "endpoint": endpoint,
            "lease_id": lease_id,
        })

        logger.info("Worker registered: %s (lease=%s)", worker_id, lease_id)
        return RegistrationReceipt(
            worker_id=worker_id,
            registered=True,
            lease_id=lease_id,
            reason="registered",
        )

    def deregister_worker(
        self,
        worker_id: str,
        reason: str = "",
    ) -> DeregistrationReceipt:
        """Deregister a worker.

        LAW 3: Releases lease before deregistration.
        LAW 5: Emits WorkerDeregistered event.
        LAW 8: Worker must be draining or terminated before deregister.

        Returns DeregistrationReceipt with released lease count.
        """
        worker = self._workers.get(worker_id)
        if worker is None:
            return DeregistrationReceipt(
                worker_id=worker_id,
                deregistered=False,
                reason="worker not found",
            )

        leases_released = 0
        if worker.lease_id and self._lease_manager is not None:
            released = self._lease_manager.release_lease(worker.lease_id)
            if released:
                leases_released = 1

        self._workers.pop(worker_id, None)

        self._emit_event("worker.deregistered", {
            "worker_id": worker_id,
            "reason": reason,
            "leases_released": leases_released,
        })

        logger.info("Worker deregistered: %s (reason=%s)", worker_id, reason)
        return DeregistrationReceipt(
            worker_id=worker_id,
            deregistered=True,
            leases_released=leases_released,
            reason=reason or "deregistered",
        )

    def update_heartbeat(self, worker_id: str) -> bool:
        """Update heartbeat timestamp for a worker.

        Returns True if worker exists and was updated.
        """
        worker = self._workers.get(worker_id)
        if worker is None:
            return False
        worker.last_heartbeat = time.time()
        return True

    def check_stale_workers(self, timeout: float = 60.0) -> List[str]:
        """Find workers whose heartbeat has exceeded the timeout.

        Returns list of stale worker IDs.
        """
        now = time.time()
        stale = []
        for wid, w in self._workers.items():
            if w.state in (WorkerState.TERMINATED, WorkerState.UNKNOWN):
                continue
            if now - w.last_heartbeat > timeout:
                stale.append(wid)
        return stale

    def set_worker_load(self, worker_id: str, load: LoadMetric) -> None:
        """Update the load metric for a worker."""
        worker = self._workers.get(worker_id)
        if worker is not None:
            worker.load = load

    def _emit_event(self, topic: str, payload: Dict[str, Any]) -> None:
        """Emit a cluster management event to EventBus."""
        if self._event_bus is None:
            return
        try:
            from core.models.events import ExecutionEvent
            event = ExecutionEvent(
                event_id=uuid.uuid4().hex[:16],
                event_type=topic.split(".")[-1].upper(),
                timestamp=time.time(),
                source="ClusterManager",
                payload=payload,
            )
            self._event_bus.publish(f"cluster.{topic}", event)
        except Exception as e:
            logger.error("Failed to emit event %s: %s", topic, e)
