"""
Relevance Filter — time decay, entropy filtering, low-relevance pruning.

Applies:
  - Time decay: score *= 2^(-age / half_life)
  - Entropy filter: reject high-entropy (noisy) text
  - Low-relevance pruning: remove entries below min_score
All operations preserve tenant_id isolation.
"""

from __future__ import annotations

import math
import re
import time
from collections import Counter
from typing import Any, Dict, List, Optional


_DEFAULT_HALF_LIFE_DAYS: float = 30.0
_HIGH_ENTROPY_THRESHOLD: float = 0.8
_MIN_RELEVANCE_SCORE: float = 0.05


class RelevanceFilter:
    """Filters entries by time decay, entropy, and minimum relevance."""

    def __init__(
        self,
        half_life_days: float = _DEFAULT_HALF_LIFE_DAYS,
        high_entropy_threshold: float = _HIGH_ENTROPY_THRESHOLD,
        min_relevance_score: float = _MIN_RELEVANCE_SCORE,
    ):
        self._half_life_days = half_life_days
        self._high_entropy_threshold = high_entropy_threshold
        self._min_relevance_score = min_relevance_score

    # ── time decay ─────────────────────────────────────────────

    def apply_time_decay(self, entry: dict, half_life_days: Optional[float] = None) -> float:
        """Apply exponential time decay to an entry's score.

        score *= 2^(-age_days / half_life_days)
        """
        hl = half_life_days or self._half_life_days
        now = time.time()
        created = entry.get("created_at", now)
        age_seconds = max(now - created, 0.0)
        age_days = age_seconds / 86400.0
        decay = 2.0 ** (-age_days / hl)
        current_score = entry.get("relevance_score", entry.get("semantic_score", 1.0))
        decayed = current_score * decay
        entry["relevance_score"] = round(decayed, 4)
        entry["decay_factor"] = round(decay, 4)
        return decay

    # ── entropy ────────────────────────────────────────────────

    @staticmethod
    def calculate_entropy(text: str) -> float:
        """Calculate Shannon entropy of a text string.

        High entropy indicates random/noisy data.
        Normalized to [0.0, 1.0] by dividing by log2(num_chars).
        """
        if not text or not text.strip():
            return 0.0
        text = text.strip()
        freq = Counter(text)
        total = len(text)
        entropy = 0.0
        for count in freq.values():
            p = count / total
            if p > 0:
                entropy -= p * math.log2(p)
        max_entropy = math.log2(min(total, 256))
        if max_entropy == 0:
            return 0.0
        return min(entropy / max_entropy, 1.0)

    def is_high_entropy(self, text: str) -> bool:
        """Check if text exceeds the high entropy threshold."""
        return self.calculate_entropy(text) >= self._high_entropy_threshold

    # ── filtering ──────────────────────────────────────────────

    def filter_low_relevance(self, entries: List[dict], min_score: Optional[float] = None) -> List[dict]:
        """Remove entries below minimum relevance score.

        Also removes high-entropy text payloads and applies time decay.
        """
        if not entries:
            return []
        threshold = min_score or self._min_relevance_score
        filtered: List[dict] = []
        for e in entries:
            self.apply_time_decay(e)
            score = e.get("relevance_score", 0.0)
            if score < threshold:
                continue
            payload_text = str(e.get("payload", {}))
            if self.is_high_entropy(payload_text):
                continue
            filtered.append(e)
        return filtered

    def set_entropy_threshold(self, threshold: float) -> None:
        self._high_entropy_threshold = threshold

    def set_min_relevance(self, score: float) -> None:
        self._min_relevance_score = score
