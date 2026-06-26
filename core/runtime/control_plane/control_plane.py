"""Phase F2 — Control Plane orchestrator implementation.

Implements IControlPlane: reconcile, enforce_policy, publish_state, drain_worker.

Coordinates Autoscaler, HealthSupervisor, ReconciliationLoop, and WorkerDrainer.

Ref: Canon LAW 8 (Guarded transitions), LAW 11 (No global state), RULE 5 (Idempotency)
"""

from __future__ import annotations

import logging
import time
from typing import Any, List, Optional

from core.runtime.control_plane.autoscaler import Autoscaler
from core.runtime.control_plane.health_supervisor import HealthSupervisor
from core.runtime.control_plane.reconciliation_loop import ReconciliationLoop
from core.runtime.control_plane.worker_drainer import WorkerDrainer
from core.runtime.models.control_plane_models import (
    ClusterSnapshot,
    ControlPlaneState,
    DrainReceipt,
    PolicyResult,
    ReconcileReport,
    ScalingPolicy,
    ScalingSignal,
    WorkerState,
)

logger = logging.getLogger("emo_ai.control_plane")


class ControlPlane:  # ←→ IControlPlane
    """Top-level Control Plane orchestrator.

    LAW 8: All state transitions guarded.
    LAW 11: No global state — per-instance.
    RULE 5: All operations idempotent.
    """

    def __init__(
        self,
        autoscaler: Optional[Autoscaler] = None,
        health_supervisor: Optional[HealthSupervisor] = None,
        reconciliation_loop: Optional[ReconciliationLoop] = None,
        worker_drainer: Optional[WorkerDrainer] = None,
        policy: Optional[ScalingPolicy] = None,
    ) -> None:
        self._autoscaler = autoscaler or Autoscaler()
        self._health = health_supervisor or HealthSupervisor()
        self._reconciler = reconciliation_loop or ReconciliationLoop()
        self._drainer = worker_drainer or WorkerDrainer()
        self._policy = policy or ScalingPolicy()
        self._current_worker_count: int = 0
        self._last_reconcile: float = 0.0
        self._errors: List[str] = []

    @property
    def autoscaler(self) -> Autoscaler:
        return self._autoscaler

    @property
    def health_supervisor(self) -> HealthSupervisor:
        return self._health

    @property
    def reconciliation_loop(self) -> ReconciliationLoop:
        return self._reconciler

    @property
    def worker_drainer(self) -> WorkerDrainer:
        return self._drainer

    @property
    def policy(self) -> ScalingPolicy:
        return self._policy

    @policy.setter
    def policy(self, p: ScalingPolicy) -> None:
        self._policy = p

    # ── reconcile ─────────────────────────────────────────────

    def reconcile(  # LAW-8, LAW-11
        self,
        desired_state: ClusterSnapshot,
    ) -> ReconcileReport:
        actual = self._reconciler.observe_current(
            worker_count=self._current_worker_count,
            healthy=self._current_worker_count,
            degraded=0,
            draining=len(self._drainer.draining_workers),
        )
        delta = self._reconciler.compute_delta(actual, desired_state)

        for correction in delta:
            if correction.action == "scale_up":
                signal = self._autoscaler.evaluate_load(actual, self._policy)
                if signal == ScalingSignal.UP:
                    load = actual.load
                    if load is not None:
                        target = self._autoscaler.calculate_target_count(load, self._policy)
                        self._autoscaler.apply_scaling(target, self._policy, self._current_worker_count)

            elif correction.action in ("drain", "scale_down"):
                for i in range(correction.action.count) if hasattr(correction, 'count') else range(1):
                    if self._drainer.draining_workers:
                        wid = self._drainer.draining_workers[0]
                        self.drain_worker(wid, reason=correction.reason)

            elif correction.action == "recover_degraded":
                pass

        self._last_reconcile = time.time()
        return self._reconciler.produce_report()

    # ── enforce_policy ────────────────────────────────────────

    def enforce_policy(  # LAW-8
        self,
        policy: ScalingPolicy,
        context: ClusterSnapshot,
    ) -> PolicyResult:
        signal = self._autoscaler.evaluate_load(context, policy)
        cooldown_until = self._autoscaler.cooldown_timer.last_action_time + policy.cooldown_sec

        if signal == ScalingSignal.HOLD:
            return PolicyResult(
                applied=False,
                signal=ScalingSignal.HOLD,
                reason="within hysteresis band or cooldown active",
                cooldown_until=cooldown_until,
            )

        if signal == ScalingSignal.UP and context.worker_count >= policy.max_workers:
            return PolicyResult(
                applied=False,
                signal=ScalingSignal.HOLD,
                reason=f"capacity exhausted: {context.worker_count} >= {policy.max_workers}",
                cooldown_until=cooldown_until,
            )

        target = self._autoscaler.calculate_target_count(
            context.load or 0,
            policy,
        )

        return PolicyResult(
            applied=True,
            signal=signal,
            reason=f"policy allows {signal.value}",
            cooldown_until=cooldown_until,
        )

    # ── publish_state ─────────────────────────────────────────

    def publish_state(  # LAW-5
        self,
    ) -> ControlPlaneState:
        return ControlPlaneState(
            active_workers=self._current_worker_count,
            draining_workers=list(self._drainer.draining_workers),
            current_replica=self._current_worker_count,
            desired_replica=self._current_worker_count,
            last_reconcile=self._last_reconcile,
            scaling_signal=self._autoscaler.evaluate_load(
                ClusterSnapshot(
                    worker_count=self._current_worker_count,
                    healthy_count=self._current_worker_count,
                ),
                self._policy,
            ),
            errors=list(self._errors),
        )

    # ── drain_worker ──────────────────────────────────────────

    def drain_worker(  # LAW-3, LAW-8, RULE-5, §15.9.3
        self,
        worker_id: str,
        reason: str = "",
    ) -> DrainReceipt:
        receipt = self._drainer.drain(worker_id, reason)
        if receipt.success:
            self._current_worker_count = max(0, self._current_worker_count - 1)

        return receipt
