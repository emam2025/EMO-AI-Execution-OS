"""F2 — ClusterManager: worker lifecycle and reconciliation.

Manages worker lifecycle and reconciles desired vs actual state.
Delegates to D8 services via constructor injection.

Ref: DEVELOPER.md §15.10
Ref: Canon LAW 10, LAW 13, LAW 23
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from core.interfaces.lease import IExecutionLeaseManager
from core.interfaces.state_store import IExecutionStateStore
from core.models.control_plane import (
    ClusterState,
    ReconciliationAction,
    WorkerStatus,
)

logger = logging.getLogger("emo_ai.control_plane.f2")


class F2ClusterManager:
    """Manages worker lifecycle and reconciliation.

    LAW 13: Dependencies injected via constructor.
    No direct execution — issues reassignment commands only.
    """

    def __init__(
        self,
        lease_manager: IExecutionLeaseManager,
        state_store: IExecutionStateStore,
    ):
        self._lease_manager = lease_manager
        self._state_store = state_store
        self._workers: Dict[str, Dict[str, Any]] = {}
        self._tasks: Dict[str, str] = {}

    def register_worker(self, worker_id: str, capabilities: Dict[str, Any]) -> None:
        """Register a new worker in the cluster."""
        self._workers[worker_id] = {
            "status": WorkerStatus.ONLINE,
            "capabilities": capabilities,
        }

    def deregister_worker(self, worker_id: str) -> None:
        """Deregister a worker and reassign its tasks.

        Delegates:
          - LeaseManager → release_lease(lease_id)
          - LeaseManager → acquire_lease(task, new_owner)
        """
        worker = self._workers.get(worker_id)
        if worker is None:
            return

        # Find tasks owned by this worker
        task_ids = [
            tid for tid, owner in self._tasks.items() if owner == worker_id
        ]

        # Reassign tasks
        for task_id in task_ids:
            del self._tasks[task_id]
            new_lease = self._lease_manager.acquire_lease(
                task_id, "control_plane",
            )

        # Release worker lease
        lease_id = worker.get("lease_id")
        if lease_id:
            self._lease_manager.release_lease(lease_id)

        del self._workers[worker_id]

    def run_reconciliation_loop(self) -> List[ReconciliationAction]:
        """Compare desired vs actual state and issue correction actions.

        Delegates:
          - LeaseManager → monitor_heartbeat(lease_id)
          - LeaseManager → acquire_lease(task, new_owner)
        """
        actions: List[ReconciliationAction] = []

        for worker_id, worker in list(self._workers.items()):
            status = worker["status"]

            # Detect unhealthy workers
            if status == WorkerStatus.UNHEALTHY:
                lease_id = worker.get("lease_id")
                if lease_id:
                    self._lease_manager.release_lease(lease_id)
                    actions.append(
                        ReconciliationAction(
                            action_type="REASSIGN_LEASE",
                            target_id=worker_id,
                            reason=f"Worker {worker_id} is unhealthy",
                        )
                    )

            # Drain draining workers
            elif status == WorkerStatus.DRAINING:
                actions.append(
                    ReconciliationAction(
                        action_type="DRAIN_WORKER",
                        target_id=worker_id,
                        reason=f"Worker {worker_id} is draining",
                    )
                )

            # Check heartbeat for online workers
            elif status == WorkerStatus.ONLINE:
                lease_id = worker.get("lease_id")
                if lease_id:
                    heartbeat_ok = self._lease_manager.monitor_heartbeat(lease_id)
                    if not heartbeat_ok:
                        worker["status"] = WorkerStatus.UNHEALTHY
                        actions.append(
                            ReconciliationAction(
                                action_type="REASSIGN_LEASE",
                                target_id=worker_id,
                                reason=f"Worker {worker_id} heartbeat failed",
                            )
                        )

        # Check for scale-up needed
        online_count = sum(
            1 for w in self._workers.values() if w["status"] == WorkerStatus.ONLINE
        )
        if online_count == 0 and len(self._tasks) > 0:
            actions.append(
                ReconciliationAction(
                    action_type="SCALE_UP",
                    target_id="cluster",
                    reason="No online workers but tasks exist",
                )
            )

        return actions

    def get_cluster_state(self) -> ClusterState:
        """Return current cluster state snapshot."""
        active = sum(
            1 for w in self._workers.values() if w["status"] == WorkerStatus.ONLINE
        )
        return ClusterState(
            active_workers=active,
            pending_tasks=len(self._tasks),
            total_capacity=len(self._workers),
        )
