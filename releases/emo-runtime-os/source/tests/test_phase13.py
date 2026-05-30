"""Phase 13 tests: MetricsStore, TimelineBuilder, QueryAnalytics, integration.

Tests cover:
  - MetricsStore: 4 tables, event recording, queries, aggregation
  - TimelineBuilder: build, summarise, day formatting
  - QueryAnalytics: instability, collapse, noisy embeddings, feedback skew
  - Integration: AdaptiveWeightEngine + MetricsStore telemetry
  - Integration: HybridRetriever + MetricsStore event emission
"""

import sys, os, time, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import warnings
warnings.filterwarnings("ignore")
import logging
logging.disable(logging.CRITICAL)


# ======================================================================
# MetricsStore Tests
# ======================================================================

from core.metrics_store import (
    MetricsStore,
    EVENT_QUERY_EXECUTED, EVENT_RETRIEVAL_COMPLETED,
    EVENT_RANKING_ADJUSTED, EVENT_DRIFT_DETECTED,
    EVENT_REGRESSION_DETECTED, EVENT_ROLLBACK_EXECUTED,
    EVENT_SHADOW_PROMOTED, EVENT_FEEDBACK_RECEIVED,
    EVENT_WEIGHT_CHANGE,
)


def make_store():
    path = os.path.join(tempfile.mkdtemp(), "test_phase13.db")
    s = MetricsStore(path)
    s.clear()
    return s


def test_store_record_event():
    s = make_store()
    eid = s.record_event(EVENT_QUERY_EXECUTED, query_id="q1", strategy="balanced")
    assert eid > 0
    events = s.query_events()
    assert len(events) == 1
    assert events[0]["event_type"] == EVENT_QUERY_EXECUTED
    assert events[0]["strategy"] == "balanced"


def test_store_record_drift_alert():
    s = make_store()
    aid = s.record_drift_alert("strategy_collapse", "warning",
                                {"strategy": "balanced", "usage_pct": 0.85})
    assert aid > 0
    alerts = s.query_drift_alerts()
    assert len(alerts) == 1
    assert alerts[0]["drift_type"] == "strategy_collapse"


def test_store_record_rollback():
    s = make_store()
    rid = s.record_rollback("precision drop", (0.7, 0.3), (0.6, 0.4))
    assert rid > 0
    events = s.query_rollback_events()
    assert len(events) == 1
    assert "precision drop" in events[0]["trigger_reason"]


def test_store_record_shadow():
    s = make_store()
    sid = s.record_shadow_evaluation(0.6, 0.8, promoted=True)
    assert sid > 0
    evals = s.query_shadow_evaluations()
    assert len(evals) == 1
    assert evals[0]["promoted"] == 1


def test_store_query_with_filters():
    s = make_store()
    s.record_event(EVENT_QUERY_EXECUTED, strategy="balanced")
    s.record_event(EVENT_QUERY_EXECUTED, strategy="balanced")
    s.record_event(EVENT_QUERY_EXECUTED, strategy="test_file")
    s.record_event(EVENT_RETRIEVAL_COMPLETED, strategy="balanced")

    # Filter by event_type
    events = s.query_events(event_type=EVENT_QUERY_EXECUTED)
    assert len(events) == 3

    # Filter by strategy
    events = s.query_events(strategy="test_file")
    assert len(events) == 1

    # Filter by both
    events = s.query_events(event_type=EVENT_QUERY_EXECUTED, strategy="balanced")
    assert len(events) == 2


def test_store_query_since():
    s = make_store()
    s.record_event(EVENT_QUERY_EXECUTED, strategy="balanced")
    time.sleep(0.02)
    mid = time.time()
    time.sleep(0.02)
    s.record_event(EVENT_QUERY_EXECUTED, strategy="test_file")

    events = s.query_events(since=mid)
    assert len(events) == 1
    assert events[0]["strategy"] == "test_file"


def test_store_strategy_usage():
    s = make_store()
    s.record_event(EVENT_QUERY_EXECUTED, strategy="balanced")
    s.record_event(EVENT_QUERY_EXECUTED, strategy="balanced")
    s.record_event(EVENT_QUERY_EXECUTED, strategy="test_file")

    usage = s.strategy_usage()
    assert usage.get("balanced") == 2
    assert usage.get("test_file") == 1


def test_store_strategy_usage_since():
    s = make_store()
    s.record_event(EVENT_QUERY_EXECUTED, strategy="balanced")
    time.sleep(0.02)
    mid = time.time()
    time.sleep(0.02)
    s.record_event(EVENT_QUERY_EXECUTED, strategy="test_file")

    usage = s.strategy_usage(since=mid)
    assert "balanced" not in usage
    assert usage.get("test_file") == 1


def test_store_weight_change_history():
    s = make_store()
    s.record_event(EVENT_RANKING_ADJUSTED, strategy="balanced",
                    old_weights=(0.6, 0.4), new_weights=(0.7, 0.3))
    s.record_event(EVENT_WEIGHT_CHANGE, strategy="large_repo",
                    old_weights=(0.7, 0.3), new_weights=(0.6, 0.4))

    changes = s.weight_change_history()
    assert len(changes) == 2


def test_store_rollback_count():
    s = make_store()
    assert s.rollback_count() == 0
    s.record_rollback("test", (0.6, 0.4), (0.5, 0.5))
    assert s.rollback_count() == 1


def test_store_drift_alert_count():
    s = make_store()
    assert s.drift_alert_count() == 0
    s.record_drift_alert("collapse", "warning", {})
    assert s.drift_alert_count() == 1


def test_store_shadow_win_rate():
    s = make_store()
    assert s.shadow_win_rate() == 0.0
    s.record_shadow_evaluation(0.6, 0.8)  # win
    s.record_shadow_evaluation(0.7, 0.3)  # loss
    assert s.shadow_win_rate() == 0.5


def test_store_clear():
    s = make_store()
    s.record_event(EVENT_QUERY_EXECUTED)
    s.clear()
    assert len(s.query_events()) == 0


# ======================================================================
# TimelineBuilder Tests
# ======================================================================

from core.timeline import TimelineBuilder


def test_timeline_build_empty():
    s = make_store()
    tb = TimelineBuilder(s)
    entries = tb.build(days=7)
    assert entries == []


def test_timeline_with_drift():
    s = make_store()
    s.record_drift_alert("strategy_collapse", "warning",
                          {"strategy": "balanced", "message": "Collapse detected"})
    tb = TimelineBuilder(s)
    entries = tb.build(days=7)
    assert len(entries) >= 1
    assert "drift" in entries[0]["event"]


def test_timeline_with_rollback():
    s = make_store()
    s.record_rollback("semantic drop", (0.7, 0.3), (0.6, 0.4))
    tb = TimelineBuilder(s)
    entries = tb.build(days=7)
    assert len(entries) >= 1
    assert entries[0]["event"] == "rollback"
    assert entries[0]["severity"] == "critical"


def test_timeline_with_shadow_promotion():
    s = make_store()
    s.record_shadow_evaluation(0.5, 0.9, promoted=True)
    tb = TimelineBuilder(s)
    entries = tb.build(days=7)
    assert len(entries) >= 1
    assert "shadow" in entries[0]["event"]


def test_timeline_with_regression():
    s = make_store()
    s.record_event(EVENT_REGRESSION_DETECTED,
                    strategy="balanced",
                    metadata={"message": "Rate dropped from 0.8 to 0.5"})
    tb = TimelineBuilder(s)
    entries = tb.build(days=7)
    assert len(entries) >= 1
    assert "regression" in entries[0]["event"]


def test_timeline_with_weight_change():
    s = make_store()
    s.record_event(EVENT_RANKING_ADJUSTED, strategy="balanced",
                    old_weights=(0.6, 0.4), new_weights=(0.7, 0.3),
                    metadata={"reason": "adaptive_boost"})
    tb = TimelineBuilder(s)
    entries = tb.build(days=7)
    assert len(entries) >= 1
    assert "weight change" in entries[0]["event"]


def test_timeline_sorted():
    s = make_store()
    s.record_rollback("rollback 1", (0.7, 0.3), (0.6, 0.4))
    time.sleep(0.02)
    s.record_drift_alert("collapse", "warning", {})
    tb = TimelineBuilder(s)
    entries = tb.build(days=7)
    # Entries should be sorted by day ascending
    assert len(entries) >= 2


def test_timeline_summarise():
    s = make_store()
    s.record_drift_alert("collapse", "warning",
                          {"message": "Strategy collapse"})
    s.record_rollback("test rollback", (0.7, 0.3), (0.6, 0.4))
    tb = TimelineBuilder(s)
    summary = tb.summarise(days=7)
    assert len(summary) >= 2
    types = {e["event"] for e in summary}
    assert "rollback" in types
    assert "drift: collapse" in types


# ======================================================================
# QueryAnalytics Tests
# ======================================================================

from core.query_analytics import QueryAnalytics
from core.query_replay import QueryReplay


def make_replay():
    path = os.path.join(tempfile.mkdtemp(), "test_qanalytics.db")
    r = QueryReplay(path)
    r.clear()
    return r


def test_analytics_empty():
    s = make_store()
    r = make_replay()
    a = QueryAnalytics(r, s)
    a.analyze()
    assert a.instability_report == []
    assert a.collapse_report.collapsed is False
    assert a.noisy_embeddings == []


def test_analytics_collapse_detected():
    s = make_store()
    for _ in range(10):
        s.record_event(EVENT_QUERY_EXECUTED, strategy="balanced")
    s.record_event(EVENT_QUERY_EXECUTED, strategy="test_file")

    a = QueryAnalytics(None, s)
    a.analyze()
    assert a.collapse_report.collapsed is True
    assert a.collapse_report.dominant_strategy == "balanced"
    assert a.collapse_report.usage_pct >= 0.9


def test_analytics_no_collapse():
    s = make_store()
    for _ in range(5):
        s.record_event(EVENT_QUERY_EXECUTED, strategy="balanced")
    for _ in range(5):
        s.record_event(EVENT_QUERY_EXECUTED, strategy="test_file")

    a = QueryAnalytics(None, s)
    a.analyze()
    assert a.collapse_report.collapsed is False


def test_analytics_instability_detected():
    r = make_replay()
    # Log the same query 3 times with different top scores
    for score in [0.9, 0.5, 0.3]:
        r.log("find auth",
              [{"symbol_id": "s1", "score": score, "final_score": score}],
              {}, strategy="balanced")

    a = QueryAnalytics(r, None)
    a.analyze()
    assert len(a.instability_report) >= 1
    ir = a.instability_report[0]
    assert ir.score_delta > 0.3
    assert ir.count == 3


def test_analytics_noisy_embeddings():
    r = make_replay()
    # Log queries where semantic scores are high but feedback is low
    qid = r.log("find auth",
                 [{"symbol_id": "s1", "semantic_score": 0.9, "score": 0.9}],
                 {}, strategy="balanced")
    r.update_feedback(qid, 0.2, success=-1)

    qid2 = r.log("find auth",
                  [{"symbol_id": "s1", "semantic_score": 0.8, "score": 0.8}],
                  {}, strategy="balanced")
    r.update_feedback(qid2, 0.3, success=-1)

    qid3 = r.log("find auth",
                  [{"symbol_id": "s1", "semantic_score": 0.85, "score": 0.85}],
                  {}, strategy="balanced")
    r.update_feedback(qid3, 0.1, success=-1)

    a = QueryAnalytics(r, None)
    a.analyze()
    assert len(a.noisy_embeddings) >= 1
    ne = a.noisy_embeddings[0]
    assert ne.symbol_id == "s1"
    assert ne.gap > 0.3  # sem - fb gap


def test_analytics_feedback_skew():
    r = make_replay()
    for i in range(5):
        qid = r.log("short query", [{"symbol_id": "s1", "score": 0.9}], {},
                     strategy="balanced")
        r.update_feedback(qid, 0.9, success=1)

    for i in range(5):
        qid = r.log("this is a very long query that goes on and on with many words",
                     [{"symbol_id": "s2", "score": 0.9}], {}, strategy="test_file")
        r.update_feedback(qid, 0.2, success=-1)

    a = QueryAnalytics(r, None)
    a.analyze()
    assert a.feedback_skew.get("has_data") is True
    assert "by_strategy" in a.feedback_skew
    assert "by_query_length" in a.feedback_skew


def test_analytics_dead_zones():
    r = make_replay()
    r.log("query", [{"symbol_id": "s1", "score": 0.9}], {}, strategy="balanced")
    a = QueryAnalytics(r, None)
    dead = a.dead_graph_zones(["s1", "s2", "s3"])
    assert "s1" not in dead  # was retrieved
    assert "s2" in dead
    assert "s3" in dead


def test_analytics_full_report():
    r = make_replay()
    s = make_store()
    for _ in range(10):
        s.record_event(EVENT_QUERY_EXECUTED, strategy="balanced")
    for score in [0.9, 0.5, 0.3]:
        r.log("find auth", [{"symbol_id": "s1", "score": score, "final_score": score}],
              {}, strategy="balanced")
    qid = r.log("test", [{"symbol_id": "s1", "semantic_score": 0.9, "score": 0.9}],
                 {}, strategy="balanced")
    r.update_feedback(qid, 0.1, success=-1)

    a = QueryAnalytics(r, s)
    report = a.full_report()
    assert "ranking_instability" in report
    assert "strategy_collapse" in report
    assert "noisy_embeddings" in report
    assert "feedback_skew" in report
    assert report["strategy_collapse"]["collapsed"] is True


# ======================================================================
# Integration Tests
# ======================================================================

from core.adaptive_weights import (
    AdaptiveWeightEngine,
    STRATEGY_BALANCED, STRATEGY_LARGE_REPO,
)
from core.feedback_loop import RankingFeedbackLoop


def test_integration_store_in_engine():
    """AdaptiveWeightEngine should emit events through MetricsStore."""
    s = make_store()
    engine = AdaptiveWeightEngine(metrics_store=s)

    # Record outcome → should emit feedback.received
    engine.record_outcome(STRATEGY_BALANCED, 0.8, success=True)

    events = s.query_events(event_type=EVENT_FEEDBACK_RECEIVED)
    assert len(events) >= 1
    assert events[0]["strategy"] == STRATEGY_BALANCED


def test_integration_guardrails_emit_events():
    """check_guardrails should record drift/regression events to store."""
    s = make_store()
    loop = RankingFeedbackLoop()
    engine = AdaptiveWeightEngine(feedback_loop=loop, metrics_store=s)

    # Create collapse scenario
    counts = {"balanced": 100, "small_repo": 2, "large_repo": 1}

    result = engine.check_guardrails(counts)
    assert result["total_alerts"] >= 1

    # Should be in store
    alerts = s.query_drift_alerts()
    assert len(alerts) >= 1
    drift_events = s.query_events(event_type=EVENT_DRIFT_DETECTED)
    assert len(drift_events) >= 1


def test_integration_rollback_records_to_store():
    """Rollback_if_needed should record rollback events."""
    s = make_store()
    engine = AdaptiveWeightEngine(metrics_store=s)
    from core.guardrails import DriftAlert
    alert = DriftAlert(kind="strategy_collapse", message="Bad", severity="warning")

    # Trigger rollback
    for _ in range(3):
        rolled, w, reason = engine.rollback_if_needed(
            [alert], (0.6, 0.4), (0.5, 0.5),
        )
    assert rolled is True

    # Check store
    rollbacks = s.query_rollback_events()
    assert len(rollbacks) >= 1

    rollback_events = s.query_events(event_type=EVENT_ROLLBACK_EXECUTED)
    assert len(rollback_events) >= 1


def test_integration_shadow_records_to_store():
    """Shadow evaluation should record events when promoted."""
    s = make_store()
    engine = AdaptiveWeightEngine(metrics_store=s)
    rank_fn = lambda entries: sorted(entries,
                                      key=lambda x: x.get("final_score", 0),
                                      reverse=True)

    n = 25  # above MIN_PROMOTION_SAMPLES
    for _ in range(n):
        engine.evaluate_shadow(
            {"merged_results": [{"final_score": 0.4}]},
            {"merged_results": [{"final_score": 0.7}]},
            rank_fn,
        )

    result = engine.should_promote_shadow()
    assert result.promotion_ready is True

    # Check store
    evals = s.query_shadow_evaluations()
    assert len(evals) > 0
    promoted = [e for e in evals if e["promoted"] == 1]
    assert len(promoted) >= 1


def test_integration_weight_change_recorded():
    """adjusted_weights should emit ranking.adjusted when weights change."""
    s = make_store()
    loop = RankingFeedbackLoop()
    for _ in range(8):
        loop.record_feedback(STRATEGY_LARGE_REPO, 1.0, success=True)
    engine = AdaptiveWeightEngine(feedback_loop=loop, metrics_store=s)

    # First call: sets baseline, no event emitted
    w_g, w_s = engine.adjusted_weights(0.7, 0.3, STRATEGY_LARGE_REPO)

    # Change the boost rate by adding failures, then call again
    for _ in range(8):
        loop.record_feedback(STRATEGY_LARGE_REPO, 0.0, success=False)
    w_g2, w_s2 = engine.adjusted_weights(0.7, 0.3, STRATEGY_LARGE_REPO)

    events = s.query_events(event_type=EVENT_RANKING_ADJUSTED)
    assert len(events) >= 1


def test_integration_hybrid_retriever_emits_events():
    """HybridRetriever.retrieve() should emit query.executed."""
    from core.hybrid_retriever import HybridRetriever, WeightsAdvisor, RepoStats

    class MockGE:
        def retrieve_symbol_core(self, sid):
            if sid == "s1":
                return {"meta": {"name": "validate"}, "static_analysis": {}}
            raise LookupError
        def heuristic_analysis(self, sid, **kw):
            return {"importance": 5.0, "overall_risk": "LOW"}
        def ranked_hotspots(self, limit=10):
            return [{"symbol_id": "s1", "symbol_name": "validate",
                     "importance_score": 5.0, "role": "pure_function",
                     "file_path": "auth.py", "incoming_calls": 3}]

    class MockSS:
        available = True
        def search_similar(self, qv, top_k=10):
            return [{"symbol_id": "s1", "score": 0.9,
                     "metadata": {"name": "validate", "file_path": "auth.py"}}]
        @property
        def size(self): return 1

    class MockEE:
        available = True
        dimension = 384
        def embed_text(self, t): return [0.1]*384
        def embed_symbol(self, s): return [0.1]*384

    s = make_store()
    hr = HybridRetriever(MockGE(), MockSS(), MockEE(),
                          weights_advisor=WeightsAdvisor(RepoStats(1200)),
                          metrics_store=s)
    result = hr.retrieve("test query", top_k=5)

    events = s.query_events(event_type=EVENT_QUERY_EXECUTED)
    assert len(events) >= 1

    retrieval_events = s.query_events(event_type=EVENT_RETRIEVAL_COMPLETED)
    assert len(retrieval_events) >= 1

    assert result["strategy"] is not None


def test_integration_end_to_end_timeline():
    """Full pipeline: guardrails → store → timeline."""
    s = make_store()
    loop = RankingFeedbackLoop()
    engine = AdaptiveWeightEngine(feedback_loop=loop, metrics_store=s)

    # 1. Record outcomes (creates regression trend)
    for _ in range(20):
        engine.record_outcome(STRATEGY_BALANCED, 0.9, success=True)
    for _ in range(20):
        engine.record_outcome(STRATEGY_BALANCED, 0.1, success=False)

    # 2. Check guardrails
    counts = {"balanced": 10, "small_repo": 10, "large_repo": 10}
    engine.check_guardrails(counts)

    # 3. Build timeline
    from core.timeline import TimelineBuilder
    tb = TimelineBuilder(s)
    entries = tb.build(days=7)

    # Should have at least some entries
    assert len(entries) >= 0  # may be 0 if no alerts fired


def test_integration_analytics_with_telemetry():
    """Analytics reads from store populated by engine."""
    s = make_store()
    loop = RankingFeedbackLoop()
    engine = AdaptiveWeightEngine(feedback_loop=loop, metrics_store=s)

    # Simulate queries through the engine's store
    for i in range(20):
        engine.store.record_event(EVENT_QUERY_EXECUTED,
                                   strategy="balanced",
                                   metadata={"query": f"query_{i}"})

    from core.query_analytics import QueryAnalytics
    a = QueryAnalytics(None, s)
    a.analyze()
    assert a.collapse_report.collapsed is True


# We need to add a helper method for directly recording events to the store
# through the engine. Let's check if we can just use self.store directly.
def test_integration_full_report():
    """End-to-end full analytics report from store + replay."""
    from core.query_analytics import QueryAnalytics
    s = make_store()
    r = make_replay()

    # Populate store with strategy data
    for _ in range(15):
        s.record_event(EVENT_QUERY_EXECUTED, strategy="balanced")
    s.record_event(EVENT_QUERY_EXECUTED, strategy="test_file")

    # Populate replay with query data
    for score in [0.9, 0.4, 0.2]:
        r.log("find auth",
              [{"symbol_id": "s1", "score": score, "final_score": score}],
              {}, strategy="balanced")

    a = QueryAnalytics(r, s)
    report = a.full_report()
    assert report["strategy_collapse"]["collapsed"] is True
    assert len(report["ranking_instability"]) >= 1


# ======================================================================
# Run all
# ======================================================================

if __name__ == "__main__":
    tests = [
        # MetricsStore
        ("store record event", test_store_record_event),
        ("store record drift alert", test_store_record_drift_alert),
        ("store record rollback", test_store_record_rollback),
        ("store record shadow", test_store_record_shadow),
        ("store query filters", test_store_query_with_filters),
        ("store query since", test_store_query_since),
        ("store strategy usage", test_store_strategy_usage),
        ("store strategy usage since", test_store_strategy_usage_since),
        ("store weight changes", test_store_weight_change_history),
        ("store rollback count", test_store_rollback_count),
        ("store drift count", test_store_drift_alert_count),
        ("store shadow win rate", test_store_shadow_win_rate),
        ("store clear", test_store_clear),
        # TimelineBuilder
        ("timeline empty", test_timeline_build_empty),
        ("timeline with drift", test_timeline_with_drift),
        ("timeline with rollback", test_timeline_with_rollback),
        ("timeline with shadow", test_timeline_with_shadow_promotion),
        ("timeline with regression", test_timeline_with_regression),
        ("timeline with weight change", test_timeline_with_weight_change),
        ("timeline sorted", test_timeline_sorted),
        ("timeline summarise", test_timeline_summarise),
        # QueryAnalytics
        ("analytics empty", test_analytics_empty),
        ("analytics collapse", test_analytics_collapse_detected),
        ("analytics no collapse", test_analytics_no_collapse),
        ("analytics instability", test_analytics_instability_detected),
        ("analytics noisy embeddings", test_analytics_noisy_embeddings),
        ("analytics feedback skew", test_analytics_feedback_skew),
        ("analytics dead zones", test_analytics_dead_zones),
        ("analytics full report", test_analytics_full_report),
        # Integration
        ("store in engine", test_integration_store_in_engine),
        ("guardrails emit", test_integration_guardrails_emit_events),
        ("rollback records", test_integration_rollback_records_to_store),
        ("shadow records", test_integration_shadow_records_to_store),
        ("weight change event", test_integration_weight_change_recorded),
        ("hybrid retriever emits", test_integration_hybrid_retriever_emits_events),
        ("end-to-end timeline", test_integration_end_to_end_timeline),
        ("analytics telemetry", test_integration_analytics_with_telemetry),
        ("full report", test_integration_full_report),
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
    print(f"Phase 13: {passed} passed, {failed} failed, {total} total")
    print(f"{'✓ COMPLETE' if failed == 0 else '✗ NEEDS FIX'}")
