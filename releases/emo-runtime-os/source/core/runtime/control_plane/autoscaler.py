"""Phase F2 — Autoscaler implementation.

Implements IAutoscaler with oscillation prevention:
  - CooldownTimer
  - HysteresisEvaluator
  - ConsecutiveCycleTracker

§15.9.4: All scaling decisions are oscillation-free.

Ref: Canon LAW 5 (Observability), LAW 8 (Guarded transitions), RULE 1 (Determinism)
"""

from __future__ import annotations

import math
import time
from typing import List, Optional, Tuple

from core.runtime.control_plane.oscillation_guard import (
    ConsecutiveCycleTracker,
    CooldownTimer,
    HysteresisEvaluator,
)
from core.runtime.models.control_plane_models import (
    ClusterSnapshot,
    LoadMetric,
    ScalingPolicy,
    ScalingReceipt,
    ScalingSignal,
    ScalingSignalRecord,
)


class Autoscaler:  # ←→ IAutoscaler
    """Scaling decision engine with oscillation prevention.

    LAW 5: All decisions observable via evaluate_load() return value.
    LAW 8: All transitions guarded (cooldown, hysteresis, consecutive cycles).
    RULE 1: Deterministic — same load + policy → same signal.
    """

    def __init__(
        self,
        cooldown_timer: Optional[CooldownTimer] = None,
        hysteresis: Optional[HysteresisEvaluator] = None,
        cycle_tracker: Optional[ConsecutiveCycleTracker] = None,
    ) -> None:
        self._cooldown = cooldown_timer or CooldownTimer()
        self._hysteresis = hysteresis or HysteresisEvaluator()
        self._cycle_tracker = cycle_tracker or ConsecutiveCycleTracker(
            required_consecutive=2,
        )
        self._signal_history: List[ScalingSignalRecord] = []
        self._current_count: int = 0

    @property
    def signal_history(self) -> List[ScalingSignalRecord]:
        return list(self._signal_history)

    @property
    def cooldown_timer(self) -> CooldownTimer:
        return self._cooldown

    # ── evaluate_load ─────────────────────────────────────────

    def evaluate_load(  # LAW-5, LAW-8
        self,
        snapshot: ClusterSnapshot,
        policy: ScalingPolicy,
    ) -> ScalingSignal:
        if snapshot.load is None:
            return ScalingSignal.HOLD

        utilization = max(
            (snapshot.load.cpu_pct / 100.0),
            (snapshot.load.mem_pct / 100.0),
        )

        # Cooldown guard: if cooldown active → HOLD
        if not self._cooldown.is_expired(policy):
            self._cycle_tracker.record(ScalingSignal.HOLD)
            return ScalingSignal.HOLD

        raw = self._hysteresis.evaluate(utilization, policy)
        self._cycle_tracker.record(raw)

        # Consecutive cycle guard: need 2 same signals in a row
        if raw in (ScalingSignal.UP, ScalingSignal.DOWN):
            if not self._cycle_tracker.threshold_met(raw):
                return ScalingSignal.HOLD

        if raw == ScalingSignal.DOWN:
            surplus = snapshot.worker_count - policy.min_workers
            if surplus >= 2:
                return ScalingSignal.DRAIN
            if surplus >= 1:
                return ScalingSignal.DOWN

        return raw

    # ── calculate_target_count ─────────────────────────────────

    def calculate_target_count(  # RULE-1
        self,
        load_snapshot: LoadMetric,
        policy: ScalingPolicy,
    ) -> int:
        utilization = max(
            (load_snapshot.cpu_pct / 100.0),
            (load_snapshot.mem_pct / 100.0),
        )
        if utilization <= 0.0:
            return policy.min_workers

        target = math.ceil(
            self._current_count * utilization / policy.target_utilization
        )
        return max(policy.min_workers, min(policy.max_workers, target))

    # ── apply_scaling ─────────────────────────────────────────

    def apply_scaling(  # LAW-8, RULE-5
        self,
        target_count: int,
        policy: ScalingPolicy,
        current_workers: int = 0,
    ) -> ScalingReceipt:
        prev = current_workers or self._current_count

        if target_count > prev:
            delta = min(target_count - prev, policy.scale_step)
            actual = prev + delta
            signal = ScalingSignal.UP
        elif target_count < prev:
            delta = min(prev - target_count, policy.scale_step)
            actual = prev - delta
            signal = ScalingSignal.DOWN
        else:
            return ScalingReceipt(
                previous_count=prev,
                target_count=target_count,
                actual_count=prev,
                signal=ScalingSignal.HOLD,
                cooldown_until=self._cooldown.last_action_time + policy.cooldown_sec,
                reason="no change needed",
            )

        self._current_count = actual
        self._cooldown.record_action()
        cooldown_until = time.time() + policy.cooldown_sec

        record = ScalingSignalRecord(
            timestamp=time.time(),
            signal=signal,
            previous_count=prev,
            target_count=actual,
            reason=f"{signal.value}: {prev}→{actual}",
        )
        self._signal_history.append(record)

        return ScalingReceipt(
            previous_count=prev,
            target_count=target_count,
            actual_count=actual,
            signal=signal,
            cooldown_until=cooldown_until,
            reason=f"{signal.value}: {prev}→{actual} (step={policy.scale_step})",
        )

    # ── enforce_cooldown ──────────────────────────────────────

    def enforce_cooldown(  # §15.9.4
        self,
        signal_history: List[Tuple[float, ScalingSignal]],
        policy: ScalingPolicy,
    ) -> bool:
        if not signal_history:
            return True

        latest_ts = max(ts for ts, _ in signal_history)
        elapsed = time.time() - latest_ts
        return elapsed >= policy.cooldown_sec
