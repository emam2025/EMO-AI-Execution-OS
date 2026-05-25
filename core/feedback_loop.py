"""Ranking Feedback Loop – Phase 11 Self-Tuning Layer.

Tracks per-query quality signals and computes strategy-level success
rates for the AdaptiveWeightEngine.

Feedback signals:
    clicked_top1        1.0   user clicked the top result
    accepted_answer     1.0   user accepted the answer
    ignored_result     -0.5   user ignored the result
    manual_correct      1.0   user manually selected a different result
    dwell_time_long     0.3   user spent time on the result
    dwell_time_short   -0.2   user quickly dismissed

Quality tracking:
    Each strategy profile records success/failure counts.
    success_rate = successes / (successes + failures + 1)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger("emo_ai.feedback_loop")

# Feedback signal definitions
FEEDBACK_SIGNALS: Dict[str, float] = {
    "clicked_top1": 1.0,
    "accepted_answer": 1.0,
    "manual_correct": 1.0,
    "dwell_time_long": 0.3,
    "ignored_result": -0.5,
    "dwell_time_short": -0.2,
}


# Performance history for a single strategy profile
@dataclass
class StrategyStats:
    name: str = "balanced"
    successes: int = 0
    failures: int = 0
    avg_feedback: float = 0.0
    total_queries: int = 0

    @property
    def success_rate(self) -> float:
        denom = self.successes + self.failures + 1
        return self.successes / denom


class RankingFeedbackLoop:
    """Tracks quality per strategy and computes success rates.

    Usage:
        loop = RankingFeedbackLoop()
        loop.record_feedback("balanced", 0.9, success=True)
        stats = loop.get_strategy_stats("balanced")
        rate = loop.success_rate("balanced")
    """

    def __init__(self):
        self._strategies: Dict[str, StrategyStats] = {}
        self._recent_feedback: list = []

    # ── public API ──────────────────────────────────────────────────────

    def record_feedback(
        self,
        strategy: str,
        feedback_score: float,
        success: Optional[bool] = None,
    ) -> None:
        """Record a single feedback event for a strategy.

        Args:
            strategy: Weight profile name ("balanced", "small_repo", …)
            feedback_score: Raw score from feedback signal [-1, 1]
            success: Explicit success flag (True/False).  If None, derived
                     from feedback_score >= 0.5.
        """
        if success is None:
            success = feedback_score >= 0.5

        if strategy not in self._strategies:
            self._strategies[strategy] = StrategyStats(name=strategy)

        stats = self._strategies[strategy]
        stats.total_queries += 1

        if success:
            stats.successes += 1
        else:
            stats.failures += 1

        # Running average
        n = stats.total_queries
        stats.avg_feedback = (
            (stats.avg_feedback * (n - 1) + feedback_score) / n
        )

        self._recent_feedback.append({
            "strategy": strategy,
            "score": feedback_score,
            "success": success,
            "cumulative_rate": stats.success_rate,
        })

    def success_rate(self, strategy: str) -> float:
        """Return the success rate for a strategy (smoothed)."""
        if strategy not in self._strategies:
            return 0.5  # neutral starting value
        return self._strategies[strategy].success_rate

    def get_strategy_stats(self, strategy: str) -> StrategyStats:
        if strategy not in self._strategies:
            return StrategyStats(name=strategy)
        return self._strategies[strategy]

    def all_strategies(self) -> Dict[str, StrategyStats]:
        return dict(self._strategies)

    def recent_feedback(self, n: int = 10) -> list:
        return self._recent_feedback[-n:]

    def best_strategy(self) -> str:
        """Return the strategy with the highest success rate."""
        if not self._strategies:
            return "balanced"
        best = max(
            self._strategies.items(),
            key=lambda kv: kv[1].success_rate,
        )
        return best[0]

    def worst_strategy(self) -> str:
        """Return the strategy with the lowest success rate."""
        if not self._strategies:
            return "balanced"
        worst = min(
            self._strategies.items(),
            key=lambda kv: kv[1].success_rate,
        )
        return worst[0]

    def quality_report(self) -> Dict[str, Any]:
        """Full quality report across all strategies."""
        return {
            "strategies": {
                name: {
                    "successes": s.successes,
                    "failures": s.failures,
                    "success_rate": round(s.success_rate, 3),
                    "avg_feedback": round(s.avg_feedback, 3),
                    "total_queries": s.total_queries,
                }
                for name, s in self._strategies.items()
            },
            "best_strategy": self.best_strategy(),
            "worst_strategy": self.worst_strategy(),
            "recent_count": len(self._recent_feedback),
        }

    # ── bulk import from QueryReplay ────────────────────────────────────

    def import_from_replay(
        self,
        logs: list,
    ) -> int:
        """Import QueryLog entries retroactively.

        Args:
            logs: list of QueryLog objects (or dicts with strategy/feedback)

        Returns: number of entries imported.
        """
        count = 0
        for log in logs:
            if isinstance(log, dict):
                strategy = log.get("strategy", "balanced")
                fb = log.get("feedback")
                success = log.get("success")
            else:
                strategy = getattr(log, "strategy", "balanced")
                fb = getattr(log, "feedback", None)
                success = getattr(log, "success", None)
            if fb is not None:
                self.record_feedback(
                    strategy, float(fb),
                    success=bool(success) if success else None,
                )
                count += 1
        return count
