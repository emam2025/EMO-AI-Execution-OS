"""Phase F2 — Autoscaler oscillation prevention under fluctuating load.

Verifies that the Autoscaler does not oscillate (rapid UP/DOWN/UP)
when load fluctuates around the hysteresis band.

Ref: §15.9.4, Canon RULE 1 (Determinism)
"""

import time
import pytest

from core.runtime.control_plane.autoscaler import Autoscaler
from core.runtime.control_plane.oscillation_guard import (
    ConsecutiveCycleTracker,
    CooldownTimer,
    HysteresisEvaluator,
)
from core.runtime.models.control_plane_models import (
    ClusterSnapshot,
    LoadMetric,
    ScalingPolicy,
    ScalingSignal,
)


class TestAutoscalerNoOscillation:
    """Verifies oscillation prevention under fluctuating load.

    Tests:
      1. Fluctuating load around target → HOLD (no oscillation)
      2. Sustained high load for 2 cycles → UP
      3. Sustained low load for 2 cycles → DOWN
      4. Single high spike → HOLD (needs 2 consecutive)
      5. Cooldown prevents immediate re-scaling
      6. Hysteresis dead-band prevents UP/DOWN flip-flop
    """

    def setup_method(self):
        self.policy = ScalingPolicy(
            min_workers=1,
            max_workers=10,
            target_utilization=0.70,
            cooldown_sec=60.0,
            hysteresis_pct=0.10,
            scale_step=2,
        )

    def make_snapshot(self, cpu: float) -> ClusterSnapshot:
        return ClusterSnapshot(
            worker_count=4,
            load=LoadMetric(cpu_pct=cpu, mem_pct=50.0),
        )

    def test_fluctuating_load_around_target_holds(self):
        """Load oscillating around target → HOLD (no oscillation)."""
        autoscaler = Autoscaler()
        signals = []
        for cpu in [68.0, 72.0, 69.0, 71.0, 68.0, 73.0]:
            snap = self.make_snapshot(cpu) if cpu else self.make_snapshot(50)
            signals.append(autoscaler.evaluate_load(
                self.make_snapshot(cpu), self.policy,
            ))
        # All should be HOLD (boundary noise, not sustained)
        assert all(s == ScalingSignal.HOLD for s in signals)

    def test_sustained_high_load_two_cycles_triggers_up(self):
        """2 consecutive cycles above target+hysteresis → UP."""
        autoscaler = Autoscaler()
        snap_high = self.make_snapshot(85.0)
        r1 = autoscaler.evaluate_load(snap_high, self.policy)
        assert r1 == ScalingSignal.HOLD  # needs 2nd cycle
        r2 = autoscaler.evaluate_load(snap_high, self.policy)
        assert r2 == ScalingSignal.UP

    def test_sustained_low_load_two_cycles_triggers_down(self):
        """2 consecutive cycles below target-hysteresis → DOWN."""
        autoscaler = Autoscaler()
        snap_low = ClusterSnapshot(
            worker_count=2,  # only 1 above min — not enough for DRAIN
            load=LoadMetric(cpu_pct=30.0, mem_pct=25.0),
        )
        r1 = autoscaler.evaluate_load(snap_low, self.policy)
        assert r1 == ScalingSignal.HOLD
        r2 = autoscaler.evaluate_load(snap_low, self.policy)
        assert r2 == ScalingSignal.DOWN

    def test_single_high_spike_does_not_trigger_up(self):
        """Single spike above band → HOLD (not 2 consecutive)."""
        autoscaler = Autoscaler()
        snap_high = self.make_snapshot(85.0)
        snap_normal = self.make_snapshot(50.0)
        r1 = autoscaler.evaluate_load(snap_high, self.policy)
        r2 = autoscaler.evaluate_load(snap_normal, self.policy)
        assert r1 == ScalingSignal.HOLD
        assert r2 == ScalingSignal.HOLD

    def test_cooldown_prevents_immediate_rescaling(self):
        """After UP, cooldown prevents another action."""
        autoscaler = Autoscaler()
        snap_high = self.make_snapshot(85.0)
        autoscaler.evaluate_load(snap_high, self.policy)
        autoscaler.evaluate_load(snap_high, self.policy)  # → UP
        autoscaler.apply_scaling(6, self.policy, current_workers=4)

        # Soon after, check evaluate (cooldown active → HOLD)
        result = autoscaler.evaluate_load(snap_high, self.policy)
        assert result == ScalingSignal.HOLD, "Cooldown should block immediate re-scale"

    def test_hysteresis_band_prevents_flip_flop(self):
        """Load near band edge doesn't cause UP/DOWN flip-flop."""
        autoscaler = Autoscaler()
        # Gradual load changes near the band edge
        loads = [75.0, 76.0, 78.0, 77.0, 79.0, 81.0, 80.0, 78.0, 76.0, 74.0]
        prev = ScalingSignal.HOLD
        for cpu in loads:
            sig = autoscaler.evaluate_load(self.make_snapshot(cpu), self.policy)
            # Never flip directly UP→DOWN or DOWN→UP
            assert not (prev == ScalingSignal.UP and sig == ScalingSignal.DOWN)
            assert not (prev == ScalingSignal.DOWN and sig == ScalingSignal.UP)
            prev = sig

    def test_drain_signal_on_sustained_surplus(self):
        """Sustained low load with surplus → DRAIN."""
        autoscaler = Autoscaler()
        snap = ClusterSnapshot(
            worker_count=10,  # surplus above min_workers=1
            load=LoadMetric(cpu_pct=20.0, mem_pct=25.0),
        )
        autoscaler.evaluate_load(snap, self.policy)
        sig = autoscaler.evaluate_load(snap, self.policy)
        assert sig == ScalingSignal.DRAIN
