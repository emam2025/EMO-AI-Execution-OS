"""F2 — Control Plane Tests.

Verifies worker lifecycle management and reconciliation logic.

Ref: DEVELOPER.md §15.10
Ref: Canon LAW 10, LAW 13, LAW 23
"""

from unittest.mock import MagicMock

from core.interfaces.lease import IExecutionLeaseManager
from core.interfaces.state_store import IExecutionStateStore
from core.models.control_plane import (
    ClusterState,
    ReconciliationAction,
    WorkerStatus,
)
from core.runtime.control_plane.f2_cluster_manager import F2ClusterManager


def _build_control_plane() -> F2ClusterManager:
    lease_manager = MagicMock(spec=IExecutionLeaseManager)
    state_store = MagicMock(spec=IExecutionStateStore)
    return F2ClusterManager(
        lease_manager=lease_manager,
        state_store=state_store,
    )


class TestControlPlane:
    def test_control_plane_registers_and_deregisters_worker(self) -> None:
        cp = _build_control_plane()
        cp.register_worker("worker-1", {"cpu": 4})
        state = cp.get_cluster_state()
        assert state.active_workers == 1
        cp.deregister_worker("worker-1")
        state = cp.get_cluster_state()
        assert state.active_workers == 0

    def test_reconciliation_loop_detects_unhealthy_worker(self) -> None:
        cp = _build_control_plane()
        cp.register_worker("worker-1", {"cpu": 4})
        cp._workers["worker-1"]["status"] = WorkerStatus.UNHEALTHY
        cp._workers["worker-1"]["lease_id"] = "lease-1"
        actions = cp.run_reconciliation_loop()
        assert any(a.action_type == "REASSIGN_LEASE" for a in actions)

    def test_reconciliation_loop_reassigns_lease_on_worker_failure(self) -> None:
        cp = _build_control_plane()
        cp.register_worker("worker-1", {"cpu": 4})
        cp._workers["worker-1"]["lease_id"] = "lease-1"
        cp._workers["worker-1"]["status"] = WorkerStatus.UNHEALTHY
        actions = cp.run_reconciliation_loop()
        cp._lease_manager.release_lease.assert_called_with("lease-1")
        assert any(a.target_id == "worker-1" for a in actions)

    def test_control_plane_drains_worker_gracefully(self) -> None:
        cp = _build_control_plane()
        cp.register_worker("worker-1", {"cpu": 4})
        cp._workers["worker-1"]["status"] = WorkerStatus.DRAINING
        actions = cp.run_reconciliation_loop()
        assert any(a.action_type == "DRAIN_WORKER" for a in actions)

    def test_get_cluster_state_returns_accurate_metrics(self) -> None:
        cp = _build_control_plane()
        cp.register_worker("worker-1", {"cpu": 4})
        cp.register_worker("worker-2", {"cpu": 8})
        cp._workers["worker-2"]["status"] = WorkerStatus.UNHEALTHY
        state = cp.get_cluster_state()
        assert state.active_workers == 1
        assert state.total_capacity == 2

    def test_control_plane_uses_lease_manager_for_reassignment(self) -> None:
        cp = _build_control_plane()
        cp.register_worker("worker-1", {"cpu": 4})
        cp._workers["worker-1"]["lease_id"] = "lease-1"
        cp._workers["worker-1"]["status"] = WorkerStatus.UNHEALTHY
        cp.run_reconciliation_loop()
        cp._lease_manager.release_lease.assert_called_once()
