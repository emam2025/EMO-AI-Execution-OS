"""High-signal tests for Guardrails — constants, thresholds, boundary checks.

Tests target exposed invariants without requiring complex construction.
"""

import pytest

from core.guardrails import (
    DriftMonitor,
    SafeWeightBoundaries,
    ConfidenceDecay,
    DriftAlert,
)


class TestDriftMonitorConstants:
    """Invariant: threshold constants must be at module or class level."""

    def test_collapse_threshold_exists(self):
        """COLLAPSE_THRESHOLD must be defined on DriftMonitor."""
        assert hasattr(DriftMonitor, "COLLAPSE_THRESHOLD")
        val = DriftMonitor.COLLAPSE_THRESHOLD
        assert val == 0.70, f"Expected COLLAPSE_THRESHOLD=0.70, got {val}"

    def test_drift_threshold_exists(self):
        """DRIFT_THRESHOLD must be defined on DriftMonitor."""
        assert hasattr(DriftMonitor, "DRIFT_THRESHOLD")
        val = DriftMonitor.DRIFT_THRESHOLD
        assert val == 0.35, f"Expected DRIFT_THRESHOLD=0.35, got {val}"


class TestDriftAlertConstruction:
    """Invariant: DriftAlert must accept kind, message, severity, detail."""

    def test_drift_alert_minimal(self):
        """DriftAlert must be constructable with minimal args."""
        alert = DriftAlert(kind="test", message="test alert")
        assert alert.kind == "test"
        assert alert.message == "test alert"

    def test_drift_alert_severity_default(self):
        """DriftAlert severity must default to 'info'."""
        alert = DriftAlert(kind="test", message="test")
        assert alert.severity == "info"

    def test_drift_alert_full(self):
        """DriftAlert must accept all four params."""
        alert = DriftAlert(
            kind="weight_drift",
            message="drift detected",
            severity="warning",
            detail={"value": 0.5, "threshold": 0.35},
        )
        assert alert.kind == "weight_drift"
        assert alert.detail["value"] == 0.5


class TestSafeWeightBoundaries:
    """Invariant: w_graph in [0.20, 0.80], w_sem = 1 - w_graph."""

    def test_clamp_enforces_lower_bound(self):
        """clamp(0.1) must return (0.20, 0.80)."""
        w_graph, w_sem = SafeWeightBoundaries.clamp(0.1)
        assert w_graph == pytest.approx(0.20, abs=1e-6)
        assert w_sem == pytest.approx(0.80, abs=1e-6)

    def test_clamp_enforces_upper_bound(self):
        """clamp(0.9) must return (0.80, 0.20)."""
        w_graph, w_sem = SafeWeightBoundaries.clamp(0.9)
        assert w_graph == pytest.approx(0.80, abs=1e-6)
        assert w_sem == pytest.approx(0.20, abs=1e-6)

    def test_clamp_within_bounds_preserves_value(self):
        """clamp(0.5) must return (0.50, 0.50)."""
        w_graph, w_sem = SafeWeightBoundaries.clamp(0.5)
        assert w_graph == pytest.approx(0.50, abs=1e-6)
        assert w_sem == pytest.approx(0.50, abs=1e-6)

    def test_is_safe_true_for_valid_range(self):
        """is_safe(0.5) must return True."""
        assert SafeWeightBoundaries.is_safe(0.5) is True

    def test_is_safe_false_for_out_of_range(self):
        """is_safe(0.1) must return False (below lower bound)."""
        assert SafeWeightBoundaries.is_safe(0.1) is False
        assert SafeWeightBoundaries.is_safe(0.9) is False


class TestConfidenceDecayFormula:
    """Invariant: decay = 2^(-age_days / half_life_days), age <= 0 -> 1.0."""

    def test_decay_future_returns_one(self):
        """decay_weight with future timestamp must return 1.0."""
        decay = ConfidenceDecay()
        import time
        future = time.time() + 86400
        val = decay.decay_weight(future)
        assert val == pytest.approx(1.0, abs=1e-6)

    def test_apply_returns_float(self):
        """apply() with a timestamp must return a float."""
        decay = ConfidenceDecay()
        import time
        result = decay.apply(0.8, time.time())
        assert isinstance(result, float)
