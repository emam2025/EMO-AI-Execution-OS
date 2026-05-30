"""Task 4 — R2-D Integration Tests: 15 tests.

Suites:
  TestCompressionIntegrity       (5)
  TestDecayAndEntropyBehavior    (5)
  TestBudgetUnderLoad            (5)
"""

import math
import tempfile
import time

import pytest

from releases.memory_os.core.memory.compression_engine import CompressionEngine
from releases.memory_os.core.memory.hierarchy import MemoryHierarchy
from releases.memory_os.core.memory.memory_router import MemoryRouter
from releases.memory_os.core.memory.relevance_filter import RelevanceFilter
from releases.memory_os.core.memory.token_optimizer import TokenOptimizer


# ── TestCompressionIntegrity (5) ────────────────────────────

class TestCompressionIntegrity:
    def test_compression_ratio_meets_40_percent(self):
        data = {"msg": "hello world " * 200, "status": "active " * 100, "detail": "long running " * 100}
        original = CompressionEngine.estimate_tokens(data)
        entries = [{"entry_id": "e1", "payload": data, "key": "k1"}]
        compressed = CompressionEngine.compress_to_graph_nodes(entries)
        compressed_tokens = CompressionEngine.estimate_tokens(compressed[0]["payload"])
        ratio = CompressionEngine.calculate_compression_ratio(original, compressed_tokens)
        assert ratio >= 0.4, f"ratio={ratio} < 0.4"

    def test_zero_critical_entity_loss(self):
        entries = [
            {"entry_id": "e1", "payload": {"critical": "data", "name": "tool_a", "status": "active", "version": "1.0"},
             "key": "k1"},
            {"entry_id": "e2", "payload": {"msg": "small"}, "key": "k2"},
        ]
        all_keys = set(e["key"] for e in entries)
        compressed = CompressionEngine.compress_to_graph_nodes(entries)
        compressed_keys = set(e["key"] for e in compressed)
        for k in all_keys:
            assert k in compressed_keys, f"Key {k} lost during compression"

    def test_dedup_preserves_unique_entries(self):
        entries = [
            {"entry_id": "e1", "payload": {"data": "unique_a"}, "key": "k1"},
            {"entry_id": "e2", "payload": {"data": "unique_b"}, "key": "k2"},
            {"entry_id": "e3", "payload": {"data": "unique_c"}, "key": "k3"},
        ]
        result = CompressionEngine.deduplicate_context(entries)
        assert len(result) == 3

    def test_hierarchy_with_compression_returns_results(self):
        tmp = tempfile.mkdtemp(prefix="r2d_c_")
        ce = CompressionEngine()
        h = MemoryHierarchy(base_dir=tmp, compression_engine=ce)
        h.store("episodic", "k1", {"data": "x" * 500}, "t1", "p1", "a1", "ct1", text="test")
        results = h.retrieve("episodic", {"scope": "project"}, "t1", "p1", "ct1")
        assert len(results) >= 1

    def test_compression_ratio_measurable(self):
        original = 1000
        compressed = 400
        ratio = CompressionEngine.calculate_compression_ratio(original, compressed)
        assert ratio == 0.6


# ── TestDecayAndEntropyBehavior (5) ─────────────────────────

class TestDecayAndEntropyBehavior:
    def test_time_decay_matches_formula(self):
        rf = RelevanceFilter()
        now = time.time()
        entry = {"created_at": now - (60 * 86400), "relevance_score": 1.0}
        decay = rf.apply_time_decay(entry)
        expected = 2.0 ** (-60 / 30.0)
        assert abs(decay - expected) < 0.01

    def test_entropy_filter_removes_noise(self):
        rf = RelevanceFilter(high_entropy_threshold=0.7)
        noisy = "".join(chr(i % 128) for i in range(200))
        assert rf.is_high_entropy(noisy) is True

    def test_relevance_filter_in_hierarchy(self):
        tmp = tempfile.mkdtemp(prefix="r2d_rf_")
        rf = RelevanceFilter(min_relevance_score=0.5)
        h = MemoryHierarchy(base_dir=tmp, relevance_filter=rf)
        h.store("episodic", "k1", {"data": "high"}, "t1", "p1", "a1", "ct1", text="high relevance data")
        results = h.retrieve("episodic", {"scope": "project"}, "t1", "p1", "ct1")
        assert isinstance(results, list)

    def test_high_entropy_text_identified(self):
        rf = RelevanceFilter()
        normal_text = "aaaaaaa bbbbbbb ccccccc"
        assert rf.is_high_entropy(normal_text) is False

    def test_decay_factor_recorded(self):
        rf = RelevanceFilter()
        entry = {"created_at": time.time() - (10 * 86400), "relevance_score": 1.0}
        rf.apply_time_decay(entry)
        assert "decay_factor" in entry
        assert entry["decay_factor"] > 0


# ── TestBudgetUnderLoad (5) ─────────────────────────────────

class TestBudgetUnderLoad:
    @pytest.fixture
    def optimizer(self):
        return TokenOptimizer()

    def test_zero_budget_overrun_under_load(self, optimizer):
        entries = [
            {"entry_id": f"e{i}", "payload": {"data": "x" * 100}, "key": f"k{i}",
             "relevance_score": 0.5, "semantic_score": 0.5}
            for i in range(100)
        ]
        result, tokens = optimizer.enforce_budget(entries, 1000)
        assert tokens <= 1000

    def test_optimization_latency_under_5ms(self, optimizer):
        entries = [
            {"entry_id": f"e{i}", "payload": {"data": "x" * 100}, "key": f"k{i}",
             "relevance_score": 0.5, "semantic_score": 0.5}
            for i in range(100)
        ]
        start = time.perf_counter()
        optimizer.enforce_budget(entries, 5000)
        elapsed = time.perf_counter() - start
        assert elapsed < 0.005, f"latency {elapsed*1000:.2f}ms >= 5ms"

    def test_critical_entities_under_load(self, optimizer):
        entries = (
            [{"entry_id": f"normal_{i}", "payload": {"data": "x" * 50}, "key": f"nk{i}",
              "importance_weight": 0.1, "relevance_score": 0.1}
             for i in range(95)]
            + [{"entry_id": f"critical_{i}", "payload": {"data": "important"}, "key": f"ck{i}",
                "importance_weight": 0.9, "relevance_score": 0.9}
               for i in range(5)]
        )
        result, tokens = optimizer.enforce_budget(entries, 500)
        result_ids = [e["entry_id"] for e in result]
        for i in range(5):
            assert f"critical_{i}" in result_ids

    def test_router_with_optimizer_returns_flags(self):
        tmp = tempfile.mkdtemp(prefix="r2d_rtr_")
        ce = CompressionEngine()
        rf = RelevanceFilter()
        to = TokenOptimizer()
        h = MemoryHierarchy(base_dir=tmp, compression_engine=ce, relevance_filter=rf, token_optimizer=to)
        h.store("episodic", "k1", {"data": "test"}, "t1", "p1", "a1", "ct1", text="test data")
        router = MemoryRouter(hierarchy=h, tenant_id="t1", project_id="p1", agent_id="a1", cognitive_trace_id="ct1")
        result = router.route_and_retrieve("test")
        assert result["compression_enabled"] is True
        assert result["filter_enabled"] is True
        assert result["optimizer_enabled"] is True

    def test_router_without_optimizer_still_works(self):
        tmp = tempfile.mkdtemp(prefix="r2d_noopt_")
        h = MemoryHierarchy(base_dir=tmp)
        h.store("episodic", "k1", {"data": "test"}, "t1", "p1", "a1", "ct1")
        router = MemoryRouter(hierarchy=h, tenant_id="t1", project_id="p1", agent_id="a1", cognitive_trace_id="ct1")
        result = router.route_and_retrieve("test")
        assert result["compression_enabled"] is False
        assert result["optimizer_enabled"] is False
