"""Adaptive Weight Engine – Phase 11 Self-Tuning + Phase 12 Guardrails.

Learns from historical query feedback and adjusts graph/semantic weights
dynamically.  No heavy ML — lightweight success-rate tracking.

Each weight strategy profile (balanced, small_repo, large_repo, test_file)
has its own success/failure history.  When a profile performs well its
boost increases; when it underperforms the boost decreases.

Strategy → profile mapping:
    balanced   → (0.6, 0.4)
    small_repo → (0.3, 0.7)
    large_repo → (0.7, 0.3)
    test_file  → (0.2, 0.8)

Boost logic:
    success_rate > 0.75  → +0.10 boost
    success_rate > 0.60  → +0.05 boost
    success_rate < 0.40  → -0.10 boost
    success_rate < 0.25  → -0.15 boost
    otherwise            →  0.00 boost

The boost is applied to the dominant weight in the profile:
    For graph-heavy profiles (w_graph > w_sem): boost → w_graph
    For semantic-heavy profiles (w_sem > w_graph): boost → w_sem
    For balanced: boost split equally

Phase 12 Guardrails integrated:
    - SafeWeightBoundaries for clamp
    - ConfidenceDecay for stale feedback
    - DriftMonitor for strategy/weight drift
    - RegressionDetector for performance drops
    - ShadowEvaluator for old-vs-new comparison
    - RollbackManager for automated rollback
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .feedback_loop import RankingFeedbackLoop
from .guardrails import (
    ConfidenceDecay,
    DriftAlert,
    DriftMonitor,
    PerformanceRegressionDetector,
    RegressionAlert,
    RollbackManager,
    SafeWeightBoundaries,
    ShadowEvaluator,
    ShadowResult,
)
from .metrics_store import (
    MetricsStore,
    EVENT_DRIFT_DETECTED,
    EVENT_FEEDBACK_RECEIVED,
    EVENT_REGRESSION_DETECTED,
    EVENT_RANKING_ADJUSTED,
    EVENT_ROLLBACK_EXECUTED,
    EVENT_SHADOW_PROMOTED,
)

logger = logging.getLogger("emo_ai.adaptive_weights")

# Strategy names — must match WeightsAdvisor profiles
STRATEGY_BALANCED = "balanced"
STRATEGY_SMALL_REPO = "small_repo"
STRATEGY_LARGE_REPO = "large_repo"
STRATEGY_TEST_FILE = "test_file"


# Strategy → base profile mapping
BASE_WEIGHTS: Dict[str, Tuple[float, float]] = {
    STRATEGY_BALANCED: (0.6, 0.4),
    STRATEGY_SMALL_REPO: (0.3, 0.7),
    STRATEGY_LARGE_REPO: (0.7, 0.3),
    STRATEGY_TEST_FILE: (0.2, 0.8),
}


def profile_from_weights(w_g: float, w_s: float) -> str:
    """Derive strategy name from base weight pair."""
    return {
        (0.6, 0.4): STRATEGY_BALANCED,
        (0.3, 0.7): STRATEGY_SMALL_REPO,
        (0.7, 0.3): STRATEGY_LARGE_REPO,
        (0.2, 0.8): STRATEGY_TEST_FILE,
    }.get((round(w_g, 1), round(w_s, 1)), STRATEGY_BALANCED)


class AdaptiveWeightEngine:
    """Learns from feedback to adjust graph/semantic weight balance.

    Phase 12 guardrails built-in:
        - SafeWeightBoundaries for [0.2, 0.8] clamp
        - ConfidenceDecay for stale feedback
        - DriftMonitor for strategy/weight drift
        - RegressionDetector for performance drops
        - ShadowEvaluator for old-vs-new comparison
        - RollbackManager for automated fallback

    Usage:
        engine = AdaptiveWeightEngine(feedback_loop)
        boost = engine.get_boost("balanced")
        w_g, w_s = engine.adjusted_weights(0.6, 0.4, "balanced")
    """

    # Success-rate thresholds for boost levels
    BOOST_HIGH = 0.10
    BOOST_MED = 0.05
    BOOST_NONE = 0.0
    BOOST_NEG = -0.10
    BOOST_LOW = -0.15

    def __init__(
        self,
        feedback_loop: Optional[RankingFeedbackLoop] = None,
        confidence_decay: Optional[ConfidenceDecay] = None,
        drift_monitor: Optional[DriftMonitor] = None,
        regression_detector: Optional[PerformanceRegressionDetector] = None,
        shadow_evaluator: Optional[ShadowEvaluator] = None,
        rollback_manager: Optional[RollbackManager] = None,
        metrics_store: Optional[MetricsStore] = None,
    ):
        self.loop = feedback_loop or RankingFeedbackLoop()
        self.decay = confidence_decay or ConfidenceDecay()
        self.drift = drift_monitor or DriftMonitor()
        self.regression = regression_detector or PerformanceRegressionDetector()
        self.shadow = shadow_evaluator or ShadowEvaluator()
        self.rollback = rollback_manager or RollbackManager()
        self.store = metrics_store

        # Track shadow weights for evaluation
        self._shadow_weights: Optional[Tuple[float, float]] = None
        self._last_weights: Optional[Tuple[float, float, str]] = None  # (w_g, w_s, strategy)

    # ── public API ──────────────────────────────────────────────────────

    def get_boost(self, strategy: str) -> float:
        """Return the learned weight boost for a strategy.

        Positive boost → increase the dominant weight.
        Negative boost → decrease the dominant weight.
        """
        rate = self.loop.success_rate(strategy)

        if rate > 0.75:
            return self.BOOST_HIGH
        if rate > 0.60:
            return self.BOOST_MED
        if rate < 0.25:
            return self.BOOST_LOW
        if rate < 0.40:
            return self.BOOST_NEG
        return self.BOOST_NONE

    def adjusted_weights(
        self,
        w_graph: float,
        w_sem: float,
        strategy: Optional[str] = None,
    ) -> Tuple[float, float]:
        """Apply learned boost + guardrails (safe clamp + rollback).

        Args:
            w_graph: Base graph weight
            w_sem: Base semantic weight
            strategy: Strategy name.  Auto-derived if None.

        Returns:
            (adjusted_w_graph, adjusted_w_sem) clamped to [0.2, 0.8]
        """
        if strategy is None:
            strategy = profile_from_weights(w_graph, w_sem)

        boost = self.get_boost(strategy)
        if boost != 0.0:
            # Apply boost to the dominant weight
            if w_graph > w_sem:
                w_graph += boost
            elif w_sem > w_graph:
                w_sem += boost
            else:
                # Balanced: split boost equally
                half = boost / 2
                w_graph += half
                w_sem += half

        # Phase 12 — SafeWeightBoundaries clamp
        w_graph, w_sem = SafeWeightBoundaries.clamp_pair(w_graph, w_sem)

        # Phase 12 — Rollback check (if we've rolled back, use fallback weights)
        if self.rollback.is_rolled_back():
            fallback_w = self._fallback_weights(strategy)
            return SafeWeightBoundaries.clamp_pair(*fallback_w)

        # Record weight change event if different from last known
        last = self._last_weights
        if last is not None and (round(w_graph, 2), round(w_sem, 2), strategy) != last:
            old_w_g, old_w_s, old_strat = last
            self._emit_weight_change(old_strat, old_w_g, old_w_s, strategy, w_graph, w_sem)
        self._last_weights = (round(w_graph, 2), round(w_sem, 2), strategy)

        return (w_graph, w_sem)

    def record_outcome(
        self,
        strategy: str,
        feedback_score: float,
        success: Optional[bool] = None,
        timestamp: Optional[float] = None,
    ) -> None:
        """Record a feedback outcome.

        Phase 12: ConfidenceDecay applies if timestamp is provided.
        Phase 13: Emits feedback.received telemetry event.
        """
        if timestamp is not None and success is not None:
            # Decay old feedback relevance
            effective = self.decay.apply(float(success), timestamp)
            self.loop.record_feedback(strategy, effective, bool(effective > 0.5))
        else:
            self.loop.record_feedback(strategy, feedback_score, success)

        # Track regression
        succ_int = 1 if (success is True or (success is None and feedback_score > 0)) else -1
        self.regression.record(strategy, succ_int)

        # Record feedback event
        if self.store:
            self.store.record_event(
                EVENT_FEEDBACK_RECEIVED,
                strategy=strategy,
                score_before=feedback_score,
                metadata={"success": succ_int == 1},
            )

    # ── guardrail checks ────────────────────────────────────────────────

    def check_drift(
        self, strategy_counts: Dict[str, int],
    ) -> List[DriftAlert]:
        """Run drift monitoring on strategy distribution and weights."""
        weights = {
            s: self.loop.success_rate(s)
            for s in BASE_WEIGHTS
        }
        return self.drift.monitor(strategy_counts, weights)

    def check_regression(self) -> List[RegressionAlert]:
        """Check all strategies for performance regression."""
        return self.regression.detect_all()

    def check_guardrails(
        self, strategy_counts: Dict[str, int],
    ) -> Dict[str, Any]:
        """Run all guardrail checks.  Returns alert summary."""
        drift_alerts = self.check_drift(strategy_counts)
        regression_alerts = self.check_regression()

        all_alerts = drift_alerts + regression_alerts  # type: ignore

        # Record events to MetricsStore
        if self.store:
            for da in drift_alerts:
                self.store.record_drift_alert(
                    drift_type=da.kind,
                    severity=da.severity,
                    details=da.detail,
                )
                self.store.record_event(
                    EVENT_DRIFT_DETECTED,
                    metadata={"kind": da.kind, "message": da.message,
                              "severity": da.severity, **da.detail},
                )
            for ra in regression_alerts:
                self.store.record_event(
                    EVENT_REGRESSION_DETECTED,
                    strategy=ra.metric.replace("success_rate_", ""),
                    metadata={"kind": ra.kind, "message": ra.message,
                              "drop": ra.drop, "severity": ra.severity},
                )

        return {
            "drift_alerts": [
                {"kind": a.kind, "message": a.message, "severity": a.severity}
                for a in drift_alerts
            ],
            "regression_alerts": [
                {
                    "kind": a.kind,
                    "message": a.message,
                    "severity": a.severity,
                    "metric": a.metric,
                    "drop": a.drop,
                }
                for a in regression_alerts
            ],
            "total_alerts": len(all_alerts),
        }

    # ── shadow evaluation ───────────────────────────────────────────────

    def set_shadow_weights(self, w_graph: float, w_sem: float) -> None:
        """Set candidate weights for shadow evaluation."""
        self._shadow_weights = (w_graph, w_sem)

    def evaluate_shadow(
        self,
        prod_result: Dict[str, Any],
        candidate_result: Dict[str, Any],
        rank_fn,
    ) -> None:
        """Feed a comparison pair into the shadow evaluator."""
        self.shadow.evaluate(prod_result, candidate_result, rank_fn)

        # Record shadow evaluation to store
        if self.store:
            prod_ranked = rank_fn(prod_result.get("merged_results", []))
            cand_ranked = rank_fn(candidate_result.get("merged_results", []))
            prod_score = self.shadow._score_ranked(prod_ranked)
            cand_score = self.shadow._score_ranked(cand_ranked)
            self.store.record_shadow_evaluation(prod_score, cand_score)

    def shadow_status(self) -> Dict[str, Any]:
        return self.shadow.status()

    def should_promote_shadow(self) -> ShadowResult:
        result = self.shadow.should_promote()
        if result.promotion_ready and self.store:
            self.store.record_shadow_evaluation(
                result.prod_score, result.candidate_score,
                promoted=True,
                metadata={"advantage": result.advantage, "samples": result.samples},
            )
            self.store.record_event(
                EVENT_SHADOW_PROMOTED,
                score_before=result.prod_score,
                score_after=result.candidate_score,
                metadata={"advantage": result.advantage, "samples": result.samples},
            )
        return result

    # ── rollback ────────────────────────────────────────────────────────

    def rollback_if_needed(
        self,
        alerts: List[Any],
        current_weights: Tuple[float, float],
        fallback_weights: Tuple[float, float] = (0.6, 0.4),
    ) -> Tuple[bool, Tuple[float, float], Optional[str]]:
        """Run rollback check.  Returns (did_rollback, weights, reason)."""
        if not alerts:
            return (False, current_weights, None)
        rolled, weights, reason = self.rollback.check_and_rollback(
            alerts, current_weights, fallback_weights,
        )
        if rolled and self.store:
            self.store.record_rollback(
                trigger_reason=reason or "guardrail_rollback",
                previous_weights=current_weights,
                restored_weights=weights,
            )
            self.store.record_event(
                EVENT_ROLLBACK_EXECUTED,
                old_weights=current_weights,
                new_weights=weights,
                metadata={"reason": reason},
            )
        return (rolled, weights, reason)

    def learning_report(self) -> Dict[str, Any]:
        """Return full learning state for inspection."""
        report = self.loop.quality_report()
        report["boosts"] = {
            s: round(self.get_boost(s), 2)
            for s in BASE_WEIGHTS
        }
        report["guardrails"] = {
            "drift_baseline": self.drift._baseline,
            "rolled_back": self.rollback.is_rolled_back(),
            "rollbacks": len(self.rollback._events),
            "shadow": self.shadow.status(),
        }
        report["regression"] = {
            s: {
                "current_rate": self.regression.current_rate(s),
                "samples": len(self.regression._history.get(s, [])),
            }
            for s in BASE_WEIGHTS
        }
        return report

    # ── internal helpers ────────────────────────────────────────────────

    def _emit_weight_change(
        self, old_strat: str, old_w_g: float, old_w_s: float,
        new_strat: str, new_w_g: float, new_w_s: float,
    ) -> None:
        if not self.store:
            return
        self.store.record_event(
            EVENT_RANKING_ADJUSTED,
            strategy=new_strat,
            old_weights=(old_w_g, old_w_s),
            new_weights=(new_w_g, new_w_s),
            metadata={
                "reason": "adaptive_boost",
                "old_strategy": old_strat,
                "boost": self.get_boost(new_strat),
            },
        )

    @staticmethod
    def _fallback_weights(strategy: str) -> Tuple[float, float]:
        """Return safe default weights when rolled back."""
        return BASE_WEIGHTS.get(strategy, (0.6, 0.4))
