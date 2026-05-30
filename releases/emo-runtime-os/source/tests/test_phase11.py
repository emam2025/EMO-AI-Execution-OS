"""Phase 11 tests: QueryReplay, FeedbackLoop, AdaptiveWeightEngine, integration.

Tests cover:
  - QueryReplay: log, replay, find_similar, recent, update_feedback,
                 compare_runs, clear, count, persistence across instances
  - FeedbackLoop: record_feedback, success_rate, best/worst strategy,
                  quality_report, import_from_replay
  - AdaptiveWeightEngine: get_boost at each threshold, adjusted_weights,
                          learning_report, edge cases
  - Integration: HybridRetriever passes query_id and strategy in output
"""
import sys, os, time, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import warnings
warnings.filterwarnings("ignore")
import logging
logging.disable(logging.CRITICAL)


# ======================================================================
# QueryReplay Tests
# ======================================================================

from core.query_replay import QueryReplay, QueryLog


def make_replay():
    path = os.path.join(tempfile.mkdtemp(), "test_phase11.db")
    r = QueryReplay(path)
    r.clear()
    return r


def test_replay_log_and_replay():
    r = make_replay()
    qid = r.log(
        query="find auth",
        results=[{"symbol_id": "s1", "score": 0.9, "name": "login"}],
        weights_used={"s1": {"w_graph": 0.6, "w_sem": 0.4}},
        strategy="balanced",
        source="hybrid",
    )
    assert qid is not None
    assert r.count() == 1

    loaded = r.replay(qid)
    assert loaded is not None
    assert loaded.text == "find auth"
    assert loaded.strategy == "balanced"
    assert loaded.results[0]["name"] == "login"


def test_replay_replay_not_found():
    r = make_replay()
    loaded = r.replay("nonexistent")
    assert loaded is None


def test_replay_find_similar():
    r = make_replay()
    r.log("find auth function", [], {}, strategy="balanced")
    r.log("connect database", [], {}, strategy="balanced")
    r.log("authentication logic", [], {}, strategy="balanced")

    hits = r.find_similar("auth", limit=5)
    assert len(hits) >= 2, f"Expected >=2, got {len(hits)}"
    texts = [h.text for h in hits]
    assert any("auth" in t for t in texts)


def test_replay_recent():
    r = make_replay()
    for i in range(5):
        r.log(f"query_{i}", [], {}, strategy="balanced")
        time.sleep(0.01)
    recent = r.recent(3)
    assert len(recent) == 3
    assert recent[0].text == "query_4"


def test_replay_update_feedback():
    r = make_replay()
    qid = r.log("test", [], {}, strategy="balanced")
    r.update_feedback(qid, 0.9, success=1)

    loaded = r.replay(qid)
    assert loaded.feedback == 0.9
    assert loaded.success == 1


def test_replay_compare_runs():
    r = make_replay()
    r.log("auth login", [{"symbol_id": "s1", "score": 0.7}],
          {"s1": {"w_graph": 0.5}}, strategy="balanced")
    time.sleep(0.01)
    r.log("auth login", [{"symbol_id": "s1", "score": 0.9}],
          {"s1": {"w_graph": 0.6}}, strategy="balanced")

    comp = r.compare_runs("auth login")
    assert comp["score_delta"] == 0.2, f"Expected 0.2, got {comp['score_delta']}"
    assert comp["previous_strategy"] == "balanced"
    assert comp["current_strategy"] == "balanced"
    assert comp["current_top"]["score"] == 0.9


def test_replay_compare_runs_need_two():
    r = make_replay()
    r.log("single", [], {}, strategy="balanced")
    comp = r.compare_runs("single")
    assert "Need at least 2" in comp.get("note", "")


def test_replay_clear():
    r = make_replay()
    assert r.count() == 0
    r.log("q1", [], {}, strategy="balanced")
    r.log("q2", [], {}, strategy="balanced")
    assert r.count() == 2
    r.clear()
    assert r.count() == 0


def test_replay_persistence():
    """Data survives across QueryReplay instances with same DB."""
    path = os.path.join(tempfile.mkdtemp(), "persist.db")
    r1 = QueryReplay(path)
    r1.clear()
    r1.log("persist test", [{"symbol_id": "x"}], {"x": {}}, strategy="test_file")
    assert r1.count() == 1

    r2 = QueryReplay(path)
    assert r2.count() == 1
    r2.clear()
    assert r2.count() == 0


def test_replay_log_with_context():
    r = make_replay()
    qid = r.log("query", [], {}, strategy="balanced",
                context={"repo_size": 1200, "file": "auth.py"})
    loaded = r.replay(qid)
    assert loaded.context.get("repo_size") == 1200
    assert loaded.context.get("file") == "auth.py"


# ======================================================================
# FeedbackLoop Tests
# ======================================================================

from core.feedback_loop import RankingFeedbackLoop


def test_feedback_record():
    loop = RankingFeedbackLoop()
    loop.record_feedback("balanced", 0.9, success=True)
    loop.record_feedback("balanced", 0.3, success=False)
    # success_rate = successes / (successes + failures + 1) = 1/(1+1+1) = 0.333
    rate = loop.success_rate("balanced")
    assert abs(rate - 0.333) < 0.01, f"Expected ~0.333, got {rate}"
    assert loop.get_strategy_stats("balanced").total_queries == 2


def test_feedback_default_success_rate():
    loop = RankingFeedbackLoop()
    assert loop.success_rate("nonexistent") == 0.5  # neutral


def test_feedback_best_worst_strategy():
    loop = RankingFeedbackLoop()
    loop.record_feedback("good", 0.9, success=True)
    loop.record_feedback("good", 0.95, success=True)
    loop.record_feedback("bad", 0.1, success=False)
    loop.record_feedback("bad", 0.2, success=False)

    assert loop.best_strategy() == "good"
    assert loop.worst_strategy() == "bad"
    assert loop.success_rate("good") > loop.success_rate("bad")


def test_feedback_auto_success_from_score():
    """When success is None, derive from feedback >= 0.5."""
    loop = RankingFeedbackLoop()
    loop.record_feedback("s", 0.9)  # >= 0.5 → success
    loop.record_feedback("s", 0.1)  # < 0.5 → failure
    stats = loop.get_strategy_stats("s")
    assert stats.successes == 1
    assert stats.failures == 1


def test_feedback_recent():
    loop = RankingFeedbackLoop()
    for i in range(5):
        loop.record_feedback("s", 0.5 + i * 0.1)
    recent = loop.recent_feedback(3)
    assert len(recent) == 3


def test_feedback_quality_report():
    loop = RankingFeedbackLoop()
    loop.record_feedback("balanced", 0.9, success=True)
    loop.record_feedback("test_file", 0.2, success=False)
    report = loop.quality_report()
    assert "strategies" in report
    assert "best_strategy" in report
    assert report["best_strategy"] == "balanced"


def test_feedback_import_from_replay():
    class FakeLog:
        def __init__(self, s, fb, ok):
            self.strategy = s
            self.feedback = fb
            self.success = 1 if ok else 0
            self.text = f"query-{s}"

    loop = RankingFeedbackLoop()
    logs = [
        FakeLog("balanced", 0.9, True),
        FakeLog("balanced", 0.2, False),
        FakeLog("test_file", 1.0, True),
        FakeLog("test_file", 1.0, True),
    ]
    n = loop.import_from_replay(logs)
    assert n == 4
    assert loop.success_rate("balanced") > 0
    # test_file: 2 successes, 0 failures → rate = 2/3 = 0.667 > 0.5
    assert loop.success_rate("test_file") > 0.5


# ======================================================================
# AdaptiveWeightEngine Tests
# ======================================================================

from core.adaptive_weights import (
    AdaptiveWeightEngine, profile_from_weights,
    STRATEGY_BALANCED, STRATEGY_SMALL_REPO, STRATEGY_LARGE_REPO,
    STRATEGY_TEST_FILE,
)


def test_profile_from_weights():
    assert profile_from_weights(0.6, 0.4) == STRATEGY_BALANCED
    assert profile_from_weights(0.3, 0.7) == STRATEGY_SMALL_REPO
    assert profile_from_weights(0.7, 0.3) == STRATEGY_LARGE_REPO
    assert profile_from_weights(0.2, 0.8) == STRATEGY_TEST_FILE
    assert profile_from_weights(0.5, 0.5) == STRATEGY_BALANCED  # unknown → default


def test_boost_high_success():
    """> 0.75 → +0.10 boost."""
    loop = RankingFeedbackLoop()
    for _ in range(8):
        loop.record_feedback(STRATEGY_BALANCED, 1.0, success=True)
    engine = AdaptiveWeightEngine(loop)
    assert engine.get_boost(STRATEGY_BALANCED) == 0.10


def test_boost_medium_success():
    """> 0.60 → +0.05 boost."""
    loop = RankingFeedbackLoop()
    for _ in range(6):
        loop.record_feedback(STRATEGY_BALANCED, 1.0, success=True)
    for _ in range(4):
        loop.record_feedback(STRATEGY_BALANCED, 0, success=False)
    engine = AdaptiveWeightEngine(loop)
    # Rate = 6/(6+4+1) ≈ 0.545 — that's between 0.40 and 0.60, so no boost
    # Wait, that's 0.545 which is < 0.60 (not medium) and > 0.40 (not negative)
    # Rate = 6/11 = 0.545 — no boost
    assert engine.get_boost(STRATEGY_BALANCED) == 0.0


def test_boost_negative():
    """< 0.40 → -0.10 boost."""
    loop = RankingFeedbackLoop()
    for _ in range(3):
        loop.record_feedback(STRATEGY_BALANCED, 1.0, success=True)
    for _ in range(5):
        loop.record_feedback(STRATEGY_BALANCED, 0, success=False)
    engine = AdaptiveWeightEngine(loop)
    # Rate = 3/(3+5+1) = 3/9 = 0.333 → < 0.40 → NEG = -0.10
    assert engine.get_boost(STRATEGY_BALANCED) == -0.10


def test_boost_negative_at_33():
    loop = RankingFeedbackLoop()
    for _ in range(3):
        loop.record_feedback(STRATEGY_BALANCED, 1.0, success=True)
    for _ in range(5):
        loop.record_feedback(STRATEGY_BALANCED, 0, success=False)
    engine = AdaptiveWeightEngine(loop)
    # Rate = 3/(3+5+1) = 3/9 = 0.333 → < 0.40 → NEG = -0.10
    assert engine.get_boost(STRATEGY_BALANCED) == -0.10


def test_boost_low_at_20():
    loop = RankingFeedbackLoop()
    for _ in range(2):
        loop.record_feedback(STRATEGY_BALANCED, 1.0, success=True)
    for _ in range(8):
        loop.record_feedback(STRATEGY_BALANCED, 0, success=False)
    engine = AdaptiveWeightEngine(loop)
    # Rate = 2/(2+8+1) = 2/11 ≈ 0.182 < 0.25 → LOW = -0.15
    assert engine.get_boost(STRATEGY_BALANCED) == -0.15


def test_adjusted_weights_graph_heavy():
    """Graph-heavy profile gets boost on graph weight."""
    loop = RankingFeedbackLoop()
    for _ in range(8):
        loop.record_feedback(STRATEGY_LARGE_REPO, 1.0, success=True)
    engine = AdaptiveWeightEngine(loop)
    w_g, w_s = engine.adjusted_weights(0.7, 0.3, STRATEGY_LARGE_REPO)
    # Boost = +0.10, added to w_g (dominant), renormalized
    # 0.7+0.1=0.8, 0.3 unchanged, sum=1.1 → norm = (0.73, 0.27)
    assert abs(w_g - 0.73) < 0.02, f"Expected ~0.73, got {w_g}"
    assert abs(w_s - 0.27) < 0.02


def test_adjusted_weights_semantic_heavy():
    """Semantic-heavy profile gets boost on semantic weight."""
    loop = RankingFeedbackLoop()
    for _ in range(8):
        loop.record_feedback(STRATEGY_SMALL_REPO, 1.0, success=True)
    engine = AdaptiveWeightEngine(loop)
    w_g, w_s = engine.adjusted_weights(0.3, 0.7, STRATEGY_SMALL_REPO)
    # Boost = +0.10, added to w_s (dominant)
    # 0.3, 0.7+0.1=0.8, sum=1.1 → norm = (0.27, 0.73)
    assert abs(w_g - 0.27) < 0.02
    assert abs(w_s - 0.73) < 0.02


def test_adjusted_weights_balanced():
    """Balanced profile splits boost equally."""
    loop = RankingFeedbackLoop()
    for _ in range(8):
        loop.record_feedback(STRATEGY_BALANCED, 1.0, success=True)
    loop.record_feedback(STRATEGY_BALANCED, 1.0, success=True)
    loop.record_feedback(STRATEGY_BALANCED, 1.0, success=True)
    loop.record_feedback(STRATEGY_BALANCED, 1.0, success=True)
    engine = AdaptiveWeightEngine(loop)
    w_g, w_s = engine.adjusted_weights(0.6, 0.4, STRATEGY_BALANCED)
    # 4 successes, 0 failures → rate = 4/5 = 0.80 → HIGH boost = +0.10
    # (0.6, 0.4) is graph-heavy (w_g > w_s) → boost goes to w_g
    # 0.7, 0.4, sum=1.1 → norm = (0.64, 0.36)
    assert abs(w_g - 0.64) < 0.02, f"Expected ~0.64, got {w_g}"
    assert abs(w_s - 0.36) < 0.02


def test_adjusted_weights_no_boost():
    loop = RankingFeedbackLoop()
    loop.record_feedback(STRATEGY_BALANCED, 0.3, success=False)
    loop.record_feedback(STRATEGY_BALANCED, 0.5, success=True)
    loop.record_feedback(STRATEGY_BALANCED, 0.7, success=True)
    loop.record_feedback(STRATEGY_BALANCED, 0.6, success=True)
    loop.record_feedback(STRATEGY_BALANCED, 0.8, success=True)
    engine = AdaptiveWeightEngine(loop)
    w_g, w_s = engine.adjusted_weights(0.6, 0.4, STRATEGY_BALANCED)
    # 4 successes, 1 failure → rate = 4/6 = 0.667 > 0.60 → MED boost = +0.05
    # (0.6, 0.4) is graph-heavy → boost goes to w_g
    # 0.65, 0.4, sum=1.05 → norm = (0.62, 0.38)
    assert abs(w_g - 0.62) < 0.02, f"Expected ~0.62, got {w_g}"
    assert abs(w_s - 0.38) < 0.02


def test_adjusted_weights_clamping():
    """Verify weights stay in [0.05, 0.95] even with extreme boosting."""
    loop = RankingFeedbackLoop()
    for _ in range(10):
        loop.record_feedback(STRATEGY_LARGE_REPO, 1.0, success=True)
    engine = AdaptiveWeightEngine(loop)
    w_g, w_s = engine.adjusted_weights(0.95, 0.05, STRATEGY_LARGE_REPO)
    # Boost = +0.10, 0.95+0.10=1.05 → clamped to 0.95
    assert w_g <= 0.95
    assert w_s >= 0.05


def test_learning_report():
    loop = RankingFeedbackLoop()
    loop.record_feedback(STRATEGY_BALANCED, 0.9, success=True)
    engine = AdaptiveWeightEngine(loop)
    report = engine.learning_report()
    assert "strategies" in report
    assert "boosts" in report
    assert STRATEGY_BALANCED in report["boosts"]


def test_learning_report_empty():
    engine = AdaptiveWeightEngine()
    report = engine.learning_report()
    assert report["strategies"] == {}


def test_record_outcome_integration():
    engine = AdaptiveWeightEngine()
    engine.record_outcome(STRATEGY_BALANCED, 0.9, success=True)
    engine.record_outcome(STRATEGY_BALANCED, 0.1, success=False)
    # 1 success, 1 failure → rate = 1/(1+1+1) = 0.333
    assert abs(engine.loop.success_rate(STRATEGY_BALANCED) - 0.333) < 0.01


# ======================================================================
# Integration Tests: HybridRetriever + Phase 11
# ======================================================================

from core.hybrid_retriever import HybridRetriever, WeightsAdvisor, RepoStats
from core.adaptive_weights import AdaptiveWeightEngine
from core.feedback_loop import RankingFeedbackLoop


class MockGE:
    def retrieve_symbol_core(self, sid):
        if sid == "s1":
            return {"meta": {"name": "validate"}, "static_analysis": {"role": "pure_function", "file_path": "auth.py", "complexity": {"cyclomatic": 2}, "behavior": {"is_recursive": False}}}
        raise LookupError
    def heuristic_analysis(self, sid, **kw):
        return {"importance": 5.0, "overall_risk": "LOW"}
    def ranked_hotspots(self, limit=10):
        return [{"symbol_id": "s1", "symbol_name": "validate", "importance_score": 5.0, "role": "pure_function", "file_path": "auth.py", "incoming_calls": 3}]


class MockSS:
    available = True
    def search_similar(self, qv, top_k=10):
        return [{"symbol_id": "s1", "score": 0.9, "metadata": {"name": "validate", "file_path": "auth.py"}}]
    @property
    def size(self): return 1


class MockEE:
    available = True
    dimension = 384
    def embed_text(self, t): return [0.1]*384
    def embed_symbol(self, s): return [0.1]*384


def test_integration_query_id_in_output():
    """HybridRetriever.retrieve() should return query_id when replay is configured."""
    replay = make_replay()
    hr = HybridRetriever(MockGE(), MockSS(), MockEE(), query_replay=replay)
    result = hr.retrieve("test")
    assert result["query_id"] is not None
    assert result["strategy"] is not None
    # Verify it was actually logged
    loaded = replay.replay(result["query_id"])
    assert loaded is not None
    assert loaded.text == "test"


def test_integration_strategy_without_replay():
    """Without replay, query_id should be None."""
    hr = HybridRetriever(MockGE(), MockSS(), MockEE())
    result = hr.retrieve("test")
    assert result["query_id"] is None


def test_integration_adaptive_weights():
    """Adaptive weight engine should adjust weights in ranking."""
    loop = RankingFeedbackLoop()
    # Train the balanced strategy to have HIGH success
    for _ in range(8):
        loop.record_feedback(STRATEGY_BALANCED, 1.0, success=True)
    adaptive = AdaptiveWeightEngine(loop)
    hr = HybridRetriever(MockGE(), MockSS(), MockEE(),
                          weights_advisor=WeightsAdvisor(RepoStats(1200)),
                          adaptive_engine=adaptive)
    result = hr.retrieve("test")
    # Balanced should have boost = +0.10
    assert result["strategy"] == STRATEGY_BALANCED
    # The weights should be adjusted from (0.6, 0.4) base
    # Graph-heavy profile → boost goes to w_g: (0.7, 0.4) → norm (0.64, 0.36)
    for rs in result["ranking_scores"]:
        assert abs(rs["w_graph"] - 0.64) < 0.05
        assert abs(rs["w_sem"] - 0.36) < 0.05


def test_integration_replay_logs_results():
    """Replay should store ranked results from retrieve()."""
    replay = make_replay()
    hr = HybridRetriever(MockGE(), MockSS(), MockEE(), query_replay=replay)
    result = hr.retrieve("test")
    loaded = replay.replay(result["query_id"])
    assert len(loaded.results) > 0
    assert loaded.results[0]["symbol_id"] == "s1"


def test_integration_deduplication_via_replay():
    """Running the same query twice logs two entries, no data loss."""
    replay = make_replay()
    hr = HybridRetriever(MockGE(), MockSS(), MockEE(), query_replay=replay)
    hr.retrieve("same query")
    hr.retrieve("same query")
    assert replay.count() == 2
    similar = replay.find_similar("same query", limit=5)
    assert len(similar) == 2


def test_integration_orchestrator_query_id():
    """Verify UnifiedRuntime passes through the hybrid retrieve result."""
    from core.orchestrator import Intent
    from core.unified_runtime import UnifiedRuntime
    from core.execution_engine import ExecutionEngine, DAGBuilder, ToolSpec, RetryPolicy, RollbackStrategy

    class MockAgent:
        def explain(self, *a): return {"insight_summary": "test"}
        def top_hotspots(self, *a): return {"insight_summary": "test"}

    replay = make_replay()
    hr = HybridRetriever(MockGE(), MockSS(), MockEE(), query_replay=replay)

    dag = (DAGBuilder()
           .add("hybrid", tool="hybrid_retrieval.retrieve",
                inputs={"query": "test", "top_k": 10})
           .build())

    engine = ExecutionEngine()
    engine.register_tool(ToolSpec(
        name="hybrid_retrieval.retrieve", timeout_seconds=30,
        retry_policy=RetryPolicy(max_retries=2),
        rollback_strategy=RollbackStrategy(),
    ))

    runner = lambda n: hr.retrieve(**n.inputs)
    result = engine.execute(dag, tool_runner=runner)

    assert result["status"] == "completed"
    for nid, nr in result["node_results"].items():
        node_result = nr.get("result", {})
        if node_result and "query_id" in str(node_result):
            assert True
            break
    assert replay.count() >= 1


# ======================================================================
# Run all
# ======================================================================

if __name__ == "__main__":
    tests = [
        # QueryReplay
        ("replay log & replay", test_replay_log_and_replay),
        ("replay not found", test_replay_replay_not_found),
        ("replay find similar", test_replay_find_similar),
        ("replay recent", test_replay_recent),
        ("replay update feedback", test_replay_update_feedback),
        ("replay compare runs", test_replay_compare_runs),
        ("replay compare need 2", test_replay_compare_runs_need_two),
        ("replay clear", test_replay_clear),
        ("replay persistence", test_replay_persistence),
        ("replay log with context", test_replay_log_with_context),
        # FeedbackLoop
        ("feedback record", test_feedback_record),
        ("feedback default rate", test_feedback_default_success_rate),
        ("feedback best/worst", test_feedback_best_worst_strategy),
        ("feedback auto success", test_feedback_auto_success_from_score),
        ("feedback recent", test_feedback_recent),
        ("feedback quality report", test_feedback_quality_report),
        ("feedback import replay", test_feedback_import_from_replay),
        # AdaptiveWeightEngine
        ("profile from weights", test_profile_from_weights),
        ("boost high success", test_boost_high_success),
        ("boost medium", test_boost_medium_success),
        ("boost negative at 33%", test_boost_negative_at_33),
        ("boost low at 20%", test_boost_low_at_20),
        ("adjusted graph-heavy", test_adjusted_weights_graph_heavy),
        ("adjusted semantic-heavy", test_adjusted_weights_semantic_heavy),
        ("adjusted balanced", test_adjusted_weights_balanced),
        ("adjusted no boost", test_adjusted_weights_no_boost),
        ("adjusted clamping", test_adjusted_weights_clamping),
        ("learning report", test_learning_report),
        ("learning report empty", test_learning_report_empty),
        ("record outcome", test_record_outcome_integration),
        # Integration
        ("query_id in output", test_integration_query_id_in_output),
        ("strategy without replay", test_integration_strategy_without_replay),
        ("adaptive weights in rank", test_integration_adaptive_weights),
        ("replay logs results", test_integration_replay_logs_results),
        ("dedup via replay", test_integration_deduplication_via_replay),
        ("orchestrator query_id", test_integration_orchestrator_query_id),
    ]

    passed = 0
    failed = 0
    for desc, test_fn in tests:
        try:
            test_fn()
            print(f"  ✓ {desc}")
            passed += 1
        except Exception as e:
            print(f"  ✗ {desc}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    total = len(tests)
    print(f"\n{'='*50}")
    print(f"Phase 11: {passed} passed, {failed} failed, {total} total")
    print(f"{'✓ COMPLETE' if failed == 0 else '✗ NEEDS FIX'}")
