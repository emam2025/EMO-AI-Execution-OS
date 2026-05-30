"""Tests for Intelligence Feedback Loop."""
import sys, os, tempfile
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import warnings
warnings.filterwarnings("ignore")
import logging
logging.disable(logging.CRITICAL)

from core.feedback_intel import (
    FeedbackIntelligence, ToolOutcome, RankingHeuristic,
    FEEDBACK_INTEL_VERSION,
)


def test_version():
    assert FEEDBACK_INTEL_VERSION == "1.0.0"


def test_ingest_success_tracks_outcomes():
    fb = FeedbackIntelligence(db_path=Path(tempfile.mkdtemp()) / "fb.db")
    fb.ingest([
        {"tool": "agent.explain", "status": "completed", "result": {"insight_summary": "ok"}},
        {"tool": "graph_retrieval.ranked_hotspots", "status": "completed", "result": {"hotspots": []}},
    ])
    assert fb.total_observations() == 2


def test_ingest_failure():
    fb = FeedbackIntelligence(db_path=Path(tempfile.mkdtemp()) / "fb.db")
    fb.ingest([
        {"tool": "agent.explain", "status": "failed", "error": "timeout", "result": {}},
    ])
    assert fb.total_observations() == 1


def test_tool_weights_default():
    fb = FeedbackIntelligence(db_path=Path(tempfile.mkdtemp()) / "fb.db")
    weights = fb.tool_weights("nonexistent")
    assert weights == {}  # insufficient observations → empty


def test_tool_weights_after_data():
    fb = FeedbackIntelligence(db_path=Path(tempfile.mkdtemp()) / "fb.db")
    for _ in range(6):  # need >= 5 total
        fb.ingest([{"tool": "t1", "status": "completed", "result": {}}], intent="explain")
    fb.ingest([{"tool": "t2", "status": "failed", "error": "timeout", "result": {}}], intent="explain")
    weights = fb.tool_weights("explain")
    assert "t1" in weights
    # prior_alpha=4 + 6 successes = 10, prior_beta=1 + 0 failures = 1 → 10/11 ≈ 0.909
    assert abs(weights["t1"] - 0.909) < 0.01


def test_confidence_calibration():
    fb = FeedbackIntelligence(db_path=Path(tempfile.mkdtemp()) / "fb.db")
    for _ in range(5):  # _MIN_OBSERVATIONS = 5
        fb.ingest([
            {"tool": "agent.explain", "status": "failed", "error": "timeout", "result": {}},
            {"tool": "agent.explain", "status": "completed", "result": {}},
        ], intent="explain")
    adj = fb.confidence_adjustment("explain")
    # 5 success, 5 failure → rate = 0.5 → adj = 0.5 + 0.5 = 1.0
    assert adj == 1.0


def test_tool_weights_reflect_high_failure_rate():
    fb = FeedbackIntelligence(db_path=Path(tempfile.mkdtemp()) / "fb.db")
    for _ in range(10):
        fb.ingest([{"tool": "agent.explain", "status": "failed",
                     "error": "timeout", "result": {}}], intent="explain")
        fb.ingest([{"tool": "agent.top_hotspots", "status": "completed",
                     "result": {}}], intent="explain")
    weights = fb.tool_weights("explain")
    assert "agent.explain" in weights
    # 10 failures + prior = Beta(4, 1+10) → 4/15 ≈ 0.267
    assert weights["agent.explain"] < 0.5
    # agent.top_hotspots: 10 successes + prior = Beta(4+10, 1) → 14/15 ≈ 0.933
    assert weights["agent.top_hotspots"] > 0.5


def test_confidence_adjustment_filtered_by_intent():
    fb = FeedbackIntelligence(db_path=Path(tempfile.mkdtemp()) / "fb.db")
    for _ in range(10):
        fb.ingest([{"tool": "agent.explain", "status": "failed",
                     "error": "timeout", "result": {}}], intent="explain")
    adj = fb.confidence_adjustment("explain")
    # 10 failures + prior = Beta(4, 1+10) → 4/15 ≈ 0.267 → / 0.8 (prior) ≈ 0.333
    assert adj < 1.0
    # unrelated intent should get default 1.0
    assert fb.confidence_adjustment("hotspots") == 1.0


def test_weights_below_min_observations_return_default():
    fb = FeedbackIntelligence(db_path=Path(tempfile.mkdtemp()) / "fb.db")
    fb.ingest([{"tool": "agent.explain", "status": "failed", "error": "timeout",
                "result": {}}], intent="explain")
    weights = fb.tool_weights("explain")
    # Only 1 observation — below default min (5), returns prior 0.8
    assert weights == {}


def test_classify_error_timeout():
    assert FeedbackIntelligence._classify_error("timeout", {}) == "timeout"
    assert FeedbackIntelligence._classify_error("connection timeout", {}) == "timeout"


def test_classify_error_contract():
    assert FeedbackIntelligence._classify_error("contract violation", {}) == "contract"


def test_classify_error_lookup():
    assert FeedbackIntelligence._classify_error("Symbol not found", {}) == "lookup"


def test_classify_error_runtime():
    assert FeedbackIntelligence._classify_error("Something broke", {}) == "runtime"


def test_classify_error_empty():
    assert FeedbackIntelligence._classify_error("", {}) == ""


def test_report():
    fb = FeedbackIntelligence(db_path=Path(tempfile.mkdtemp()) / "fb.db")
    fb.ingest([{"tool": "agent.explain", "status": "completed", "result": {}}])
    report = fb.report()
    assert report["version"] == "1.0.0"
    assert report["total_observations"] == 1
    assert "agent.explain" in report["tools_tracked"]


def test_ingest_with_none_result():
    """None result should not crash ingest."""
    fb = FeedbackIntelligence(db_path=Path(tempfile.mkdtemp()) / "fb.db")
    fb.ingest([{"tool": "agent.explain", "status": "completed", "result": None}])
    assert fb.total_observations() == 1


def test_multiple_batches():
    """Ingesting in multiple batches accumulates correctly."""
    fb = FeedbackIntelligence(db_path=Path(tempfile.mkdtemp()) / "fb.db")
    for _ in range(6):
        fb.ingest([{"tool": "t1", "status": "completed", "result": {}}], intent="g")
        fb.ingest([{"tool": "t2", "status": "completed", "result": {}}], intent="g")
    fb.ingest([{"tool": "t1", "status": "failed", "error": "err", "result": {}}], intent="g")
    assert fb.total_observations() == 13
    weights = fb.tool_weights("g")
    assert "t1" in weights
    assert "t2" in weights
    # t1: 6 success, 1 failure → posterior = (4+6) / (4+6+1+1) = 10/12 ≈ 0.833
    assert abs(weights["t1"] - 0.833) < 0.01
    # t2: 6 success, 0 failures → posterior = (4+6) / (4+6+0+1) = 10/11 ≈ 0.909
    assert abs(weights["t2"] - 0.909) < 0.01
