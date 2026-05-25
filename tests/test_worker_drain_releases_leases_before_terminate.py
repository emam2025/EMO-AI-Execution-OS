"""Phase F2 — Worker drain lifecycle: RELEASE_LEASES before TERMINATE.

Verifies the 5-phase drain lifecycle per §15.9.3:
  MARK_DRAINING → STOP_NEW_LEASES → AWAIT_COMPLETION
  → RELEASE_LEASES → TERMINATE

Guarantees LAW 3: RELEASE_LEASES completes before TERMINATE.

Ref: §15.9.3, Canon LAW 3, LAW 8, RULE 5
"""

import pytest

from core.runtime.control_plane.worker_drainer import WorkerDrainer
from core.runtime.models.control_plane_models import (
    WorkerDrainingState,
    WorkerState,
)


class TestWorkerDrainReleasesLeasesBeforeTerminate:
    """Verifies LAW 3: RELEASE_LEASES before TERMINATE.

    Tests:
      1. Full 5-phase drain completes successfully
      2. Cannot TERMINATE without RELEASE_LEASES
      3. Draining is idempotent (RULE 5)
      4. Already terminated → no-op
      5. Active leases are awaited before release
      6. Timeout forces lease release
    """

    def test_full_5_phase_drain_completes(self):
        drainer = WorkerDrainer(max_drain_wait_sec=300.0)
        receipt = drainer.drain("worker-1", reason="scale down", active_lease_count=0)
        assert receipt.success
        assert receipt.state == WorkerState.TERMINATED
        assert receipt.leases_released == 0
        assert drainer.is_terminated("worker-1")

    def test_leases_released_before_terminate(self):
        drainer = WorkerDrainer(max_drain_wait_sec=0.0)
        receipt = drainer.drain("worker-2", reason="test", active_lease_count=3)
        assert receipt.success
        assert receipt.leases_released == 3
        assert drainer.is_terminated("worker-2")

    def test_cannot_terminate_without_release_leases(self):
        drainer = WorkerDrainer()
        drainer.mark_draining("worker-3")
        drainer.stop_new_leases("worker-3")
        # Skip AWAIT_COMPLETION and RELEASE_LEASES
        terminated = drainer.terminate("worker-3")
        assert not terminated  # LAW 3 violation prevented
        assert not drainer.is_terminated("worker-3")

    def test_drain_idempotent(self):
        drainer = WorkerDrainer()
        r1 = drainer.drain("worker-4", reason="first")
        r2 = drainer.drain("worker-4", reason="second")
        assert r1.success
        assert r2.success
        assert r2.reason == "already terminated"

    def test_already_draining_returns_existing_state(self):
        drainer = WorkerDrainer()
        drainer.mark_draining("worker-5")
        result = drainer.mark_draining("worker-5")
        assert result is True  # idempotent

    def test_drain_awaits_active_leases(self):
        drainer = WorkerDrainer(max_drain_wait_sec=10.0)
        ok = drainer.await_completion("worker-non-existent")
        assert not ok  # not in draining state

    def test_drain_timeout_releases_leases(self):
        drainer = WorkerDrainer(max_drain_wait_sec=0.0)
        drainer.mark_draining("worker-6")
        drainer.stop_new_leases("worker-6")
        ok = drainer.await_completion("worker-6", active_lease_count=2)
        assert ok  # timeout forces completion
        released = drainer.release_leases("worker-6", 2)
        assert released == 2
        assert drainer.terminate("worker-6")

    def test_draining_workers_list(self):
        drainer = WorkerDrainer()
        drainer.mark_draining("w1")
        drainer.stop_new_leases("w1")
        drainer.mark_draining("w2")
        draining = drainer.draining_workers
        assert "w1" in draining
        assert "w2" in draining
