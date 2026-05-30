"""
Token Budget Optimizer — dynamic budget enforcement with critical entity priority.

Ensures ContextWindow never exceeds token_budget even under heavy load.
Preserves critical entities (weight ≥ 0.8 or relationship_count ≥ 3).
Estimation uses chars/4 with +10% safety margin.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Tuple


_SAFETY_MARGIN: float = 1.10
_CRITICAL_WEIGHT_THRESHOLD: float = 0.8
_CRITICAL_RELATIONSHIP_COUNT: int = 3


class BudgetExceededError(Exception):
    """Raised when budget cannot be satisfied even with minimum entries."""


class TokenOptimizer:
    """Optimizes token allocation within budget constraints."""

    def __init__(
        self,
        safety_margin: float = _SAFETY_MARGIN,
        critical_weight: float = _CRITICAL_WEIGHT_THRESHOLD,
        critical_relationship_count: int = _CRITICAL_RELATIONSHIP_COUNT,
    ):
        self._safety_margin = safety_margin
        self._critical_weight = critical_weight
        self._critical_relationship_count = critical_relationship_count

    # ── estimation ─────────────────────────────────────────────

    @staticmethod
    def estimate_tokens(data: Any) -> int:
        """Estimate token count with +10% safety margin.

        chars / 4 is the baseline; margin overestimates slightly.
        """
        raw = json.dumps(data, default=str) if not isinstance(data, str) else data
        base = max(1, len(raw) // 4)
        return int(base * _SAFETY_MARGIN)

    # ── critical entity detection ──────────────────────────────

    @staticmethod
    def is_critical(entry: dict) -> bool:
        """Check if an entry is critical and must be preserved."""
        weight = entry.get("importance_weight", entry.get("weight", 0.0))
        if weight >= _CRITICAL_WEIGHT_THRESHOLD:
            return True
        rel_count = entry.get("relationship_count", 0)
        if rel_count >= _CRITICAL_RELATIONSHIP_COUNT:
            return True
        relevance = entry.get("relevance_score", entry.get("semantic_score", 0.0))
        if relevance >= 0.9:
            return True
        return False

    # ── budget enforcement ─────────────────────────────────────

    def enforce_budget(
        self,
        entries: List[dict],
        budget: int,
    ) -> Tuple[List[dict], int]:
        """Enforce token budget, prioritizing critical entities.

        Returns (selected_entries, tokens_used).
        Never exceeds budget. Raises BudgetExceededError if critical
        entities alone exceed budget.
        """
        if not entries:
            return [], 0
        effective_budget = int(budget / self._safety_margin)
        critical: List[dict] = []
        non_critical: List[dict] = []
        for e in entries:
            if self.is_critical(e):
                critical.append(e)
            else:
                non_critical.append(e)
        critical.sort(key=lambda x: x.get("relevance_score", x.get("semantic_score", 0.0)), reverse=True)
        non_critical.sort(key=lambda x: x.get("relevance_score", x.get("semantic_score", 0.0)), reverse=True)
        selected: List[dict] = []
        tokens_used = 0
        for e in critical:
            et = self.estimate_tokens(e.get("payload", {})) + self.estimate_tokens(e.get("key", ""))
            if tokens_used + et > effective_budget:
                raise BudgetExceededError(
                    f"Critical entities alone exceed budget: {tokens_used + et} > {effective_budget}"
                )
            selected.append(e)
            tokens_used += et
        for e in non_critical:
            et = self.estimate_tokens(e.get("payload", {})) + self.estimate_tokens(e.get("key", ""))
            if tokens_used + et > effective_budget:
                break
            selected.append(e)
            tokens_used += et
        return selected, tokens_used

    def critical_entities_first(self, entries: List[dict]) -> List[dict]:
        """Sort entries with critical entities first, preserving internal ordering."""
        critical = [e for e in entries if self.is_critical(e)]
        non_critical = [e for e in entries if not self.is_critical(e)]
        return critical + non_critical
