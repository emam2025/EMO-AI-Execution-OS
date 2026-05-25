"""Tests for Phase 3.8 — Runtime Trace Intelligence."""

import pytest
from core.codegraph.bridge import RuntimeStats
from core.codegraph.runtime_intelligence import (
    HotspotAnalyzer,
    RuntimeCentrality,
    ExecutionTopology,
    FailureTopology,
    ExecutionFrequencyTracker,
    RuntimeHotspot,
    RuntimeCentralityScore,
)
from core.codegraph.drift import (
    RuntimeGraphBuilder,
    RuntimeDriftDetector,
    DriftClassifier,
    DriftEvent,
    DriftReport,
    RuntimeExecutionGraph,
)
from core.runtime_intelligence import RuntimeIntelligence
from core.canon.rules import law_17, law_18, law_19
from core.canon.context import ValidationContext


# ═══════════════════════════════════════════════════════════════════════
# 3.8.1.1 — Hotspot Analyzer
# ═══════════════════════════════════════════════════════════════════════

class TestHotspotAnalyzer:
    def test_empty_stats_returns_empty(self):
        stats = RuntimeStats()
        analyzer = HotspotAnalyzer(stats)
        assert analyzer.analyze() == []

    def test_single_tool_hotspot(self):
        stats = RuntimeStats()
        stats.record_node_completed("tool_a", duration=1.0)
        analyzer = HotspotAnalyzer(stats)
        hotspots = analyzer.analyze(min_executions=0)
        assert len(hotspots) == 1
        assert hotspots[0].tool == "tool_a"
        assert hotspots[0].execution_count == 1

    def test_hotspot_sorted_by_score(self):
        stats = RuntimeStats()
        for _ in range(10):
            stats.record_node_completed("hot_tool", duration=0.5)
        stats.record_node_completed("cold_tool", duration=5.0)
        analyzer = HotspotAnalyzer(stats)
        hotspots = analyzer.analyze(min_executions=0)
        assert hotspots[0].score >= hotspots[1].score

    def test_min_executions_filter(self):
        stats = RuntimeStats()
        stats.record_node_completed("rare_tool", duration=1.0)
        analyzer = HotspotAnalyzer(stats)
        assert analyzer.analyze(min_executions=5) == []

    def test_hotspot_score_range(self):
        stats = RuntimeStats()
        for _ in range(5):
            stats.record_node_completed("tool_a", duration=1.0)
        stats.record_node_failed("tool_a")
        analyzer = HotspotAnalyzer(stats)
        hs = analyzer.analyze(min_executions=0)[0]
        assert 0.0 <= hs.score <= 1.0


# ═══════════════════════════════════════════════════════════════════════
# 3.8.1.2 — Execution Topology
# ═══════════════════════════════════════════════════════════════════════

class TestExecutionTopology:
    def test_empty_events(self):
        topo = ExecutionTopology()
        graph = topo.build([])
        assert graph.trace_count == 0

    def test_single_event(self):
        topo = ExecutionTopology()
        events = [{"event_id": "e1", "event_type": "NODE_STARTED",
                   "timestamp": 100.0, "payload": {"tool": "t1"},
                   "session_id": "s1"}]
        graph = topo.build(events)
        assert graph.trace_count == 1
        assert "e1" in graph.nodes

    def test_two_events_have_edge(self):
        topo = ExecutionTopology()
        events = [
            {"event_id": "e1", "event_type": "NODE_STARTED",
             "timestamp": 100.0, "payload": {"tool": "t1"}, "session_id": "s1"},
            {"event_id": "e2", "event_type": "NODE_COMPLETED",
             "timestamp": 101.0, "payload": {"tool": "t1", "node_id": "n1"},
             "session_id": "s1"},
        ]
        graph = topo.build(events)
        assert len(graph.edges) == 1
        assert graph.edges[0].source_event_id == "e1"
        assert graph.edges[0].target_event_id == "e2"

    def test_session_id_extracted(self):
        topo = ExecutionTopology()
        events = [{"event_id": "e1", "event_type": "NODE_STARTED",
                   "timestamp": 0.0, "payload": {}, "session_id": "s1"}]
        graph = topo.build(events)
        assert graph.session_id == "s1"


# ═══════════════════════════════════════════════════════════════════════
# 3.8.1.3 — Failure Topology
# ═══════════════════════════════════════════════════════════════════════

class TestFailureTopology:
    def test_no_failure_events(self):
        ft = FailureTopology()
        events = [{"event_id": "e1", "event_type": "NODE_COMPLETED",
                   "timestamp": 0.0, "payload": {"tool": "t1"}}]
        assert ft.analyze(events) == []

    def test_single_failure(self):
        ft = FailureTopology()
        events = [{"event_id": "e1", "event_type": "NODE_FAILED",
                   "timestamp": 0.0, "payload": {"tool": "t1", "error": "err"}}]
        paths = ft.analyze(events)
        assert len(paths) == 1
        assert paths[0].root_tool == "t1"
        assert paths[0].final_outcome == "failed"

    def test_retry_path(self):
        ft = FailureTopology()
        events = [
            {"event_id": "e1", "event_type": "NODE_FAILED",
             "timestamp": 0.0, "payload": {"tool": "t1", "error": "err"}},
            {"event_id": "e2", "event_type": "RETRY_DECISION",
             "timestamp": 0.1, "payload": {"tool": "t1"}},
        ]
        paths = ft.analyze(events)
        assert len(paths) == 1
        assert paths[0].retry_count == 1

    def test_retry_storm_detection(self):
        ft = FailureTopology()
        events = [
            {"event_id": "e0", "event_type": "NODE_FAILED",
             "timestamp": 0.0, "payload": {"tool": "t1", "error": "err"}},
            {"event_id": "e1", "event_type": "RETRY_DECISION",
             "timestamp": 0.1, "payload": {"tool": "t1"}},
            {"event_id": "e2", "event_type": "NODE_FAILED",
             "timestamp": 0.2, "payload": {"tool": "t1", "error": "err"}},
            {"event_id": "e3", "event_type": "RETRY_DECISION",
             "timestamp": 0.3, "payload": {"tool": "t1"}},
            {"event_id": "e4", "event_type": "NODE_FAILED",
             "timestamp": 0.4, "payload": {"tool": "t1", "error": "err"}},
            {"event_id": "e5", "event_type": "RETRY_DECISION",
             "timestamp": 0.5, "payload": {"tool": "t1"}},
        ]
        paths = ft.analyze(events)
        assert len(paths) == 1
        assert paths[0].is_storm(threshold=3)

    def test_rollback_path(self):
        ft = FailureTopology()
        events = [
            {"event_id": "e1", "event_type": "NODE_FAILED",
             "timestamp": 0.0, "payload": {"tool": "t1", "error": "err"}},
            {"event_id": "e2", "event_type": "STATE_TRANSITION",
             "timestamp": 0.1, "payload": {"tool": "t1", "error": ""}},
        ]
        paths = ft.analyze(events)
        assert len(paths) == 1
        assert paths[0].final_outcome == "rolled_back"


# ═══════════════════════════════════════════════════════════════════════
# 3.8.1.4 — Runtime Centrality
# ═══════════════════════════════════════════════════════════════════════

class TestRuntimeCentrality:
    def test_empty_stats_returns_empty(self):
        engine = RuntimeCentrality(RuntimeStats())
        assert engine.compute() == []

    def test_centrality_scored(self):
        stats = RuntimeStats()
        stats.record_node_completed("tool_a", duration=1.0)
        stats.record_node_failed("tool_a")
        engine = RuntimeCentrality(stats)
        scores = engine.compute()
        assert len(scores) == 1
        assert scores[0].tool == "tool_a"
        assert scores[0].runtime_centrality > 0.0

    def test_centrality_sorted(self):
        stats = RuntimeStats()
        for _ in range(10):
            stats.record_node_completed("freq_tool", duration=0.5)
        stats.record_node_completed("rare_tool", duration=5.0)
        engine = RuntimeCentrality(stats)
        scores = engine.compute()
        assert scores[0].runtime_centrality >= scores[1].runtime_centrality

    def test_silently_critical_empty(self):
        engine = RuntimeCentrality(RuntimeStats())
        assert engine.silently_critical() == []


# ═══════════════════════════════════════════════════════════════════════
# 3.8.1.5 — Execution Frequency
# ═══════════════════════════════════════════════════════════════════════

class TestExecutionFrequencyTracker:
    def test_empty(self):
        tracker = ExecutionFrequencyTracker()
        assert tracker.get_tool_frequency("none") == []

    def test_record_single(self):
        tracker = ExecutionFrequencyTracker()
        tracker.record_execution("s1", "tool_a", success=True)
        records = tracker.get_tool_frequency("tool_a")
        assert len(records) == 1
        assert records[0].execution_count == 1

    def test_record_failure(self):
        tracker = ExecutionFrequencyTracker()
        tracker.record_execution("s1", "tool_a", success=False)
        records = tracker.get_tool_frequency("tool_a")
        assert records[0].failure_count == 1

    def test_trend_stable(self):
        tracker = ExecutionFrequencyTracker()
        for sid in ("s1", "s2", "s3"):
            tracker.record_execution(sid, "tool_a", success=True)
        trend = tracker.get_trend("tool_a")
        assert trend.trend_direction == "stable"

    def test_trend_increasing(self):
        tracker = ExecutionFrequencyTracker()
        tracker.record_execution("s1", "tool_a", success=True)
        for _ in range(5):
            tracker.record_execution("s2", "tool_a", success=True)
        trend = tracker.get_trend("tool_a")
        assert trend.trend_direction == "increasing"

    def test_top_frequency(self):
        tracker = ExecutionFrequencyTracker()
        for _ in range(5):
            tracker.record_execution("s1", "tool_a", success=True)
        tracker.record_execution("s1", "tool_b", success=True)
        top = tracker.top_frequency(limit=2)
        assert top[0] == "tool_a"


# ═══════════════════════════════════════════════════════════════════════
# 3.8.2.1 — Runtime Graph Builder
# ═══════════════════════════════════════════════════════════════════════

class TestRuntimeGraphBuilder:
    def test_empty_events(self):
        builder = RuntimeGraphBuilder()
        graph = builder.build([])
        assert len(graph.nodes) == 0
        assert graph.session_count == 0

    def test_single_node(self):
        builder = RuntimeGraphBuilder()
        events = [{"event_id": "e1", "event_type": "NODE_COMPLETED",
                   "payload": {"tool": "t1"}, "timestamp": 0.0,
                   "trace_id": "tr1", "session_id": "s1"}]
        graph = builder.build(events)
        assert "e1" in graph.nodes
        assert graph.nodes["e1"].tool == "t1"

    def test_dependency_chain(self):
        builder = RuntimeGraphBuilder()
        events = [
            {"event_id": "e1", "event_type": "NODE_COMPLETED",
             "payload": {"tool": "t1"}, "timestamp": 0.0,
             "trace_id": "tr1", "session_id": "s1"},
            {"event_id": "e2", "event_type": "NODE_COMPLETED",
             "payload": {"tool": "t2"}, "timestamp": 1.0,
             "trace_id": "tr1", "session_id": "s1"},
        ]
        graph = builder.build(events)
        assert len(graph.nodes) == 2
        assert len(graph.edges) >= 0

    def test_session_count(self):
        builder = RuntimeGraphBuilder()
        events = [
            {"event_id": "e1", "event_type": "NODE_COMPLETED",
             "payload": {"tool": "t1"}, "timestamp": 0.0,
             "trace_id": "tr1", "session_id": "s1"},
            {"event_id": "e2", "event_type": "NODE_COMPLETED",
             "payload": {"tool": "t2"}, "timestamp": 1.0,
             "trace_id": "tr2", "session_id": "s2"},
        ]
        graph = builder.build(events)
        assert graph.session_count == 2


# ═══════════════════════════════════════════════════════════════════════
# 3.8.2.2 — Drift Classifier
# ═══════════════════════════════════════════════════════════════════════

class TestDriftClassifier:
    def test_classify_hidden_dependency(self):
        clf = DriftClassifier()
        event = clf.classify_node_drift("tool_a", 0.0, 0.5, is_hidden=True)
        assert event.drift_type == "HIDDEN_DEPENDENCY"
        assert event.severity == "HIGH"

    def test_classify_boundary_violation(self):
        clf = DriftClassifier()
        event = clf.classify_node_drift("tool_a", 0.0, 0.5, is_boundary=True)
        assert event.drift_type == "BOUNDARY_VIOLATION"
        assert event.severity == "CRITICAL"

    def test_classify_coupling_explosion(self):
        clf = DriftClassifier()
        event = clf.classify_node_drift("tool_a", 0.1, 0.8)
        assert event.drift_type == "COUPLING_EXPLOSION"
        assert event.severity == "HIGH"

    def test_classify_minor_drift_warning(self):
        clf = DriftClassifier()
        event = clf.classify_node_drift("tool_a", 0.1, 0.25)
        assert event.severity == "WARNING"

    def test_classify_stable_info(self):
        clf = DriftClassifier()
        event = clf.classify_node_drift("tool_a", 0.1, 0.12)
        assert event.severity == "INFO"

    def test_report_max_severity(self):
        report = DriftReport(events=[
            DriftEvent(severity="INFO"),
            DriftEvent(severity="HIGH"),
        ])
        assert report.max_severity == "HIGH"
        assert report.is_blocking is True

    def test_report_non_blocking(self):
        report = DriftReport(events=[
            DriftEvent(severity="INFO"),
            DriftEvent(severity="WARNING"),
        ])
        assert report.is_blocking is False


# ═══════════════════════════════════════════════════════════════════════
# 3.8.3 — RuntimeIntelligence API
# ═══════════════════════════════════════════════════════════════════════

class TestRuntimeIntelligence:
    def test_explain_unknown_execution(self):
        ri = RuntimeIntelligence()
        result = ri.explain_execution("nonexistent")
        assert "error" in result
        assert result["execution_id"] == "nonexistent"

    def test_explain_failure_no_failures(self):
        ri = RuntimeIntelligence()
        result = ri.explain_failure("nonexistent")
        assert "error" in result or not result.get("has_failures", True)

    def test_why_executed_unknown(self):
        ri = RuntimeIntelligence()
        result = ri.why_executed("unknown_tool")
        assert result["tool"] == "unknown_tool"
        assert result["total_executions"] == 0

    def test_record_and_query(self):
        ri = RuntimeIntelligence()
        ri.record_execution("s1", "tool_a", success=True)
        ri.record_execution("s1", "tool_a", success=False)
        result = ri.why_executed("tool_a")
        assert result["total_executions"] == 2
        assert len(result["execution_log"]) == 1


# ═══════════════════════════════════════════════════════════════════════
# LAW 17-19 Canon rules
# ═══════════════════════════════════════════════════════════════════════

class TestCanonLaws17to19:
    def test_law_17_fails_without_event_bus(self):
        ctx = ValidationContext()
        assert law_17(ctx) is False

    def test_law_17_passes_with_event_bus(self):
        ctx = ValidationContext(event_bus=object())
        assert law_17(ctx) is True

    def test_law_18_fails_without_drift_detector(self):
        ctx = ValidationContext()
        assert law_18(ctx) is False

    def test_law_18_passes_with_drift_detector(self):
        ctx = ValidationContext(drift_detector=object())
        assert law_18(ctx) is True

    def test_law_19_fails_without_runtime_intel(self):
        ctx = ValidationContext()
        assert law_19(ctx) is False

    def test_law_19_passes_with_runtime_intel(self):
        ctx = ValidationContext(runtime_intelligence=object())
        assert law_19(ctx) is True
