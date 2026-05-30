"""Tests for 3.4.5.2 — CodeGraph Drift Detector.

Verifies metrics computation, snapshot building, drift detection,
storage, and the full orchestration pipeline.
"""

import os
import sys
import tempfile
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.codegraph import (
    CodeGraph,
    CodeGraphDriftDetector,
    DriftDetector,
    DriftStore,
    Edge,
    EdgeType,
    Node,
    NodeType,
    build_codegraph,
    build_snapshot,
)
from core.codegraph.drift.metrics import (
    compute_coupling_delta,
    compute_entropy,
    compute_risk_delta,
)


# ── Metrics Tests ─────────────────────────────────────────────────────────────

class TestMetrics:

    def test_coupling_delta_positive(self):
        assert compute_coupling_delta(0.3, 0.7) == pytest.approx(0.4)

    def test_coupling_delta_negative(self):
        assert compute_coupling_delta(0.7, 0.3) == pytest.approx(-0.4)

    def test_coupling_delta_zero(self):
        assert compute_coupling_delta(0.5, 0.5) == 0.0

    def test_risk_delta(self):
        assert compute_risk_delta(0.1, 0.5) == 0.4

    def test_entropy_single_node(self):
        assert compute_entropy(edges=0, nodes=1) == 0.0

    def test_entropy_zero_nodes(self):
        assert compute_entropy(edges=0, nodes=0) == 0.0

    def test_entropy_increases_with_edges(self):
        e1 = compute_entropy(edges=10, nodes=5)
        e2 = compute_entropy(edges=20, nodes=5)
        assert e2 > e1

    def test_entropy_decreases_with_more_nodes(self):
        e1 = compute_entropy(edges=10, nodes=5)
        e2 = compute_entropy(edges=10, nodes=10)
        assert e2 < e1


# ── Snapshot Tests ────────────────────────────────────────────────────────────

class TestSnapshot:

    @pytest.fixture
    def sample_graph(self):
        graph = CodeGraph()
        graph.add_node(Node(id="n1", type=NodeType.FILE, name="a.py", path="core/a.py"))
        graph.add_node(Node(id="n2", type=NodeType.FILE, name="b.py", path="core/b.py"))
        graph.add_edge(Edge(from_id="n1", to_id="n2", type=EdgeType.DEPENDS_ON))
        return graph

    def test_build_snapshot(self, sample_graph):
        snap = build_snapshot(sample_graph, version="v1", metadata={"timestamp": 1000.0})
        assert snap["version"] == "v1"
        assert snap["node_count"] == 2
        assert snap["edge_count"] == 1
        assert snap["dependency_entropy"] > 0
        assert snap["timestamp"] == 1000.0

    def test_snapshot_without_metadata(self, sample_graph):
        snap = build_snapshot(sample_graph, version="v2")
        assert snap["timestamp"] == 0.0
        assert snap["coupling_score"] == 0.0


# ── DriftStore Tests ──────────────────────────────────────────────────────────

class TestDriftStore:

    @pytest.fixture
    def temp_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = DriftStore(base_path=os.path.join(tmp, "drift"))
            yield store

    def test_save_and_load(self, temp_store):
        snap = {"version": "v1", "coupling_score": 0.5, "node_count": 10}
        temp_store.save(snap)
        loaded = temp_store.load("v1")
        assert loaded is not None
        assert loaded["coupling_score"] == 0.5

    def test_load_missing(self, temp_store):
        assert temp_store.load("nonexistent") is None

    def test_list_versions(self, temp_store):
        temp_store.save({"version": "v1"})
        temp_store.save({"version": "v2"})
        versions = temp_store.list_versions()
        assert "v1" in versions
        assert "v2" in versions

    def test_latest(self, temp_store):
        temp_store.save({"version": "v1"})
        temp_store.save({"version": "v2"})
        latest = temp_store.latest()
        assert latest is not None
        assert latest["version"] == "v2"

    def test_latest_empty(self, temp_store):
        assert temp_store.latest() is None

    def test_clear(self, temp_store):
        temp_store.save({"version": "v1"})
        temp_store.save({"version": "v2"})
        temp_store.clear()
        assert temp_store.list_versions() == []


# ── DriftDetector Tests ───────────────────────────────────────────────────────

class TestDriftDetector:

    @pytest.fixture
    def detector(self):
        return DriftDetector()

    def test_detect_no_change(self, detector):
        snap = {"version": "v1", "coupling_score": 0.5, "risk_score": 0.3,
                "dependency_entropy": 0.7}
        report = detector.detect(snap, snap)
        assert report["coupling_delta"] == 0.0
        assert report["risk_delta"] == 0.0
        assert report["entropy_delta"] == 0.0
        assert report["severity"] == "LOW"

    def test_detect_coupling_increase(self, detector):
        old_snap = {"version": "v1", "coupling_score": 0.3, "risk_score": 0.2,
                    "dependency_entropy": 0.5}
        new_snap = {"version": "v2", "coupling_score": 0.7, "risk_score": 0.2,
                    "dependency_entropy": 0.5}
        report = detector.detect(old_snap, new_snap)
        assert report["coupling_delta"] == 0.4
        assert "COUPLING_DEGRADATION" in report["violations"]

    def test_detect_risk_increase(self, detector):
        old_snap = {"version": "v1", "coupling_score": 0.3, "risk_score": 0.1,
                    "dependency_entropy": 0.5}
        new_snap = {"version": "v2", "coupling_score": 0.3, "risk_score": 0.5,
                    "dependency_entropy": 0.5}
        report = detector.detect(old_snap, new_snap)
        assert report["risk_delta"] == 0.4
        assert "RISK_INCREASE" in report["violations"]

    def test_severity_classification(self, detector):
        # CRITICAL: sum > 0.5
        old = {"version": "v1", "coupling_score": 0.0, "risk_score": 0.0,
               "dependency_entropy": 0.0}
        new = {"version": "v2", "coupling_score": 0.6, "risk_score": 0.0,
               "dependency_entropy": 0.0}
        assert detector.detect(old, new)["severity"] == "CRITICAL"

        # HIGH: sum > 0.25
        new2 = {"version": "v3", "coupling_score": 0.3, "risk_score": 0.0,
                "dependency_entropy": 0.0}
        assert detector.detect(old, new2)["severity"] == "HIGH"

        # MEDIUM: sum > 0.1
        new3 = {"version": "v4", "coupling_score": 0.15, "risk_score": 0.0,
                "dependency_entropy": 0.0}
        assert detector.detect(old, new3)["severity"] == "MEDIUM"

        # LOW: sum <= 0.1
        new4 = {"version": "v5", "coupling_score": 0.05, "risk_score": 0.0,
                "dependency_entropy": 0.0}
        assert detector.detect(old, new4)["severity"] == "LOW"

    def test_versions_in_report(self, detector):
        old = {"version": "abc123", "coupling_score": 0.5, "risk_score": 0.3,
               "dependency_entropy": 0.7}
        new = {"version": "def456", "coupling_score": 0.6, "risk_score": 0.4,
               "dependency_entropy": 0.8}
        report = detector.detect(old, new)
        assert report["from_version"] == "abc123"
        assert report["to_version"] == "def456"


# ── CodeGraphDriftDetector Orchestration Tests ───────────────────────────────

class TestCodeGraphDriftDetector:

    @pytest.fixture
    def setup(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = DriftStore(base_path=os.path.join(tmp, "drift"))
            detector = DriftDetector()
            orchestrator = CodeGraphDriftDetector(store=store, detector=detector)
            yield store, detector, orchestrator

    def test_run_with_existing_previous(self, setup):
        store, _, orchestrator = setup
        store.save({"version": "v1", "coupling_score": 0.3, "risk_score": 0.2,
                    "dependency_entropy": 0.5})
        new_snap = {"version": "v2", "coupling_score": 0.6, "risk_score": 0.2,
                    "dependency_entropy": 0.5}
        report = orchestrator.run("v1", new_snap)
        assert report is not None
        assert report["coupling_delta"] == 0.3

    def test_run_without_previous_returns_none(self, setup):
        _, _, orchestrator = setup
        new_snap = {"version": "v1", "coupling_score": 0.5, "risk_score": 0.3,
                    "dependency_entropy": 0.7}
        report = orchestrator.run("nonexistent", new_snap)
        assert report is None

    def test_run_persists_new_snapshot(self, setup):
        store, _, orchestrator = setup
        store.save({"version": "v1", "coupling_score": 0.3, "risk_score": 0.2,
                    "dependency_entropy": 0.5})
        new_snap = {"version": "v2", "coupling_score": 0.5, "risk_score": 0.3,
                    "dependency_entropy": 0.6}
        orchestrator.run("v1", new_snap)
        loaded = store.load("v2")
        assert loaded is not None
        assert loaded["coupling_score"] == 0.5

    def test_integration_with_build_snapshot(self, setup):
        store, _, orchestrator = setup
        # Save initial snapshot
        graph_v1 = CodeGraph()
        graph_v1.add_node(Node(id="n1", type=NodeType.FILE, name="a.py", path="core/a.py"))
        snap_v1 = build_snapshot(graph_v1, version="v1", metadata={"timestamp": 1000.0})
        store.save(snap_v1)

        # Build new graph with more coupling
        graph_v2 = CodeGraph()
        graph_v2.add_node(Node(id="n1", type=NodeType.FILE, name="a.py", path="core/a.py"))
        graph_v2.add_node(Node(id="n2", type=NodeType.FILE, name="b.py", path="core/b.py"))
        graph_v2.add_edge(Edge(from_id="n1", to_id="n2", type=EdgeType.DEPENDS_ON))
        snap_v2 = build_snapshot(graph_v2, version="v2", metadata={"timestamp": 2000.0})

        report = orchestrator.run("v1", snap_v2)
        assert report is not None
        assert report["severity"] in ("LOW", "MEDIUM", "HIGH", "CRITICAL")
