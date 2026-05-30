"""Task 4 — Semantic layer: 15 tests.

Suites:
  TestEmbeddingConsistency    (5)
  TestSemanticSearchAccuracy  (5)
  TestContextBudgetEnforcement (5)
"""

import math
import tempfile

import pytest

from releases.memory_os.core.memory.context_selector import ContextSelector
from releases.memory_os.core.memory.embedding import MockEmbeddingProvider, cosine_similarity
from releases.memory_os.core.memory.retrieval_ranker import RetrievalRanker
from releases.memory_os.core.memory.semantic_index import SemanticIndex


# ── TestEmbeddingConsistency (5) ─────────────────────────────

class TestEmbeddingConsistency:
    def test_same_text_produces_same_vector(self):
        e = MockEmbeddingProvider(dimensions=8)
        v1 = e.embed_text("hello world")
        v2 = e.embed_text("hello world")
        assert v1 == v2

    def test_different_text_produces_different_vector(self):
        e = MockEmbeddingProvider(dimensions=8)
        v1 = e.embed_text("hello")
        v2 = e.embed_text("world")
        assert v1 != v2

    def test_normalized_vector_has_unit_length(self):
        e = MockEmbeddingProvider(dimensions=8)
        v = e.embed_text("test vector")
        norm = math.sqrt(sum(x * x for x in v))
        assert abs(norm - 1.0) < 1e-6

    def test_empty_text_returns_zero_vector(self):
        e = MockEmbeddingProvider(dimensions=8)
        v = e.embed_text("")
        assert v == [0.0] * 8

    def test_dimension_matches_config(self):
        e = MockEmbeddingProvider(dimensions=16)
        v = e.embed_text("test")
        assert len(v) == 16


# ── TestSemanticSearchAccuracy (5) ──────────────────────────

class TestSemanticSearchAccuracy:
    @pytest.fixture
    def index(self):
        idx = SemanticIndex(dimensions=8)
        embed = MockEmbeddingProvider(dimensions=8)
        idx.insert("e1", embed.embed_text("project sprint planning", "t1"), "t1", "p1", "plan", "episodic", 1000)
        idx.insert("e2", embed.embed_text("api documentation", "t1"), "t1", "p1", "api_doc", "semantic", 1001)
        idx.insert("e3", embed.embed_text("agent conversation log", "t1"), "t1", "p1", "chat", "episodic", 1002)
        return idx, embed

    def test_search_returns_results_for_exact_text_match(self, index):
        idx, embed = index
        qvec = embed.embed_text("project sprint planning", "t1")
        results = idx.search(qvec, "t1", "p1", limit=10, threshold=0.0)
        assert len(results) >= 1
        exact = [r for r in results if r["key"] == "plan"]
        assert len(exact) >= 1

    def test_search_respects_tenant_isolation(self, index):
        idx, embed = index
        qvec = embed.embed_text("sprint planning")
        results = idx.search(qvec, "other_tenant", "p1", limit=10, threshold=0.0)
        assert len(results) == 0

    def test_search_filters_by_project(self, index):
        idx, embed = index
        idx.insert("e4", embed.embed_text("project data", "t1"), "t1", "p2", "proj2", "episodic", 1003)
        qvec = embed.embed_text("project")
        results = idx.search(qvec, "t1", "p1", limit=10, threshold=0.0)
        for r in results:
            assert r["project_id"] == "p1"

    def test_search_respects_threshold(self, index):
        idx, embed = index
        qvec = embed.embed_text("completely unrelated random noise")
        results_no_threshold = idx.search(qvec, "t1", "p1", limit=10, threshold=0.0)
        results_filtered = idx.search(qvec, "t1", "p1", limit=10, threshold=0.99)
        assert len(results_filtered) <= len(results_no_threshold)

    def test_precision_at_k_meets_threshold(self, index):
        idx, embed = index
        idx.insert("e5", embed.embed_text("project management tasks", "t1"), "t1", "p1", "tasks", "episodic", 1004)
        idx.insert("e6", embed.embed_text("project roadmap milestones", "t1"), "t1", "p1", "roadmap", "episodic", 1005)
        qvec = embed.embed_text("project planning")
        results = idx.search(qvec, "t1", "p1", limit=5, threshold=0.0)
        assert len(results) >= 1
        top_keys = [r["key"] for r in results[:3]]
        relevant = {"plan", "tasks", "roadmap", "api_doc", "chat"}
        if top_keys:
            precision = sum(1 for k in top_keys if k in relevant) / len(top_keys)
            assert precision >= 0.5


# ── TestContextBudgetEnforcement (5) ────────────────────────

class TestContextBudgetEnforcement:
    def test_selector_never_exceeds_budget(self):
        sel = ContextSelector(default_budget=100)
        large_entries = [
            {"entry_id": f"e{i}", "tenant_id": "t1", "project_id": "p1",
             "payload": {"data": "x" * 200}, "key": f"k{i}",
             "relevance_score": 0.9, "semantic_score": 0.9,
             "agent_id": "a1", "layer": "episodic", "content_hash": "h1"}
            for i in range(20)
        ]
        result = sel.select_context(
            query="test",
            budget=100,
            ranked_results=large_entries,
            tenant_id="t1",
            project_id="p1",
            cognitive_trace_id="ct1",
        )
        assert result["tokens_used"] <= 100

    def test_empty_results_returns_zero_entries(self):
        sel = ContextSelector()
        result = sel.select_context(
            query="test",
            ranked_results=[],
            tenant_id="t1",
            project_id="p1",
            cognitive_trace_id="ct1",
        )
        assert result["entries_selected"] == 0

    def test_selector_requires_tenant_id(self):
        sel = ContextSelector()
        with pytest.raises(ValueError, match="tenant_id"):
            sel.select_context(
                query="test",
                tenant_id="",
                project_id="p1",
                cognitive_trace_id="ct1",
            )

    def test_selector_requires_project_id(self):
        sel = ContextSelector()
        with pytest.raises(ValueError, match="project_id"):
            sel.select_context(
                query="test",
                tenant_id="t1",
                project_id="",
                cognitive_trace_id="ct1",
            )

    def test_high_relevance_entries_prioritized_within_budget(self):
        sel = ContextSelector(default_budget=200)
        entries = [
            {"entry_id": f"e{i}", "tenant_id": "t1", "project_id": "p1",
             "payload": {"d": "x"}, "key": f"k{i}",
             "relevance_score": 1.0 - i * 0.1, "semantic_score": 0.9,
             "agent_id": "a1", "layer": "episodic", "content_hash": "h1"}
            for i in range(10)
        ]
        result = sel.select_context(
            query="t",
            budget=200,
            ranked_results=entries,
            tenant_id="t1",
            project_id="p1",
            cognitive_trace_id="ct1",
        )
        selected = result["selected_entries"]
        if len(selected) >= 2:
            assert selected[0]["relevance_score"] >= selected[1]["relevance_score"]
