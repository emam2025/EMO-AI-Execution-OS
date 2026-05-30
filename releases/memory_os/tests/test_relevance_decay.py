"""Task 2 — Relevance Decay & Entropy Filter: 10 tests.

Verifies time decay curve, entropy calculation, low-relevance pruning.
"""

import math
import time

import pytest

from releases.memory_os.core.memory.relevance_filter import RelevanceFilter


class TestTimeDecay:
    @pytest.fixture
    def filter(self):
        return RelevanceFilter(half_life_days=30.0)

    def test_recent_entry_has_high_decay(self, filter):
        entry = {"created_at": time.time(), "relevance_score": 1.0}
        filter.apply_time_decay(entry)
        assert entry["relevance_score"] > 0.9

    def test_old_entry_has_low_decay(self, filter):
        old_time = time.time() - (365 * 86400)
        entry = {"created_at": old_time, "relevance_score": 1.0}
        filter.apply_time_decay(entry)
        assert entry["relevance_score"] < 0.5

    def test_decay_curve_accuracy_vs_formula(self, filter):
        now = time.time()
        for days_ago in [0, 1, 7, 30, 90]:
            created = now - (days_ago * 86400)
            entry = {"created_at": created, "relevance_score": 1.0}
            decay = filter.apply_time_decay(entry)
            expected = 2.0 ** (-days_ago / 30.0)
            assert abs(decay - expected) < 0.01, f"days_ago={days_ago}: {decay} != {expected}"

    def test_custom_half_life(self, filter):
        old_time = time.time() - (30 * 86400)
        entry = {"created_at": old_time, "relevance_score": 1.0}
        filter.apply_time_decay(entry, half_life_days=15.0)
        assert entry["relevance_score"] < 0.3


class TestEntropy:
    @pytest.fixture
    def filter(self):
        return RelevanceFilter(high_entropy_threshold=0.8)

    def test_low_entropy_text(self, filter):
        text = "hello world this is normal text"
        entropy = filter.calculate_entropy(text)
        assert entropy < 0.8

    def test_high_entropy_text(self, filter):
        text = "".join(chr(i % 128) for i in range(1000))
        entropy = filter.calculate_entropy(text)
        assert entropy > 0.8

    def test_empty_text_zero_entropy(self, filter):
        assert filter.calculate_entropy("") == 0.0

    def test_high_entropy_rejected(self, filter):
        noisy = "".join(chr(i % 128) for i in range(500))
        assert filter.is_high_entropy(noisy) is True


class TestLowRelevanceFilter:
    @pytest.fixture
    def filter(self):
        return RelevanceFilter(min_relevance_score=0.1)

    def test_low_relevance_removed(self, filter):
        entries = [
            {"created_at": time.time(), "relevance_score": 0.01, "payload": {"msg": "low"}},
            {"created_at": time.time(), "relevance_score": 0.5, "payload": {"msg": "high"}},
        ]
        result = filter.filter_low_relevance(entries)
        assert len(result) == 1
        assert result[0]["relevance_score"] >= 0.1

    def test_high_entropy_removed(self, filter):
        noisy_text = "".join(chr(i % 128) for i in range(300))
        entries = [
            {"created_at": time.time(), "relevance_score": 0.9, "payload": noisy_text},
            {"created_at": time.time(), "relevance_score": 0.9, "payload": "aaaaaaa bbbbbbb ccccccc"},
        ]
        result = filter.filter_low_relevance(entries)
        assert len(result) == 1

    def test_active_data_not_deleted(self, filter):
        entries = [
            {"created_at": time.time(), "relevance_score": 1.0, "payload": "active critical entry"},
        ]
        result = filter.filter_low_relevance(entries)
        assert len(result) == 1
