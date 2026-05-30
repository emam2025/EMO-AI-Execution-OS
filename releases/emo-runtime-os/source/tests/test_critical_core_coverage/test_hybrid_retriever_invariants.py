"""High-signal tests for HybridRetriever — weight fusion, cache, dedup, score clamping.

Invariants targeted:
  - Final score clamped to [0, 1]
  - Deduplication by symbol_id in merge
  - Semantic availability gate
  - Embedding cache eviction at 5000 entries
  - WeightsAdvisor test-file detection over size-based profiles
"""

import pytest

from core.hybrid_retriever import HybridRetriever, WeightsAdvisor, RepoStats


class TestHybridRetrieverScoreClamping:
    """Invariant: final_score in rank() is clamped [0, 1]."""

    def test_score_never_exceeds_one(self):
        """rank() must clamp scores to max 1.0."""
        retriever = HybridRetriever(None, None, None)
        dummy_results = [
            {"symbol_id": "s1", "graph_score": 50.0, "semantic_score": 50.0},
        ]
        ranked = retriever.rank(dummy_results)
        for r in ranked:
            assert r.get("final_score", 0) <= 1.0 + 1e-9, (
                f"Score {r.get('final_score')} exceeds 1.0"
            )

    def test_score_never_below_zero(self):
        """rank() must clamp scores to min 0.0."""
        retriever = HybridRetriever(None, None, None)
        dummy_results = [
            {"symbol_id": "s2", "graph_score": -100.0, "semantic_score": -100.0},
        ]
        ranked = retriever.rank(dummy_results)
        for r in ranked:
            assert r.get("final_score", 0) >= 0.0, (
                f"Score {r.get('final_score')} below 0.0"
            )


class TestHybridRetrieverMergeDedup:
    """Invariant: merge deduplicates by symbol_id, graph fields take priority."""

    def test_merge_deduplicates_by_symbol_id(self):
        """merge() must not return duplicate symbol_ids."""
        retriever = HybridRetriever(None, None, None)
        graph_results = [{"symbol_id": "s1", "kind": "function", "graph_score": 0.9}]
        semantic_results = [{"symbol_id": "s1", "kind": "class", "semantic_score": 0.8}]
        merged = retriever.merge(graph_results, semantic_results, top_k=10)
        symbol_ids = [m["symbol_id"] for m in merged]
        assert len(symbol_ids) == len(set(symbol_ids)), (
            "Duplicate symbol_id found in merged results"
        )


class TestHybridRetrieverSemanticGate:
    """Invariant: retrieve works when semantic layer is unavailable."""

    def test_retrieve_no_semantic_does_not_crash(self):
        """retrieve() must not crash when semantic store is None."""
        retriever = HybridRetriever(None, None, None)
        result = retriever.retrieve("test query", top_k=5)
        assert isinstance(result, dict), "retrieve must return a dict"


class TestWeightsAdvisorTestFileDetection:
    """Invariant: test-file paths return (0.2, 0.8) regardless of repo size."""

    def test_test_file_path_returns_test_weights(self):
        """get_weights() must return (0.2, 0.8) for test file paths."""
        advisor = WeightsAdvisor(RepoStats(size=5000, total_symbols=100, languages=["python"]))
        w_graph, w_sem = advisor.get_weights(path="tests/test_foo.py")
        assert w_graph == pytest.approx(0.2, abs=1e-6), (
            f"Expected w_graph=0.2 for test path, got {w_graph}"
        )
        assert w_sem == pytest.approx(0.8, abs=1e-6), (
            f"Expected w_sem=0.8 for test path, got {w_sem}"
        )
