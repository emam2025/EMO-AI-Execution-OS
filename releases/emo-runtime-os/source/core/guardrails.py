"""Drift Detection & Guardrails – Phase 12.

Ensures the self-tuning retrieval system stays stable, safe, and
monitorable.  Six sub-systems:

1. DriftMonitor        – detect strategy collapse + weight drift over time
2. SafeWeightBoundaries – clamp weights to [0.2, 0.8]
3. ConfidenceDecay     – decay old feedback so stale patterns fade
4. RegressionDetector  – detect success-rate drops > 0.15
5. ShadowEvaluator     – compare old vs new weights in background
6. RollbackManager     – orchestrate rollback when guardrails fire

Architecture:
    AdaptiveWeightEngine
            ↓
    ┌────── Guardrails ──────┐
    │  DriftMonitor          │
    │  SafeWeightBoundaries  │
    │  ConfidenceDecay       │
    │  RegressionDetector    │
    │  ShadowEvaluator       │
    │  RollbackManager       │
    └────────────────────────┘
            ↓
    HybridRetriever.rank()
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("emo_ai.guardrails")


# ======================================================================
# 1 – DriftMonitor
# ======================================================================

@dataclass
class DriftAlert:
    kind: str = ""
    message: str = ""
    severity: str = "info"  # "info" | "warning" | "critical"
    detail: Dict[str, Any] = field(default_factory=dict)


class DriftMonitor:
    """Monitors strategy distribution and weight drift over time.

    Alerts:
      - strategy_collapse: one strategy > 70% of recent queries
      - weight_drift:      weight change from baseline > 0.35
    """

    COLLAPSE_THRESHOLD = 0.70
    DRIFT_THRESHOLD = 0.35

    def __init__(self):
        self._baseline: Optional[Dict[str, float]] = None  # {strategy: pct}

    # ── public API ──────────────────────────────────────────────────────

    def set_baseline(self, strategy_counts: Dict[str, int]) -> None:
        total = sum(strategy_counts.values()) or 1
        self._baseline = {
            s: round(c / total, 3) for s, c in strategy_counts.items()
        }

    def detect_strategy_collapse(
        self, strategy_counts: Dict[str, int],
    ) -> Optional[DriftAlert]:
        """Check if a single strategy dominates > 70% of recent usage."""
        total = sum(strategy_counts.values())
        if total == 0:
            return None

        for strategy, count in strategy_counts.items():
            pct = count / total
            if pct > self.COLLAPSE_THRESHOLD:
                return DriftAlert(
                    kind="strategy_collapse",
                    message=(
                        f"Strategy '{strategy}' dominates {pct:.0%} of queries "
                        f"(threshold {self.COLLAPSE_THRESHOLD:.0%}). "
                        "Other strategies are being starved."
                    ),
                    severity="warning",
                    detail={
                        "strategy": strategy,
                        "usage_pct": round(pct, 3),
                        "threshold": self.COLLAPSE_THRESHOLD,
                        "counts": strategy_counts,
                    },
                )
        return None

    def detect_weight_drift(
        self, current_weights: Dict[str, float],
    ) -> Optional[DriftAlert]:
        """Check if any strategy's weight drifted > DRIFT_THRESHOLD from baseline."""
        if self._baseline is None:
            return None

        for strategy, current in current_weights.items():
            base = self._baseline.get(strategy, 0.0)
            drift = abs(current - base)
            if drift > self.DRIFT_THRESHOLD:
                return DriftAlert(
                    kind="weight_drift",
                    message=(
                        f"Strategy '{strategy}' drifted {drift:.0%} from baseline "
                        f"(baseline={base:.0%}, current={current:.0%}). "
                        f"Threshold is {self.DRIFT_THRESHOLD:.0%}."
                    ),
                    severity="warning",
                    detail={
                        "strategy": strategy,
                        "baseline": base,
                        "current": current,
                        "drift": round(drift, 3),
                        "threshold": self.DRIFT_THRESHOLD,
                    },
                )
        return None

    def monitor(
        self,
        strategy_counts: Dict[str, int],
        current_weights: Optional[Dict[str, float]] = None,
    ) -> List[DriftAlert]:
        """Run all drift checks. Returns list of active alerts."""
        alerts: List[DriftAlert] = []
        collapse = self.detect_strategy_collapse(strategy_counts)
        if collapse:
            alerts.append(collapse)
        if current_weights is not None:
            drift = self.detect_weight_drift(current_weights)
            if drift:
                alerts.append(drift)
        return alerts


# ======================================================================
# 2 – SafeWeightBoundaries
# ======================================================================

class SafeWeightBoundaries:
    """Ensures weights never leave safe operational range.

    Safe range: w_graph ∈ [0.20, 0.80]
    w_sem  = 1.0 - w_graph (derived, not clamped independently)
    """

    MIN_GRAPH = 0.20
    MAX_GRAPH = 0.80

    @classmethod
    def clamp(cls, w_graph: float) -> Tuple[float, float]:
        """Clamp w_graph to safe range; derive w_sem = 1 - w_graph."""
        w_graph = max(cls.MIN_GRAPH, min(cls.MAX_GRAPH, w_graph))
        return (round(w_graph, 2), round(1.0 - w_graph, 2))

    @classmethod
    def clamp_pair(cls, w_graph: float, w_sem: float) -> Tuple[float, float]:
        """Clamp both weights and renormalize to sum = 1.0."""
        w_graph = max(cls.MIN_GRAPH, min(cls.MAX_GRAPH, w_graph))
        w_sem = max(cls.MIN_GRAPH, min(cls.MAX_GRAPH, w_sem))
        total = w_graph + w_sem
        return (round(w_graph / total, 2), round(w_sem / total, 2))

    @classmethod
    def is_safe(cls, w_graph: float) -> bool:
        return cls.MIN_GRAPH <= w_graph <= cls.MAX_GRAPH


# ======================================================================
# 3 – ConfidenceDecay
# ======================================================================

class ConfidenceDecay:
    """Reduces influence of old feedback so stale patterns fade.

    Decay formula:
        weight = 2 ^ (-age_days / half_life_days)
        effective = score * weight

    Default half-life: 30 days (feedback loses half its weight monthly).
    """

    DEFAULT_HALF_LIFE_DAYS = 30.0

    def __init__(self, half_life_days: float = DEFAULT_HALF_LIFE_DAYS):
        self.half_life = half_life_days

    def decay_weight(self, timestamp: float) -> float:
        """Compute multiplicative decay weight for feedback age."""
        age_days = (time.time() - timestamp) / 86400.0
        if age_days <= 0:
            return 1.0
        return 2.0 ** (-age_days / self.half_life)

    def apply(
        self, feedback_score: float, timestamp: float,
    ) -> float:
        """Apply decay to a single feedback score."""
        return feedback_score * self.decay_weight(timestamp)

    def apply_to_strategy(
        self,
        loop: Any,  # RankingFeedbackLoop
        strategy: str,
        logs: List[Any],
    ) -> float:
        """Recompute a strategy's success_rate with decay applied."""
        weighted = 0.0
        total_weight = 0.0
        successes = 0
        failures = 0

        for log in logs:
            strat = getattr(log, "strategy", None) or log.get("strategy", "")
            if strat != strategy:
                continue
            fb = getattr(log, "feedback", None) or log.get("feedback")
            ts = getattr(log, "timestamp", None) or log.get("timestamp", 0.0)
            success = getattr(log, "success", None) or log.get("success", 0)

            if fb is not None:
                w = self.decay_weight(ts)
                weighted += float(fb) * w
                total_weight += w
                if success == 1:
                    successes += 1
                elif success == -1:
                    failures += 1

        if total_weight == 0:
            return loop.success_rate(strategy)

        av = weighted / total_weight
        # Derive effective rate from weighted average feedback
        return max(0.0, min(1.0, (av + 1.0) / 2.0))


# ======================================================================
# 4 – PerformanceRegressionDetector
# ======================================================================

@dataclass
class RegressionAlert:
    kind: str = ""
    message: str = ""
    severity: str = "warning"
    metric: str = ""
    previous_value: float = 0.0
    current_value: float = 0.0
    drop: float = 0.0
    threshold: float = 0.0


class PerformanceRegressionDetector:
    """Detects success-rate drops > 0.15 and precision@K degradation.

    Maintains a rolling window of recent performance per strategy.
    Compares latest window average to the preceding window average.
    """

    ROLLING_WINDOW = 50    # queries per window
    DROP_THRESHOLD = 0.15  # 15% drop triggers alert
    MIN_SAMPLES = 10       # minimum samples before checking

    def __init__(self):
        # {strategy: deque of (timestamp, success_int)}
        self._history: Dict[str, deque] = {}

    # ── public API ──────────────────────────────────────────────────────

    def record(self, strategy: str, success: int) -> None:
        if strategy not in self._history:
            self._history[strategy] = deque(maxlen=self.ROLLING_WINDOW * 2)
        self._history[strategy].append((time.time(), success))

    def detect_regression(
        self, strategy: str,
    ) -> Optional[RegressionAlert]:
        """Detect if the last window's success rate dropped significantly."""
        history = self._history.get(strategy, deque())
        if len(history) < self.MIN_SAMPLES:
            return None

        n = len(history)
        mid = n // 2
        recent = list(history)[mid:]
        older = list(history)[:mid]

        recent_rate = self._rate(recent)
        older_rate = self._rate(older)
        drop = older_rate - recent_rate

        if drop > self.DROP_THRESHOLD:
            return RegressionAlert(
                kind="performance_regression",
                message=(
                    f"Success rate for '{strategy}' dropped {drop:.1%} "
                    f"(was {older_rate:.1%}, now {recent_rate:.1%}). "
                    f"Threshold is {self.DROP_THRESHOLD:.0%}."
                ),
                severity="warning",
                metric=f"success_rate_{strategy}",
                previous_value=older_rate,
                current_value=recent_rate,
                drop=round(drop, 3),
                threshold=self.DROP_THRESHOLD,
            )
        return None

    def detect_all(self) -> List[RegressionAlert]:
        """Check all tracked strategies for regression."""
        alerts: List[RegressionAlert] = []
        for strategy in list(self._history.keys()):
            alert = self.detect_regression(strategy)
            if alert:
                alerts.append(alert)
        return alerts

    def current_rate(self, strategy: str) -> float:
        """Latest window success rate (0.5 if insufficient data)."""
        history = self._history.get(strategy, deque())
        if len(history) < self.MIN_SAMPLES:
            return 0.5
        recent = list(history)[-self.ROLLING_WINDOW:]
        return self._rate(recent)

    # ── internal ────────────────────────────────────────────────────────

    @staticmethod
    def _rate(samples: List[Tuple[float, int]]) -> float:
        if not samples:
            return 0.0
        successes = sum(1 for _, s in samples if s == 1)
        return successes / len(samples)


# ======================================================================
# 5 – ShadowEvaluator
# ======================================================================

@dataclass
class ShadowResult:
    candidate_won: bool = False
    promotion_ready: bool = False
    prod_score: float = 0.0
    candidate_score: float = 0.0
    advantage: float = 0.0
    samples: int = 0


class ShadowEvaluator:
    """Runs old vs new weights side-by-side in the background.

    Accumulates results across queries and decides whether the candidate
    weights should be promoted to production.
    """

    MIN_PROMOTION_SAMPLES = 20
    MIN_ADVANTAGE = 0.05  # candidate must be at least 5% better

    def __init__(self):
        self._prod_scores: List[float] = []
        self._candidate_scores: List[float] = []
        self._promoted = False

    # ── public API ──────────────────────────────────────────────────────

    def evaluate(
        self,
        prod_result: Dict[str, Any],
        candidate_result: Dict[str, Any],
        rank_fn: Callable,
    ) -> None:
        """Run both weight sets through the same rank function.

        Args:
            prod_result: Merged results dict from retrieve()
            candidate_result: Same query, different weights
            rank_fn: Function that accepts merged entries and returns ranked list
        """
        prod_ranked = rank_fn(prod_result.get("merged_results", []))
        cand_ranked = rank_fn(candidate_result.get("merged_results", []))

        prod_score = self._score_ranked(prod_ranked)
        cand_score = self._score_ranked(cand_ranked)

        self._prod_scores.append(prod_score)
        self._candidate_scores.append(cand_score)

    def should_promote(self) -> ShadowResult:
        """Check if candidate consistently outperforms production."""
        n = len(self._prod_scores)
        if n < self.MIN_PROMOTION_SAMPLES:
            return ShadowResult(samples=n)

        prod_avg = sum(self._prod_scores) / n
        cand_avg = sum(self._candidate_scores) / n
        advantage = cand_avg - prod_avg

        ready = (
            advantage > self.MIN_ADVANTAGE
            and cand_avg >= prod_avg
        )

        return ShadowResult(
            candidate_won=advantage > 0,
            promotion_ready=ready,
            prod_score=round(prod_avg, 4),
            candidate_score=round(cand_avg, 4),
            advantage=round(advantage, 4),
            samples=n,
        )

    def reset(self) -> None:
        self._prod_scores.clear()
        self._candidate_scores.clear()
        self._promoted = False

    def status(self) -> Dict[str, Any]:
        return {
            "samples": len(self._prod_scores),
            "prod_avg": round(sum(self._prod_scores) / max(1, len(self._prod_scores)), 4),
            "candidate_avg": round(sum(self._candidate_scores) / max(1, len(self._candidate_scores)), 4),
            "promoted": self._promoted,
        }

    # ── internal ────────────────────────────────────────────────────────

    @staticmethod
    def _score_ranked(ranked: List[Dict[str, Any]]) -> float:
        """Score a ranked list: higher is better.

        Weighted sum: top position has higher weight.
        score = Σ (1 / (pos + 1)) * entry.final_score
        """
        if not ranked:
            return 0.0
        total = 0.0
        for i, entry in enumerate(ranked[:10]):
            position_weight = 1.0 / (i + 1)
            total += position_weight * entry.get("final_score", 0)
        return total


# ======================================================================
# 6 – RollbackManager
# ======================================================================

@dataclass
class RollbackEvent:
    timestamp: float = 0.0
    reason: str = ""
    alert_type: str = ""
    strategy: str = ""
    weights_before: Tuple[float, float] = (0.0, 0.0)
    weights_after: Tuple[float, float] = (0.0, 0.0)


class RollbackManager:
    """Orchestrates rollback when guardrails fire.

    - Collects alerts from DriftMonitor + RegressionDetector
    - Decides if rollback is needed
    - Records rollback events
    - Returns safe fallback weights
    """

    MAX_CONSECUTIVE_ALERTS = 3  # trigger rollback after N alerts

    def __init__(self):
        self._events: List[RollbackEvent] = []
        self._alert_count: int = 0
        self._last_rollback: Optional[float] = None
        self._rolled_back: bool = False

    # ── public API ──────────────────────────────────────────────────────

    def check_and_rollback(
        self,
        alerts: List[Any],
        current_weights: Tuple[float, float],
        fallback_weights: Tuple[float, float] = (0.6, 0.4),
    ) -> Tuple[bool, Tuple[float, float], Optional[str]]:
        """Check alerts; rollback if too many consecutive alerts.

        Args:
            alerts: List of DriftAlert or RegressionAlert
            current_weights: (w_graph, w_sem) currently in use
            fallback_weights: safe default to roll back to

        Returns:
            (rolled_back, new_weights, reason_or_None)
        """
        if not alerts:
            self._alert_count = 0
            return (False, current_weights, None)

        self._alert_count += len(alerts)

        if self._alert_count >= self.MAX_CONSECUTIVE_ALERTS:
            reason = "; ".join(
                getattr(a, "message", str(a))[:80] for a in alerts
            )
            self._record_rollback(reason, "guardrail_alert",
                                  current_weights, fallback_weights)

            self._rolled_back = True
            self._alert_count = 0
            return (True, fallback_weights, reason)

        return (False, current_weights, None)

    def record_manual_rollback(
        self,
        reason: str,
        weights_before: Tuple[float, float],
        weights_after: Tuple[float, float],
    ) -> None:
        """Record a manual rollback (e.g., triggered by operator)."""
        self._record_rollback(reason, "manual", weights_before, weights_after)
        self._rolled_back = True

    def is_rolled_back(self) -> bool:
        return self._rolled_back

    def clear(self) -> None:
        self._events.clear()
        self._alert_count = 0
        self._last_rollback = None
        self._rolled_back = False

    def history(self, n: int = 10) -> List[Dict[str, Any]]:
        return [
            {
                "timestamp": e.timestamp,
                "reason": e.reason,
                "type": e.alert_type,
                "strategy": e.strategy,
                "weights_before": e.weights_before,
                "weights_after": e.weights_after,
            }
            for e in self._events[-n:]
        ]

    def status(self) -> Dict[str, Any]:
        return {
            "rolled_back": self._rolled_back,
            "alert_count": self._alert_count,
            "total_rollbacks": len(self._events),
            "last_rollback": self._last_rollback,
        }

    # ── internal ────────────────────────────────────────────────────────

    def _record_rollback(
        self, reason: str, alert_type: str,
        before: Tuple[float, float],
        after: Tuple[float, float],
    ) -> None:
        event = RollbackEvent(
            timestamp=time.time(),
            reason=reason,
            alert_type=alert_type,
            weights_before=before,
            weights_after=after,
        )
        self._events.append(event)
        self._last_rollback = event.timestamp
        logger.warning("Rollback: %s — (%s) → (%s)", reason, before, after)
