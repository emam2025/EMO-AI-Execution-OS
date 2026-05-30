"""Phase F2 — Reconciliation Loop implementation.

Implements IReconciliationLoop: Observe → Compare → Act cycle.

Interval strategy (§15.9.2):
  - observe: every 5s
  - evaluate: every 15s
  - act: every 30s

Ref: Canon RULE 1 (Determinism), RULE 2 (Reversibility), LAW 11 (No global state)
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional

from core.runtime.models.control_plane_models import (
    ClusterSnapshot,
    Correction,
    DeltaReport,
    LoadMetric,
    ReconcileReport,
    ScheduleReceipt,
)


class ReconciliationLoop:  # ←→ IReconciliationLoop
    """Observe → Compare → Act cycle for cluster state correction.

    LAW 11: No global state — per-instance.
    RULE 1: Deterministic comparison.
    RULE 2: Corrections are reversible.
    """

    OBSERVE_INTERVAL: float = 5.0
    EVALUATE_INTERVAL: float = 15.0
    ACT_INTERVAL: float = 30.0

    def __init__(self) -> None:
        self._last_observe: float = 0.0
        self._last_evaluate: float = 0.0
        self._last_act: float = 0.0
        self._current_snapshot: Optional[ClusterSnapshot] = None
        self._pending_corrections: List[Correction] = []
        self._applied_corrections: List[Correction] = []

    # ── observe_current ───────────────────────────────────────

    def observe_current(  # RULE-1
        self,
        worker_count: int = 0,
        healthy: int = 0,
        degraded: int = 0,
        draining: int = 0,
        load: Optional[LoadMetric] = None,
    ) -> ClusterSnapshot:
        self._last_observe = time.time()
        snapshot = ClusterSnapshot(
            worker_count=worker_count,
            healthy_count=healthy,
            degraded_count=degraded,
            draining_count=draining,
            load=load,
            timestamp=self._last_observe,
        )
        self._current_snapshot = snapshot
        return snapshot

    @property
    def current_snapshot(self) -> Optional[ClusterSnapshot]:
        return self._current_snapshot

    # ── compare_desired ───────────────────────────────────────

    def compare_desired(  # RULE-1
        self,
        actual: ClusterSnapshot,
        desired: ClusterSnapshot,
    ) -> DeltaReport:
        deficit = max(0, desired.worker_count - actual.worker_count)
        surplus = max(0, actual.worker_count - desired.worker_count)
        drift = deficit > 0 or surplus > 0

        corrections: List[Correction] = []
        if surplus > 0:
            corrections.append(Correction(
                action="scale_down" if surplus <= 2 else "drain",
                reason=f"surplus {surplus} workers",
                priority=3,
            ))
        if deficit > 0:
            corrections.append(Correction(
                action="scale_up",
                reason=f"deficit {deficit} workers",
                priority=1,
            ))

        return DeltaReport(
            drift_detected=drift,
            worker_deficit=deficit,
            worker_surplus=surplus,
            corrections=corrections,
            observed_timestamp=actual.timestamp or time.time(),
        )

    # ── compute_delta ─────────────────────────────────────────

    def compute_delta(  # RULE-1, RULE-2
        self,
        actual: ClusterSnapshot,
        desired: ClusterSnapshot,
    ) -> List[Correction]:
        corrections: List[Correction] = []

        deficit = max(0, desired.worker_count - actual.worker_count)
        surplus = max(0, actual.worker_count - desired.worker_count)

        if deficit > 0:
            corrections.append(Correction(
                action="scale_up",
                reason=f"deficit {deficit} workers",
                priority=1,
            ))

        if surplus > 0:
            corrections.append(Correction(
                action="drain" if surplus >= 2 else "scale_down",
                worker_id="",
                reason=f"surplus {surplus} workers",
                priority=3,
            ))

        healthy_deficit = max(0, desired.healthy_count - actual.healthy_count)
        if healthy_deficit > 0 and actual.degraded_count > 0:
            corrections.append(Correction(
                action="recover_degraded",
                reason=f"{actual.degraded_count} degraded workers",
                priority=2,
            ))

        corrections.sort(key=lambda c: c.priority)
        return corrections

    # ── schedule_correction ───────────────────────────────────

    def schedule_correction(  # LAW-11, RULE-2
        self,
        corrections: List[Correction],
    ) -> ScheduleReceipt:
        self._pending_corrections = sorted(corrections, key=lambda c: c.priority)
        self._last_act = time.time()

        estimated = self._last_act + (len(corrections) * self.ACT_INTERVAL)

        return ScheduleReceipt(
            corrections_scheduled=len(corrections),
            estimated_completion=estimated,
            batch_id=uuid.uuid4().hex[:16],
        )

    def apply_next_correction(self) -> Optional[Correction]:
        if not self._pending_corrections:
            return None
        correction = self._pending_corrections.pop(0)
        self._applied_corrections.append(correction)
        return correction

    def produce_report(self) -> ReconcileReport:
        snapshot = self._current_snapshot
        return ReconcileReport(
            observed_workers=snapshot.worker_count if snapshot else 0,
            desired_workers=0,
            corrections_applied=len(self._applied_corrections),
            corrections_pending=len(self._pending_corrections),
            drift_count=len(self._applied_corrections),
            timestamp=time.time(),
        )

    def reset(self) -> None:
        self._last_observe = 0.0
        self._last_evaluate = 0.0
        self._last_act = 0.0
        self._current_snapshot = None
        self._pending_corrections.clear()
        self._applied_corrections.clear()
