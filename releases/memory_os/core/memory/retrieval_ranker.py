"""
Retrieval Ranker — fuses semantic_score × priority_weight × recency_decay.

Combines three signals into a single relevance_score:
1. semantic_score — cosine similarity from SemanticIndex
2. priority_weight — router classification priority (project > agent > global)
3. recency_factor — time decay based on created_at

Applies min_relevance_threshold to filter weak results.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional


_RECENCY_HALF_LIFE: float = 86400.0  # 24 hours in seconds
_PRIORITY_WEIGHTS: dict = {
    "project": 1.0,
    "agent": 0.8,
    "global": 0.6,
}


class RetrievalRanker:
    """Merges semantic, priority, and recency signals into a single rank score."""

    def __init__(
        self,
        scope: str = "project",
        min_relevance_threshold: float = 0.1,
    ):
        self._scope = scope
        self._min_relevance_threshold = min_relevance_threshold

    def rank_results(
        self,
        results: List[dict],
        router_context: Optional[dict] = None,
    ) -> List[dict]:
        """Rank results by fused score and apply relevance filter.

        Args:
            results: List of result dicts with at least semantic_score and created_at.
            router_context: Optional dict with classification, scope, etc.

        Returns:
            Ranked results sorted by relevance_score descending, filtered by threshold.
        """
        if not results:
            return []
        now = time.time()
        scope = (router_context or {}).get("scope", self._scope)
        priority_weight = _PRIORITY_WEIGHTS.get(scope, 1.0)
        scored: List[dict] = []
        for r in results:
            semantic = r.get("semantic_score", 0.0)
            created = r.get("created_at", now)
            age = max(now - created, 0.0)
            recency_factor = 2.0 ** (-age / _RECENCY_HALF_LIFE)
            relevance = semantic * priority_weight * recency_factor
            r["priority_weight"] = priority_weight
            r["recency_factor"] = round(recency_factor, 4)
            r["relevance_score"] = round(relevance, 4)
            if relevance >= self._min_relevance_threshold:
                scored.append(r)
        scored.sort(key=lambda x: x["relevance_score"], reverse=True)
        return scored

    def set_threshold(self, threshold: float) -> None:
        self._min_relevance_threshold = threshold
