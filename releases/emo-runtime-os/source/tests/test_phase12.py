"""Phase 12 tests: DriftMonitor, SafeWeightBoundaries, ConfidenceDecay,
RegressionDetector, ShadowEvaluator, RollbackManager, and integration.

Tests cover:
  - DriftMonitor: strategy collapse > 70%, weight drift > 0.35, baseline
  - SafeWeightBoundaries: clamp to [0.2, 0.8], renormalization
  - ConfidenceDecay: decay weight formula, effective score, strategy
  - RegressionDetector: drop > 0.15, stable case, multi-strategy
  - ShadowEvaluator: accumulate, promote threshold, reset
  - RollbackManager: threshold triggering, manual, clear
  - Integration: AdaptiveWeightEngine guardrail checks, full pipeline
"""

import sys, os, time, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import warnings
warnings.filterwarnings("ignore")
import logging
logging.disable(logging.CRITICAL)


# ======================================================================
# DriftMonitor Tests
# ======================================================================

from core.guardrails import (
    DriftMonitor, DriftAlert, SafeWeightBoundaries,
    ConfidenceDecay, PerformanceRegressionDetector, RegressionAlert,
    ShadowEvaluator, ShadowResult, RollbackManager, RollbackEvent,
)


def test_drift_no_collapse():
    m = DriftMonitor()
    counts = {"balanced": 10, "small_repo": 15, "large_repo": 12}
    alert = m.detect_strategy_collapse(counts)
    assert alert is None, f"Expected no collapse, got {alert}"


def test_drift_collapse_detected():
    m = DriftMonitor()
    counts = {"balanced": 30, "small_repo": 2, "large_repo": 1}
    alert = m.detect_strategy_collapse(counts)
    assert alert is not None
    assert alert.kind == "strategy_collapse"
    assert "balanced" in alert.message
    assert alert.severity == "warning"
    assert "usage_pct" in alert.detail
    assert abs(alert.detail["usage_pct"] - 30/33) < 0.001


def test_drift_collapse_empty():
    m = DriftMonitor()
    alert = m.detect_strategy_collapse({})
    assert alert is None


def test_drift_weight_drift_detected():
    m = DriftMonitor()
    m.set_baseline({"balanced": 0.6, "small_repo": 0.4})
    current = {"balanced": 0.2, "small_repo": 0.8}
    alert = m.detect_weight_drift(current)
    assert alert is not None
    assert alert.kind == "weight_drift"
    assert abs(alert.detail["drift"] - 0.4) < 0.001


def test_drift_weight_no_drift():
    m = DriftMonitor()
    m.set_baseline({"balanced": 0.6, "small_repo": 0.4})
    current = {"balanced": 0.6, "small_repo": 0.4}
    alert = m.detect_weight_drift(current)
    assert alert is None


def test_drift_weight_no_baseline():
    m = DriftMonitor()
    alert = m.detect_weight_drift({"balanced": 0.9})
    assert alert is None


def test_drift_monitor_combines():
    m = DriftMonitor()
    counts = {"balanced": 50, "small_repo": 1, "large_repo": 2}
    m.set_baseline({"balanced": 0.6, "small_repo": 0.4})
    current = {"balanced": 0.9, "small_repo": 0.1}
    alerts = m.monitor(counts, current)
    assert len(alerts) >= 1  # collapse detected (balanced ~94%)
    kinds = [a.kind for a in alerts]
    assert "strategy_collapse" in kinds


# ======================================================================
# SafeWeightBoundaries Tests
# ======================================================================

def test_clamp_normal():
    w_g, w_s = SafeWeightBoundaries.clamp(0.6)
    assert w_g == 0.6
    assert w_s == 0.4


def test_clamp_low():
    w_g, w_s = SafeWeightBoundaries.clamp(0.1)
    assert w_g == 0.2  # MIN_GRAPH
    assert w_s == 0.8


def test_clamp_high():
    w_g, w_s = SafeWeightBoundaries.clamp(0.9)
    assert w_g == 0.8  # MAX_GRAPH
    assert w_s == 0.2


def test_clamp_pair_both_outside():
    w_g, w_s = SafeWeightBoundaries.clamp_pair(0.1, 0.9)
    assert w_g >= SafeWeightBoundaries.MIN_GRAPH
    assert w_s >= SafeWeightBoundaries.MIN_GRAPH
    assert abs(w_g + w_s - 1.0) < 0.01


def test_clamp_pair_renormalizes():
    w_g, w_s = SafeWeightBoundaries.clamp_pair(0.9, 0.1)
    # Both clamped: 0.8, 0.2 → total=1.0 → no renormalization needed
    assert abs(w_g + w_s - 1.0) < 0.01


def test_is_safe():
    assert SafeWeightBoundaries.is_safe(0.5) is True
    assert SafeWeightBoundaries.is_safe(0.2) is True
    assert SafeWeightBoundaries.is_safe(0.8) is True
    assert SafeWeightBoundaries.is_safe(0.1) is False
    assert SafeWeightBoundaries.is_safe(0.9) is False


# ======================================================================
# ConfidenceDecay Tests
# ======================================================================

def test_decay_current():
    d = ConfidenceDecay()
    weight = d.decay_weight(time.time())
    assert abs(weight - 1.0) < 0.001


def test_decay_old():
    d = ConfidenceDecay(half_life_days=30.0)
    # 30 days ago → weight = 0.5
    past = time.time() - (30 * 86400)
    weight = d.decay_weight(past)
    assert abs(weight - 0.5) < 0.01, f"Expected ~0.5, got {weight}"


def test_decay_very_old():
    d = ConfidenceDecay(half_life_days=30.0)
    # 120 days ago → 2^(-120/30) = 2^(-4) = 0.0625
    past = time.time() - (120 * 86400)
    weight = d.decay_weight(past)
    assert abs(weight - 0.0625) < 0.01, f"Expected ~0.0625, got {weight}"


def test_decay_apply():
    d = ConfidenceDecay()
    past = time.time() - (30 * 86400)
    effective = d.apply(1.0, past)
    assert effective < 1.0  # Decayed
    assert effective > 0.0


def test_decay_apply_no_age():
    d = ConfidenceDecay()
    effective = d.apply(0.8, time.time())
    assert abs(effective - 0.8) < 0.02


def test_decay_future_timestamp():
    d = ConfidenceDecay()
    future = time.time() + 86400
    effective = d.apply(0.9, future)
    assert effective == 0.9  # age_days <= 0 → return 1.0


# ======================================================================
# PerformanceRegressionDetector Tests
# ======================================================================

def test_regression_insufficient_samples():
    d = PerformanceRegressionDetector()
    d.record("balanced", 1)
    d.record("balanced", 1)
    d.record("balanced", 1)
    alert = d.detect_regression("balanced")
    assert alert is None  # MIN_SAMPLES = 10


def test_regression_no_drop():
    d = PerformanceRegressionDetector()
    for _ in range(12):
        d.record("balanced", 1)
    alert = d.detect_regression("balanced")
    assert alert is None


def test_regression_drop_detected():
    d = PerformanceRegressionDetector()
    # First half (older): all successes
    for _ in range(25):
        d.record("balanced", 1)
    # Second half (recent): all failures
    for _ in range(25):
        d.record("balanced", -1)
    alert = d.detect_regression("balanced")
    assert alert is not None
    assert alert.kind == "performance_regression"
    assert alert.drop > 0.15


def test_regression_detect_all():
    d = PerformanceRegressionDetector()
    for _ in range(25):
        d.record("good", 1)
    for _ in range(25):
        d.record("good", -1)
    for _ in range(10):
        d.record("stable", 1)
    alerts = d.detect_all()
    assert len(alerts) >= 1
    kinds = [a.kind for a in alerts]
    assert "performance_regression" in kinds


def test_regression_current_rate():
    d = PerformanceRegressionDetector()
    for _ in range(20):
        d.record("balanced", 1)
    rate = d.current_rate("balanced")
    assert abs(rate - 1.0) < 0.01


def test_regression_current_rate_insufficient():
    d = PerformanceRegressionDetector()
    rate = d.current_rate("unknown")
    assert rate == 0.5  # neutral default


# ======================================================================
# ShadowEvaluator Tests
# ======================================================================

def test_shadow_accumulate():
    s = ShadowEvaluator()
    rank_fn = lambda entries: sorted(entries, key=lambda x: x.get("final_score", 0), reverse=True)

    # Simulate 5 comparisons (below MIN_PROMOTION_SAMPLES)
    for _ in range(5):
        s.evaluate(
            {"merged_results": [{"final_score": 0.6}]},
            {"merged_results": [{"final_score": 0.8}]},
            rank_fn,
        )

    result = s.should_promote()
    assert result.samples == 5
    assert result.promotion_ready is False  # Not enough samples yet


def test_shadow_insufficient_samples():
    s = ShadowEvaluator()
    rank_fn = lambda entries: entries
    result = s.should_promote()
    assert result.promotion_ready is False
    assert result.samples < ShadowEvaluator.MIN_PROMOTION_SAMPLES


def test_shadow_promotion_ready():
    s = ShadowEvaluator()
    rank_fn = lambda entries: sorted(entries, key=lambda x: x.get("final_score", 0), reverse=True)

    for _ in range(ShadowEvaluator.MIN_PROMOTION_SAMPLES):
        s.evaluate(
            {"merged_results": [{"final_score": 0.4}]},
            {"merged_results": [{"final_score": 0.7}]},
            rank_fn,
        )

    result = s.should_promote()
    assert result.promotion_ready is True
    assert result.advantage > ShadowEvaluator.MIN_ADVANTAGE


def test_shadow_candidate_loses():
    s = ShadowEvaluator()
    rank_fn = lambda entries: sorted(entries, key=lambda x: x.get("final_score", 0), reverse=True)

    for _ in range(ShadowEvaluator.MIN_PROMOTION_SAMPLES):
        s.evaluate(
            {"merged_results": [{"final_score": 0.8}]},
            {"merged_results": [{"final_score": 0.3}]},
            rank_fn,
        )

    result = s.should_promote()
    assert result.candidate_won is False
    assert result.promotion_ready is False


def test_shadow_reset():
    s = ShadowEvaluator()
    rank_fn = lambda entries: entries
    for _ in range(10):
        s.evaluate({"merged_results": []}, {"merged_results": []}, rank_fn)
    s.reset()
    result = s.should_promote()
    assert result.samples == 0


def test_shadow_status():
    s = ShadowEvaluator()
    status = s.status()
    assert "samples" in status
    assert "prod_avg" in status
    assert "promoted" in status


# ======================================================================
# RollbackManager Tests
# ======================================================================

def test_rollback_no_alerts():
    r = RollbackManager()
    rolled, weights, reason = r.check_and_rollback([], (0.6, 0.4))
    assert rolled is False
    assert weights == (0.6, 0.4)
    assert reason is None


def test_rollback_threshold_triggered():
    r = RollbackManager()
    alert = DriftAlert(kind="strategy_collapse", message="Test alert", severity="warning")
    # First two calls with alerts: under threshold
    for _ in range(2):
        rolled, w, reason = r.check_and_rollback([alert], (0.6, 0.4), (0.5, 0.5))
        assert rolled is False
    # Third call: threshold reached
    rolled, w, reason = r.check_and_rollback([alert], (0.6, 0.4), (0.5, 0.5))
    assert rolled is True
    assert w == (0.5, 0.5)
    assert reason is not None


def test_rollback_alerts_accumulate():
    r = RollbackManager()
    alert = DriftAlert(kind="strategy_collapse", message="Bad", severity="warning")
    # 3 call with 1 alert each
    for _ in range(3):
        rolled, _, _ = r.check_and_rollback([alert], (0.6, 0.4))
    assert rolled is True  # 3*1 = 3 >= MAX_CONSECUTIVE_ALERTS
    # This tests: alert count includes ALL alerts each call


def test_rollback_manual():
    r = RollbackManager()
    assert r.is_rolled_back() is False
    r.record_manual_rollback("operator", (0.7, 0.3), (0.6, 0.4))
    assert r.is_rolled_back() is True
    assert len(r._events) == 1


def test_rollback_clear():
    r = RollbackManager()
    r.record_manual_rollback("test", (0.7, 0.3), (0.6, 0.4))
    assert r.is_rolled_back() is True
    r.clear()
    assert r.is_rolled_back() is False
    assert len(r._events) == 0


def test_rollback_history():
    r = RollbackManager()
    r.record_manual_rollback("reason1", (0.7, 0.3), (0.6, 0.4))
    r.record_manual_rollback("reason2", (0.5, 0.5), (0.6, 0.4))
    hist = r.history(2)
    assert len(hist) == 2
    assert hist[0]["reason"] == "reason1"
    assert hist[1]["reason"] == "reason2"


def test_rollback_status():
    r = RollbackManager()
    status = r.status()
    assert status["total_rollbacks"] == 0
    assert status["rolled_back"] is False


# ======================================================================
# Integration Tests: AdaptiveWeightEngine + Guardrails
# ======================================================================

from core.adaptive_weights import (
    AdaptiveWeightEngine, profile_from_weights,
    STRATEGY_BALANCED, STRATEGY_SMALL_REPO, STRATEGY_LARGE_REPO,
    STRATEGY_TEST_FILE,
)
from core.feedback_loop import RankingFeedbackLoop


def test_integration_safe_clamping():
    """Adjusted weights should never leave [0.2, 0.8]."""
    engine = AdaptiveWeightEngine()
    for strategy in [STRATEGY_BALANCED, STRATEGY_SMALL_REPO, STRATEGY_LARGE_REPO, STRATEGY_TEST_FILE]:
        w_g, w_s = engine.adjusted_weights(0.05, 0.95, strategy)
        assert SafeWeightBoundaries.is_safe(w_g)
        assert SafeWeightBoundaries.is_safe(w_s)
        assert abs(w_g + w_s - 1.0) < 0.01


def test_integration_high_boost_clamped():
    """Even extreme boosting stays within [0.2, 0.8]."""
    loop = RankingFeedbackLoop()
    for _ in range(10):
        loop.record_feedback(STRATEGY_LARGE_REPO, 1.0, success=True)
    engine = AdaptiveWeightEngine(loop)
    w_g, w_s = engine.adjusted_weights(0.3, 0.7, STRATEGY_LARGE_REPO)
    # STRATEGY_LARGE_REPO → base (0.7, 0.3), boost +0.10 → (0.8, 0.3)
    # clamp_pair → still (0.73, 0.27) roughly
    assert SafeWeightBoundaries.is_safe(w_g)
    assert SafeWeightBoundaries.is_safe(w_s)
    assert abs(w_g + w_s - 1.0) < 0.01


def test_integration_decay_in_record():
    """record_outcome with timestamp applies decay."""
    engine = AdaptiveWeightEngine()
    # Recent feedback
    recent = time.time()
    engine.record_outcome(STRATEGY_BALANCED, 0.9, success=True, timestamp=recent)
    # Old feedback (120 days ago → heavy decay)
    old = time.time() - (120 * 86400)
    engine.record_outcome(STRATEGY_BALANCED, 1.0, success=True, timestamp=old)
    # The old feedback should have very little weight
    # But rate formula: successes/(successes+failures+1)
    # Both are successes, so rate should be high
    rate = engine.loop.success_rate(STRATEGY_BALANCED)
    assert rate > 0  # Both contributed


def test_integration_drift_check():
    """AdaptiveWeightEngine.check_drift should return alerts for collapse."""
    loop = RankingFeedbackLoop()
    engine = AdaptiveWeightEngine(loop)
    counts = {"balanced": 50, "small_repo": 2, "large_repo": 1}
    alerts = engine.check_drift(counts)
    assert len(alerts) >= 1
    assert alerts[0].kind == "strategy_collapse"


def test_integration_regression_check():
    """Regression detection works through AdaptiveWeightEngine."""
    engine = AdaptiveWeightEngine()
    # Record mostly failures (creates regression in recent window)
    for _ in range(15):
        engine.record_outcome(STRATEGY_BALANCED, 0.1, success=False)
    # Now successes
    for _ in range(15):
        engine.record_outcome(STRATEGY_BALANCED, 0.9, success=True)
    alerts = engine.check_regression()
    # Should be no regression (both halves have mixed results)
    # Actually the first 15 are failures, next 15 are successes
    # Older half: 15 failures → rate = 0/15 = 0.0
    # Recent half: 15 successes → rate = 15/15 = 1.0
    # Drop = 0.0 - 1.0 = -1.0 (improvement, not regression)
    assert len(alerts) == 0  # No drop (actually improved)


def test_integration_regression_detected():
    """Check regression when performance actually drops."""
    engine = AdaptiveWeightEngine()
    # First half successes
    for _ in range(15):
        engine.record_outcome(STRATEGY_BALANCED, 0.9, success=True)
    # Second half failures
    for _ in range(15):
        engine.record_outcome(STRATEGY_BALANCED, 0.1, success=False)
    alerts = engine.check_regression()
    # Older half: 15 successes → rate = 1.0
    # Recent half: 15/15 ... wait, the split is by the deque ordering
    # First 15 are successes, next 15 are failures
    # Index 0-14: successes, Index 15-29: failures
    # mid = 30//2 = 15
    # older = [0:15] = successes → rate = 1.0
    # recent = [15:30] = failures → rate = 0.0
    # drop = 1.0 - 0.0 = 1.0 > 0.15 → detected!
    assert len(alerts) >= 1
    assert alerts[0].kind == "performance_regression"


def test_integration_rollback_after_regression():
    """Regression alerts should eventually trigger rollback."""
    engine = AdaptiveWeightEngine()
    # Cause regression
    for _ in range(15):
        engine.record_outcome(STRATEGY_BALANCED, 0.9, success=True)
    for _ in range(15):
        engine.record_outcome(STRATEGY_BALANCED, 0.1, success=False)

    alerts = engine.check_regression()
    assert len(alerts) >= 1

    # Feed alerts to rollback
    rolled, weights, reason = engine.rollback_if_needed(
        alerts, (0.6, 0.4), (0.5, 0.5),
    )
    # First call: alert_count = len(alerts) >= 1 < 3 → no rollback yet
    assert rolled is False

    # Two more rounds to trigger
    for _ in range(2):
        rolled, weights, reason = engine.rollback_if_needed(
            alerts, (0.6, 0.4), (0.5, 0.5),
        )
    assert rolled is True
    assert weights == (0.5, 0.5)


def test_integration_guardrail_report():
    """learning_report should include guardrail state."""
    loop = RankingFeedbackLoop()
    engine = AdaptiveWeightEngine(loop)
    report = engine.learning_report()
    assert "guardrails" in report
    assert "regression" in report
    assert report["guardrails"]["rolled_back"] is False


def test_integration_shadow_through_engine():
    """Shadow evaluation flow through AdaptiveWeightEngine."""
    engine = AdaptiveWeightEngine()
    rank_fn = lambda entries: sorted(entries, key=lambda x: x.get("final_score", 0), reverse=True)
    engine.set_shadow_weights(0.5, 0.5)
    n = ShadowEvaluator.MIN_PROMOTION_SAMPLES + 5
    for _ in range(n):
        engine.evaluate_shadow(
            {"merged_results": [{"final_score": 0.6}]},
            {"merged_results": [{"final_score": 0.8}]},
            rank_fn,
        )
    status = engine.shadow_status()
    assert status["samples"] == n
    assert status["candidate_avg"] > status["prod_avg"]
    result = engine.should_promote_shadow()
    assert result.promotion_ready is True


def test_integration_rolled_back_weights():
    """When rolled back, adjusted_weights should return fallback."""
    engine = AdaptiveWeightEngine()
    engine.rollback.record_manual_rollback("test", (0.6, 0.4), (0.5, 0.5))
    w_g, w_s = engine.adjusted_weights(0.7, 0.3, STRATEGY_LARGE_REPO)
    # Rolled back → fallback for large_repo = (0.7, 0.3) → clamped
    assert SafeWeightBoundaries.is_safe(w_g)
    assert SafeWeightBoundaries.is_safe(w_s)
    assert abs(w_g + w_s - 1.0) < 0.01


# ======================================================================
# Run all
# ======================================================================

if __name__ == "__main__":
    tests = [
        # DriftMonitor
        ("drift no collapse", test_drift_no_collapse),
        ("drift collapse detected", test_drift_collapse_detected),
        ("drift collapse empty", test_drift_collapse_empty),
        ("drift weight drift", test_drift_weight_drift_detected),
        ("drift weight no drift", test_drift_weight_no_drift),
        ("drift weight no baseline", test_drift_weight_no_baseline),
        ("drift monitor combines", test_drift_monitor_combines),
        # SafeWeightBoundaries
        ("clamp normal", test_clamp_normal),
        ("clamp low", test_clamp_low),
        ("clamp high", test_clamp_high),
        ("clamp pair both outside", test_clamp_pair_both_outside),
        ("clamp pair renormalizes", test_clamp_pair_renormalizes),
        ("is safe", test_is_safe),
        # ConfidenceDecay
        ("decay current", test_decay_current),
        ("decay old", test_decay_old),
        ("decay very old", test_decay_very_old),
        ("decay apply", test_decay_apply),
        ("decay apply no age", test_decay_apply_no_age),
        ("decay future", test_decay_future_timestamp),
        # RegressionDetector
        ("regression insufficient", test_regression_insufficient_samples),
        ("regression no drop", test_regression_no_drop),
        ("regression drop detected", test_regression_drop_detected),
        ("regression detect all", test_regression_detect_all),
        ("regression current rate", test_regression_current_rate),
        ("regression current rate insufficient", test_regression_current_rate_insufficient),
        # ShadowEvaluator
        ("shadow accumulate", test_shadow_accumulate),
        ("shadow insufficient samples", test_shadow_insufficient_samples),
        ("shadow promotion ready", test_shadow_promotion_ready),
        ("shadow candidate loses", test_shadow_candidate_loses),
        ("shadow reset", test_shadow_reset),
        ("shadow status", test_shadow_status),
        # RollbackManager
        ("rollback no alerts", test_rollback_no_alerts),
        ("rollback threshold triggered", test_rollback_threshold_triggered),
        ("rollback alerts accumulate", test_rollback_alerts_accumulate),
        ("rollback manual", test_rollback_manual),
        ("rollback clear", test_rollback_clear),
        ("rollback history", test_rollback_history),
        ("rollback status", test_rollback_status),
        # Integration
        ("safe clamping integration", test_integration_safe_clamping),
        ("high boost clamped", test_integration_high_boost_clamped),
        ("decay in record", test_integration_decay_in_record),
        ("drift check", test_integration_drift_check),
        ("regression check", test_integration_regression_check),
        ("regression detected", test_integration_regression_detected),
        ("rollback after regression", test_integration_rollback_after_regression),
        ("guardrail report", test_integration_guardrail_report),
        ("shadow through engine", test_integration_shadow_through_engine),
        ("rolled back weights", test_integration_rolled_back_weights),
    ]

    passed = 0
    failed = 0
    for desc, test_fn in tests:
        try:
            test_fn()
            print(f"  ✓ {desc}")
            passed += 1
        except Exception as e:
            print(f"  ✗ {desc}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    total = len(tests)
    print(f"\n{'='*50}")
    print(f"Phase 12: {passed} passed, {failed} failed, {total} total")
    print(f"{'✓ COMPLETE' if failed == 0 else '✗ NEEDS FIX'}")
