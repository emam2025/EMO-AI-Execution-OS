"""Task 3 — Token Budget Enforcement: 5 tests.

Verifies zero budget overrun, critical entity priority, estimation.
"""

import pytest

from releases.memory_os.core.memory.token_optimizer import BudgetExceededError, TokenOptimizer


class TestTokenEstimation:
    def test_estimate_returns_positive(self):
        assert TokenOptimizer.estimate_tokens("hello") >= 1

    def test_longer_text_higher_estimate(self):
        short = TokenOptimizer.estimate_tokens("short")
        long = TokenOptimizer.estimate_tokens("a" * 1000)
        assert long > short


class TestBudgetEnforcement:
    @pytest.fixture
    def optimizer(self):
        return TokenOptimizer()

    def test_empty_entries(self, optimizer):
        result, tokens = optimizer.enforce_budget([], 1000)
        assert result == []
        assert tokens == 0

    def test_zero_budget_overrun(self, optimizer):
        entries = [
            {"entry_id": f"e{i}", "payload": {"data": "x" * 200}, "key": f"k{i}",
             "relevance_score": 0.5, "semantic_score": 0.5}
            for i in range(50)
        ]
        result, tokens = optimizer.enforce_budget(entries, 500)
        assert tokens <= 500

    def test_critical_entities_preserved(self, optimizer):
        entries = [
            {"entry_id": "critical", "payload": {"data": "important"}, "key": "k1",
             "importance_weight": 0.9, "relevance_score": 0.9},
            {"entry_id": "normal", "payload": {"data": "x" * 500}, "key": "k2",
             "importance_weight": 0.1, "relevance_score": 0.1},
        ]
        result, tokens = optimizer.enforce_budget(entries, 200)
        eids = [e["entry_id"] for e in result]
        assert "critical" in eids

    def test_critical_entities_first(self, optimizer):
        entries = [
            {"entry_id": "normal", "importance_weight": 0.1, "relevance_score": 0.1},
            {"entry_id": "critical", "importance_weight": 0.9, "relevance_score": 0.9},
            {"entry_id": "normal2", "importance_weight": 0.2, "relevance_score": 0.2},
        ]
        ordered = optimizer.critical_entities_first(entries)
        assert ordered[0]["entry_id"] == "critical"
