"""Query Analytics – Phase 13 System Intelligence.

Detects:
  1. Ranking instability   – same query → different results over time
  2. Strategy collapse     – one strategy dominates > 90%
  3. Noisy embeddings      – high semantic score but poor feedback
  4. Dead graph zones      – symbols never retrieved
  5. Feedback skew         – feedback biased toward specific query types

Usage:
    analytics = QueryAnalytics(replay, store)
    report = analytics.full_report()
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from .metrics_store import MetricsStore, EVENT_QUERY_EXECUTED
from .query_replay import QueryReplay

logger = logging.getLogger("emo_ai.query_analytics")


# ======================================================================
# Data types
# ======================================================================

@dataclass
class InstabilityRecord:
    query: str = ""
    score_delta: float = 0.0
    rank_changes: int = 0
    symbol_set_churn: float = 0.0  # fraction of symbols that changed
    count: int = 0


@dataclass
class CollapseReport:
    collapsed: bool = False
    dominant_strategy: str = ""
    usage_pct: float = 0.0
    threshold: float = 0.9


@dataclass
class NoisyEmbedding:
    symbol_id: str = ""
    avg_semantic_score: float = 0.0
    avg_feedback: float = 0.0
    gap: float = 0.0  # sem_score - feedback (positive = noisy)
    sample_count: int = 0


class QueryAnalytics:
    """Reads from QueryReplay + MetricsStore to produce intelligence.

    Usage:
        analytics = QueryAnalytics(replay, store)
        # ── Pre-compute (reads all data once, caches results)
        analytics.analyze()
        # ── Access results
        print(analytics.instability_report)
        print(analytics.collapse_report)
        print(analytics.noisy_embeddings)
        print(analytics.dead_zones)
        print(analytics.feedback_skew)

        # ── Or get everything at once
        report = analytics.full_report()
    """

    # Thresholds
    INSTABILITY_MIN_OCCURRENCES = 3
    COLLAPSE_THRESHOLD = 0.90
    NOISE_MIN_SAMPLES = 3
    NOISE_GAP_THRESHOLD = 0.30

    def __init__(
        self,
        replay: Optional[QueryReplay] = None,
        store: Optional[MetricsStore] = None,
    ):
        self._replay = replay
        self._store = store

        # Results (populated after analyze())
        self.instability_report: List[InstabilityRecord] = []
        self.collapse_report: CollapseReport = CollapseReport()
        self.noisy_embeddings: List[NoisyEmbedding] = []
        self.dead_zones: List[str] = []
        self.feedback_skew: Dict[str, Any] = {}

    # ═══════════════════════════════════════════════════════════════════
    # Analysis pipeline
    # ═══════════════════════════════════════════════════════════════════

    def analyze(self) -> None:
        """Run all analysis passes.  Results available on instance attrs."""
        self._detect_instability()
        self._detect_collapse()
        self._detect_noisy_embeddings()
        self._detect_feedback_skew()

    def full_report(self) -> Dict[str, Any]:
        """Run analysis and return everything as a dict."""
        self.analyze()
        return {
            "ranking_instability": [
                {
                    "query": ir.query,
                    "score_delta": ir.score_delta,
                    "rank_changes": ir.rank_changes,
                    "symbol_churn": ir.symbol_set_churn,
                    "occurrences": ir.count,
                }
                for ir in self.instability_report
            ],
            "strategy_collapse": {
                "collapsed": self.collapse_report.collapsed,
                "dominant_strategy": self.collapse_report.dominant_strategy,
                "usage_pct": self.collapse_report.usage_pct,
                "threshold": self.collapse_report.threshold,
            },
            "noisy_embeddings": [
                {
                    "symbol_id": ne.symbol_id,
                    "avg_semantic_score": ne.avg_semantic_score,
                    "avg_feedback": ne.avg_feedback,
                    "gap": ne.gap,
                    "sample_count": ne.sample_count,
                }
                for ne in self.noisy_embeddings
            ],
            "feedback_skew": self.feedback_skew,
        }

    # ═══════════════════════════════════════════════════════════════════
    # 1 – Ranking instability
    # ═══════════════════════════════════════════════════════════════════

    def _detect_instability(self) -> None:
        if not self._replay:
            self.instability_report = []
            return

        # Group queries by normalised text
        recent = self._replay.recent(200)
        groups: Dict[str, List[Any]] = defaultdict(list)
        for log in recent:
            key = log.text.strip().lower()
            groups[key].append(log)

        records: List[InstabilityRecord] = []
        for query_text, logs in groups.items():
            if len(logs) < self.INSTABILITY_MIN_OCCURRENCES:
                continue

            # Collect top-5 symbol IDs per execution
            symbol_sets: List[Set[str]] = []
            scores: List[float] = []
            for log in logs:
                top5 = log.results[:5]
                symbol_sets.append({r.get("symbol_id", "") for r in top5})
                scores.append(
                    top5[0].get("final_score", top5[0].get("score", 0))
                    if top5 else 0
                )

            # Score delta (max - min)
            score_delta = max(scores) - min(scores) if scores else 0.0

            # Rank changes: count symbol_id position shifts across runs
            rank_changes = self._count_rank_changes(logs)

            # Symbol set churn: average fraction of symbols that differ
            # between consecutive runs
            churns: List[float] = []
            for i in range(1, len(symbol_sets)):
                s1 = symbol_sets[i - 1]
                s2 = symbol_sets[i]
                union = s1 | s2
                intersection = s1 & s2
                churns.append(
                    1.0 - (len(intersection) / len(union)) if union else 0.0
                )
            avg_churn = sum(churns) / len(churns) if churns else 0.0

            records.append(InstabilityRecord(
                query=query_text,
                score_delta=round(score_delta, 4),
                rank_changes=rank_changes,
                symbol_set_churn=round(avg_churn, 4),
                count=len(logs),
            ))

        records.sort(key=lambda r: r.score_delta, reverse=True)
        self.instability_report = records

    # ═══════════════════════════════════════════════════════════════════
    # 2 – Strategy collapse
    # ═══════════════════════════════════════════════════════════════════

    def _detect_collapse(self) -> None:
        if not self._store:
            self.collapse_report = CollapseReport()
            return

        usage = self._store.strategy_usage()
        total = sum(usage.values())
        if total == 0:
            self.collapse_report = CollapseReport()
            return

        dominant = max(usage, key=usage.get)
        pct = usage[dominant] / total

        self.collapse_report = CollapseReport(
            collapsed=pct > self.COLLAPSE_THRESHOLD,
            dominant_strategy=dominant,
            usage_pct=round(pct, 3),
            threshold=self.COLLAPSE_THRESHOLD,
        )

    # ═══════════════════════════════════════════════════════════════════
    # 3 – Noisy embeddings
    # ═══════════════════════════════════════════════════════════════════

    def _detect_noisy_embeddings(self) -> None:
        if not self._replay:
            self.noisy_embeddings = []
            return

        recent = self._replay.recent(500)

        # Group by symbol_id across all queries
        symbol_feedback: Dict[str, List[float]] = defaultdict(list)
        symbol_semantic: Dict[str, List[float]] = defaultdict(list)

        for log in recent:
            for res in log.results:
                sid = res.get("symbol_id", "")
                if not sid:
                    continue
                sem = res.get("semantic_score", res.get("score", 0))
                symbol_semantic[sid].append(sem)

        for log in recent:
            sid = log.results[0].get("symbol_id", "") if log.results else ""
            if not sid:
                continue
            if log.feedback is not None:
                symbol_feedback[sid].append(log.feedback)

        noisy: List[NoisyEmbedding] = []
        for sid in symbol_semantic:
            sem_scores = symbol_semantic[sid]
            fb_scores = symbol_feedback.get(sid, [])
            if len(fb_scores) < self.NOISE_MIN_SAMPLES:
                continue
            avg_sem = sum(sem_scores) / len(sem_scores)
            avg_fb = sum(fb_scores) / len(fb_scores)
            gap = avg_sem - avg_fb
            if gap > self.NOISE_GAP_THRESHOLD:
                noisy.append(NoisyEmbedding(
                    symbol_id=sid,
                    avg_semantic_score=round(avg_sem, 4),
                    avg_feedback=round(avg_fb, 4),
                    gap=round(gap, 4),
                    sample_count=len(fb_scores),
                ))

        noisy.sort(key=lambda n: n.gap, reverse=True)
        self.noisy_embeddings = noisy

    # ═══════════════════════════════════════════════════════════════════
    # 4 – Dead graph zones
    # ═══════════════════════════════════════════════════════════════════

    def dead_graph_zones(
        self,
        all_graph_symbols: List[str],
        top_fraction: float = 0.3,
    ) -> List[str]:
        """Identify symbols that exist in the graph but are never retrieved.

        Args:
            all_graph_symbols: Complete list of symbol IDs in the graph.
            top_fraction: Consider top 30% of most-callable symbols as "should
                          be retrievable".

        Returns:
            Symbol IDs that never appear in query results.
        """
        if not self._replay or not all_graph_symbols:
            self.dead_zones = []
            return self.dead_zones

        # Get all symbol IDs that have appeared in any result
        retrieved: Set[str] = set()
        recent = self._replay.recent(500)
        for log in recent:
            for res in log.results:
                sid = res.get("symbol_id", "")
                if sid:
                    retrieved.add(sid)

        dead = [s for s in all_graph_symbols if s not in retrieved]
        self.dead_zones = dead
        return dead

    # ═══════════════════════════════════════════════════════════════════
    # 5 – Feedback skew
    # ═══════════════════════════════════════════════════════════════════

    def _detect_feedback_skew(self) -> None:
        if not self._replay:
            self.feedback_skew = {}
            return

        recent = self._replay.recent(500)
        if not recent:
            self.feedback_skew = {"has_data": False}
            return

        # By strategy
        strategy_feedback: Dict[str, List[float]] = defaultdict(list)
        # By symbol
        symbol_feedback: Dict[str, List[float]] = defaultdict(list)
        # By query length (short < 10 words, medium, long > 30)
        length_feedback: Dict[str, List[float]] = defaultdict(list)

        for log in recent:
            if log.feedback is None:
                continue
            strategy_feedback[log.strategy].append(log.feedback)

            top = log.results[0] if log.results else {}
            sid = top.get("symbol_id", "")
            if sid:
                symbol_feedback[sid].append(log.feedback)

            word_count = len(log.text.split())
            if word_count < 10:
                length_feedback["short"].append(log.feedback)
            elif word_count > 30:
                length_feedback["long"].append(log.feedback)
            else:
                length_feedback["medium"].append(log.feedback)

        # Compute skew indicators
        def avg(lst: List[float]) -> float:
            return sum(lst) / len(lst) if lst else 0.0

        self.feedback_skew = {
            "has_data": True,
            "by_strategy": {
                s: {
                    "avg": round(avg(v), 4),
                    "count": len(v),
                }
                for s, v in sorted(strategy_feedback.items())
            },
            "by_query_length": {
                s: {
                    "avg": round(avg(v), 4),
                    "count": len(v),
                }
                for s, v in sorted(length_feedback.items())
            },
            "most_skewed_symbol": (
                max(symbol_feedback, key=lambda s: abs(
                    avg(symbol_feedback[s]) - 0.5
                ))
                if symbol_feedback else ""
            ),
        }

    # ═══════════════════════════════════════════════════════════════════
    # Helpers
    # ═══════════════════════════════════════════════════════════════════

    @staticmethod
    def _count_rank_changes(logs: List[Any]) -> int:
        """Count how many times a symbol_id changed position across runs."""
        if len(logs) < 2:
            return 0

        # Build {symbol_id: [positions]} across all logs
        positions: Dict[str, List[int]] = {}
        for log in logs:
            for rank, res in enumerate(log.results[:10]):
                sid = res.get("symbol_id", "")
                if not sid:
                    continue
                if sid not in positions:
                    positions[sid] = [rank]
                else:
                    positions[sid].append(rank)

        changes = 0
        for sid, pos_list in positions.items():
            for i in range(1, len(pos_list)):
                if pos_list[i] != pos_list[i - 1]:
                    changes += 1
        return changes
