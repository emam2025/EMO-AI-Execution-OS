"""Phase F2 — Oscillation Prevention Guards.  # LAW-8 # RULE-1

CooldownTimer, HysteresisEvaluator, ConsecutiveCycleTracker.

§15.9.4: Cooldown and hysteresis are mandatory for oscillation-free scaling.

Ref: Canon LAW 8 (Guarded transitions), RULE 1 (Determinism)
"""

from __future__ import annotations

import time
from typing import List, Tuple

from core.runtime.models.control_plane_models import (
    ScalingPolicy,
    ScalingSignal,
)


class CooldownTimer:  # §15.9.4
    """Tracks cooldown between scaling actions.

    Cooldown starts after any UP or DOWN action.
    HOLD and DRAIN do not reset cooldown.
    """

    def __init__(self) -> None:
        self._last_action_time: float = 0.0

    @property
    def last_action_time(self) -> float:
        return self._last_action_time

    def record_action(self) -> None:
        self._last_action_time = time.time()

    def is_expired(self, policy: ScalingPolicy) -> bool:
        elapsed = time.time() - self._last_action_time
        return elapsed >= policy.cooldown_sec

    def remaining(self, policy: ScalingPolicy) -> float:
        elapsed = time.time() - self._last_action_time
        return max(0.0, policy.cooldown_sec - elapsed)

    def reset(self) -> None:
        self._last_action_time = 0.0


class HysteresisEvaluator:  # §15.9.4
    """Evaluates whether utilization is within the hysteresis dead-band.

    Dead-band: [target - hysteresis, target + hysteresis]
    Within this band → HOLD signal (no action).
    """

    def evaluate(
        self,
        utilization: float,
        policy: ScalingPolicy,
    ) -> ScalingSignal:
        band_low = policy.target_utilization - policy.hysteresis_pct
        band_high = policy.target_utilization + policy.hysteresis_pct

        if utilization > band_high:
            return ScalingSignal.UP
        if utilization < band_low:
            return ScalingSignal.DOWN
        return ScalingSignal.HOLD


class ConsecutiveCycleTracker:  # §15.9.4
    """Tracks consecutive scaling signals for oscillation prevention.

    A scaling action (UP/DOWN) requires the same signal for N
    consecutive evaluation cycles before being emitted.
    """

    def __init__(self, required_consecutive: int = 2) -> None:
        self._required = required_consecutive
        self._history: List[ScalingSignal] = []

    @property
    def history(self) -> List[ScalingSignal]:
        return list(self._history)

    def record(self, signal: ScalingSignal) -> None:
        self._history.append(signal)

    def count_consecutive(self, signal: ScalingSignal) -> int:
        count = 0
        for s in reversed(self._history):
            if s == signal:
                count += 1
            else:
                break
        return count

    def threshold_met(self, signal: ScalingSignal) -> bool:
        return self.count_consecutive(signal) >= self._required

    def reset(self) -> None:
        self._history.clear()
