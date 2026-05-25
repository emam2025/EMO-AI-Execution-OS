"""Phase F2 — Worker Drain Lifecycle implementation.

5-phase draining lifecycle (§15.9.3):
  MARK_DRAINING → STOP_NEW_LEASES → AWAIT_COMPLETION
  → RELEASE_LEASES → TERMINATE

Guarantees RELEASE_LEASES before TERMINATE (LAW 3 compliance).

Ref: Canon LAW 3 (Lease integrity), LAW 8 (Guarded transitions), RULE 5 (Idempotency)
"""

from __future__ import annotations

import logging
import time
from typing import Dict, Optional

from core.runtime.models.control_plane_models import (
    DrainReceipt,
    WorkerDrainingState,
    WorkerState,
)

logger = logging.getLogger("emo_ai.control_plane.drainer")


class WorkerDrainer:  # §15.9.3
    """Manages the 5-phase worker draining lifecycle.

    LAW 3: RELEASE_LEASES MUST complete before TERMINATE.
    LAW 8: Each phase transition MUST be guarded.
    RULE 5: Each drain operation is idempotent.

    Draining lifecycle:
      MARK_DRAINING → STOP_NEW_LEASES → AWAIT_COMPLETION
      → RELEASE_LEASES → TERMINATE
    """

    def __init__(self, max_drain_wait_sec: float = 300.0) -> None:
        self._drain_states: Dict[str, WorkerDrainingState] = {}
        self._drain_start: Dict[str, float] = {}
        self._leases_released: Dict[str, int] = {}
        self._max_drain_wait = max_drain_wait_sec
        self._terminated: Dict[str, bool] = {}

    @property
    def draining_workers(self) -> list:
        return [wid for wid, st in self._drain_states.items()
                if st != WorkerDrainingState.TERMINATE]

    @property
    def drain_states(self) -> Dict[str, WorkerDrainingState]:
        return dict(self._drain_states)

    def get_drain_state(self, worker_id: str) -> Optional[WorkerDrainingState]:
        return self._drain_states.get(worker_id)

    def is_terminated(self, worker_id: str) -> bool:
        return self._terminated.get(worker_id, False)

    # ── Phase 1: MARK_DRAINING ────────────────────────────────

    def mark_draining(  # LAW-8, RULE-5
        self,
        worker_id: str,
        reason: str = "",
    ) -> bool:
        if self._drain_states.get(worker_id) == WorkerDrainingState.TERMINATE:
            logger.debug("Already terminated: %s", worker_id)
            return False

        if worker_id in self._drain_states:
            logger.debug("Already draining: %s", worker_id)
            return True

        self._drain_states[worker_id] = WorkerDrainingState.MARK_DRAINING
        self._drain_start[worker_id] = time.time()
        self._leases_released[worker_id] = 0
        logger.info("MARK_DRAINING: %s (%s)", worker_id, reason)
        return True

    # ── Phase 2: STOP_NEW_LEASES ──────────────────────────────

    def stop_new_leases(  # LAW-8
        self,
        worker_id: str,
    ) -> bool:
        state = self._drain_states.get(worker_id)
        if state != WorkerDrainingState.MARK_DRAINING and state is not None:
            return state == WorkerDrainingState.STOP_NEW_LEASES

        if state is None:
            return False

        self._drain_states[worker_id] = WorkerDrainingState.STOP_NEW_LEASES
        logger.info("STOP_NEW_LEASES: %s", worker_id)
        return True

    # ── Phase 3: AWAIT_COMPLETION ─────────────────────────────

    def await_completion(  # LAW-8, RULE-3
        self,
        worker_id: str,
        active_lease_count: int = 0,
    ) -> bool:
        state = self._drain_states.get(worker_id)
        if state != WorkerDrainingState.STOP_NEW_LEASES and state is not None:
            return state == WorkerDrainingState.AWAIT_COMPLETION

        if state is None:
            return False

        if active_lease_count > 0:
            elapsed = time.time() - self._drain_start.get(worker_id, 0)
            if elapsed < self._max_drain_wait:
                logger.debug(
                    "AWAIT_COMPLETION: %s — %d active leases, %.0fs elapsed",
                    worker_id, active_lease_count, elapsed,
                )
                return False

            logger.warning(
                "AWAIT_COMPLETION timeout: %s — %d leases forced",
                worker_id, active_lease_count,
            )

        self._drain_states[worker_id] = WorkerDrainingState.AWAIT_COMPLETION
        logger.info("AWAIT_COMPLETION: %s (leases=%d)", worker_id, active_lease_count)
        return True

    # ── Phase 4: RELEASE_LEASES ───────────────────────────────

    def release_leases(  # LAW-3, LAW-8
        self,
        worker_id: str,
        lease_count: int = 0,
    ) -> int:
        state = self._drain_states.get(worker_id)
        if state == WorkerDrainingState.RELEASE_LEASES:
            return self._leases_released.get(worker_id, 0)

        if state != WorkerDrainingState.AWAIT_COMPLETION and state is not None:
            return 0

        if state is None:
            return 0

        self._drain_states[worker_id] = WorkerDrainingState.RELEASE_LEASES
        self._leases_released[worker_id] = lease_count
        logger.info("RELEASE_LEASES: %s — %d leases", worker_id, lease_count)
        return lease_count

    # ── Phase 5: TERMINATE ────────────────────────────────────

    def terminate(  # LAW-8, RULE-4
        self,
        worker_id: str,
    ) -> bool:
        state = self._drain_states.get(worker_id)

        # RULE 5: Already terminated → idempotent
        if state == WorkerDrainingState.TERMINATE:
            return True

        # Guard: must have completed RELEASE_LEASES before TERMINATE
        if state != WorkerDrainingState.RELEASE_LEASES:
            logger.error(
                "LAW 3 VIOLATION: Cannot TERMINATE %s without RELEASE_LEASES "
                "(state=%s)", worker_id, state,
            )
            return False

        self._drain_states[worker_id] = WorkerDrainingState.TERMINATE
        self._terminated[worker_id] = True
        logger.info("TERMINATE: %s", worker_id)
        return True

    # ── Full drain flow ───────────────────────────────────────

    def drain(  # LAW-3, LAW-8, §15.9.3
        self,
        worker_id: str,
        reason: str = "",
        active_lease_count: int = 0,
    ) -> DrainReceipt:
        if self.is_terminated(worker_id):
            return DrainReceipt(
                worker_id=worker_id,
                success=True,
                state=WorkerState.TERMINATED,
                leases_released=self._leases_released.get(worker_id, 0),
                reason="already terminated",
            )

        self.mark_draining(worker_id, reason)
        self.stop_new_leases(worker_id)

        completion_ok = self.await_completion(worker_id, active_lease_count)
        if not completion_ok:
            return DrainReceipt(
                worker_id=worker_id,
                success=False,
                state=WorkerState.DRAINING,
                leases_released=0,
                reason="awaiting completion timeout",
            )

        released = self.release_leases(worker_id, active_lease_count)
        terminated = self.terminate(worker_id)

        return DrainReceipt(
            worker_id=worker_id,
            success=terminated,
            state=WorkerState.TERMINATED if terminated else WorkerState.DRAINING,
            leases_released=released,
            reason=reason or "drain completed",
        )
