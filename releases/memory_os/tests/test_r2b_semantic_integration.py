"""Task 3 — R2-B integration with R2-A: 10 tests.

Verifies embedding pipeline, semantic index, ranker, and context selector
work together without breaking R2-A isolation contracts.
"""

import tempfile
import pytest

from releases.memory_os.core.memory.context_selector import ContextSelector
from releases.memory_os.core.memory.embedding import MockEmbeddingProvider
from releases.memory_os.core.memory.hierarchy import MemoryHierarchy
from releases.memory_os.core.memory.memory_router import MemoryRouter
from releases.memory_os.core.memory.retrieval_ranker import RetrievalRanker
from releases.memory_os.core.memory.semantic_index import SemanticIndex
from releases.memory_os.core.models.memory import MemoryScope


@pytest.fixture
def semantic_hierarchy():
    tmp = tempfile.mkdtemp(prefix="r2b_int_")
    index = SemanticIndex(dimensions=8)
    embed = MockEmbeddingProvider(dimensions=8)
    h = MemoryHierarchy(base_dir=tmp, semantic_index=index, embedding_provider=embed)
    h.store("episodic", "plan_sprint", {"plan": "sprint goals"}, "t1", "p1", "a1", "ct1", text="project sprint planning goals")
    h.store("semantic", "api_doc", {"endpoint": "/users"}, "t1", "p1", "a1", "ct1", text="api documentation for users endpoint")
    h.store("episodic", "chat_log", {"msg": "hello"}, "t1", "p1", "a1", "ct1", text="agent conversation log")
    yield h


@pytest.fixture
def semantic_router(semantic_hierarchy):
    ranker = RetrievalRanker(min_relevance_threshold=0.01)
    selector = ContextSelector(default_budget=4096)
    return MemoryRouter(
        hierarchy=semantic_hierarchy,
        tenant_id="t1",
        project_id="p1",
        agent_id="a1",
        cognitive_trace_id="ct1",
        ranker=ranker,
        context_selector=selector,
    )


class TestEmbeddingIndexIntegration:
    def test_store_indexes_embedding(self, semantic_hierarchy):
        assert semantic_hierarchy.semantic_index is not None
        assert semantic_hierarchy.semantic_index.count("t1") == 3

    def test_store_without_text_skips_indexing(self, semantic_hierarchy):
        h = semantic_hierarchy
        h.store("episodic", "no_text", {"x": 1}, "t1", "p1", "a1", "ct1", text="")
        assert h.semantic_index.count("t1") == 3

    def test_retrieve_with_semantic_query_adds_scores(self, semantic_hierarchy):
        results = semantic_hierarchy.retrieve(
            "episodic", {"scope": "project", "text": "sprint planning"},
            "t1", "p1", "ct1", limit=10,
        )
        for r in results:
            assert "semantic_score" in r

    def test_semantic_search_returns_scores_for_all_results(self, semantic_hierarchy):
        results = semantic_hierarchy.retrieve(
            "episodic", {"scope": "project", "text": "sprint planning goals"},
            "t1", "p1", "ct1", limit=10,
        )
        for r in results:
            assert isinstance(r.get("semantic_score"), float)


class TestRankerSelectorIntegration:
    def test_ranker_accepts_semantic_scores(self, semantic_hierarchy):
        results = semantic_hierarchy.retrieve(
            "episodic", {"scope": "project", "text": "planning"},
            "t1", "p1", "ct1", limit=10,
        )
        ranker = RetrievalRanker(min_relevance_threshold=0.0)
        ranked = ranker.rank_results(results, {"scope": "project"})
        assert len(ranked) > 0
        for r in ranked:
            assert "relevance_score" in r

    def test_selector_respects_budget(self, semantic_hierarchy):
        selector = ContextSelector(default_budget=100)
        ranked = [
            {"entry_id": "e1", "tenant_id": "t1", "project_id": "p1",
             "payload": {"data": "x" * 500}, "key": "k1", "relevance_score": 0.9, "semantic_score": 0.9,
             "agent_id": "a1", "layer": "episodic", "content_hash": "h1"},
        ]
        result = selector.select_context(
            query="test",
            budget=100,
            ranked_results=ranked,
            tenant_id="t1",
            project_id="p1",
            cognitive_trace_id="ct1",
        )
        assert result["tokens_used"] <= 100

    def test_router_pipeline_returns_semantic_context(self, semantic_router):
        result = semantic_router.route_and_retrieve("project planning sprint", limit=5)
        assert "entries" in result
        assert "tokens_used" in result
        assert "entries_selected_in_context" in result

    def test_router_pipeline_does_not_break_without_semantic(self):
        tmp = tempfile.mkdtemp(prefix="r2b_no_sem_")
        h = MemoryHierarchy(base_dir=tmp)
        h.store("episodic", "k1", {"x": 1}, "t1", "p1", "a1", "ct1")
        router = MemoryRouter(hierarchy=h, tenant_id="t1", project_id="p1", agent_id="a1", cognitive_trace_id="ct1")
        result = router.route_and_retrieve("test query")
        assert "entries" in result
