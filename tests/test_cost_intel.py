"""Tests for Cost & Performance Intelligence."""
import sys, os, tempfile
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import warnings
warnings.filterwarnings("ignore")
import logging
logging.disable(logging.CRITICAL)
import time

from core.execution_engine import PlanNode
from core.cost_intel import (
    CostTracker, CostAwareScheduler, NodeCost, COST_INTEL_VERSION,
)


def test_cost_intel_version():
    assert COST_INTEL_VERSION == "1.0.0"


def test_node_cost_total():
    cost = NodeCost(tool="test", duration_seconds=2.0, estimated_tokens=5000, io_weight=1.5)
    expected = (2.0 + 5000 / 100_000) * 1.5
    assert abs(cost.total_cost - expected) < 0.001


def test_tracker_record_and_p50():
    tracker = CostTracker(db_path=Path(tempfile.mkdtemp()) / "cost.db")
    for d in [0.1, 0.2, 0.3]:
        tracker.record(NodeCost(tool="t1", duration_seconds=d))
    assert tracker.count("t1") == 3
    assert abs(tracker.p50("t1") - 0.2) < 0.01


def test_tracker_p95():
    tracker = CostTracker(db_path=Path(tempfile.mkdtemp()) / "cost.db")
    durs = list(range(1, 101))  # 1..100 sec
    for d in durs:
        tracker.record(NodeCost(tool="slow", duration_seconds=float(d)))
    assert tracker.count("slow") == 100
    p95 = tracker.p95("slow")
    assert 94 <= p95 <= 96, f"P95={p95}, expected ~95"


def test_tracker_p99():
    tracker = CostTracker(db_path=Path(tempfile.mkdtemp()) / "cost.db")
    durs = list(range(1, 101))
    for d in durs:
        tracker.record(NodeCost(tool="precise", duration_seconds=float(d)))
    p99 = tracker.p99("precise")
    assert 98 <= p99 <= 100, f"P99={p99}, expected ~99"


def test_tracker_no_data_returns_zero():
    tracker = CostTracker(db_path=Path(tempfile.mkdtemp()) / "cost.db")
    assert tracker.p50("nonexistent") == 0.0
    assert tracker.p95("nonexistent") == 0.0


def test_tracker_mean():
    tracker = CostTracker(db_path=Path(tempfile.mkdtemp()) / "cost.db")
    for d in [1.0, 2.0, 3.0]:
        tracker.record(NodeCost(tool="avg_tool", duration_seconds=d))
    assert abs(tracker.mean("avg_tool") - 2.0) < 0.01


def test_tracker_report():
    tracker = CostTracker(db_path=Path(tempfile.mkdtemp()) / "cost.db")
    tracker.record(NodeCost(tool="t", duration_seconds=0.5))
    report = tracker.report()
    assert "t" in report
    assert report["t"]["count"] == 1
    assert abs(report["t"]["max"] - 0.5) < 0.01


def test_scheduler_orders_by_cost():
    tracker = CostTracker(db_path=Path(tempfile.mkdtemp()) / "cost.db")
    # Seed data: cheap_tool = 0.1s, expensive_tool = 2.0s
    tracker.record(NodeCost(tool="cheap_tool", duration_seconds=0.1))
    tracker.record(NodeCost(tool="expensive_tool", duration_seconds=2.0))
    scheduler = CostAwareScheduler(tracker)

    nodes = [
        PlanNode(id="exp", tool="expensive_tool"),
        PlanNode(id="cheap", tool="cheap_tool"),
    ]
    ordered = scheduler.schedule(nodes)
    assert ordered[0].id == "cheap"
    assert ordered[1].id == "exp"


def test_scheduler_tie_breaks_by_id():
    tracker = CostTracker(db_path=Path(tempfile.mkdtemp()) / "cost.db")
    tracker.record(NodeCost(tool="same", duration_seconds=0.5))
    scheduler = CostAwareScheduler(tracker)
    nodes = [
        PlanNode(id="z", tool="same"),
        PlanNode(id="a", tool="same"),
    ]
    ordered = scheduler.schedule(nodes)
    # Same cost → sort by id: a before z
    assert ordered[0].id == "a"


def test_scheduler_no_data_fallback():
    tracker = CostTracker(db_path=Path(tempfile.mkdtemp()) / "cost.db")
    scheduler = CostAwareScheduler(tracker)
    nodes = [
        PlanNode(id="b", tool="unknown"),
        PlanNode(id="a", tool="unknown"),
    ]
    ordered = scheduler.schedule(nodes)
    # No data → both return 1.0 → sort by id
    assert ordered[0].id == "a"


def test_estimate_cost_fallback():
    tracker = CostTracker(db_path=Path(tempfile.mkdtemp()) / "cost.db")
    node = PlanNode(id="n", tool="unseen")
    assert tracker.estimate_cost(node) == 1.0
