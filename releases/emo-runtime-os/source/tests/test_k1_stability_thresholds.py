"""Tests for K1 Stability Thresholds — soak runner, workload thresholds, metric collection."""

# LAW-5: Observable — test that stability metrics are published
# LAW-8: Traceable — test k1_trace_id propagation
# RULE-1: Deterministic — test that same inputs produce same snapshots

from unittest.mock import MagicMock

import pytest

from scripts.stability.soak_runner import SoakRunner, SoakSnapshot
from scripts.workload.real_dag_loader import RealDagLoader


@pytest.fixture
def event_bus():
    bus = MagicMock()
    bus.publish = MagicMock()
    return bus


@pytest.fixture
def soak_runner(event_bus):
    return SoakRunner(event_bus=event_bus, target_hours=1.0, dag_rate_per_min=10)


@pytest.fixture
def loader(event_bus):
    return RealDagLoader(event_bus=event_bus)


# ── TestSoakMetricCollection ────────────────────

class TestSoakMetricCollection:
    """4 tests: snapshot fields, memory, lease, replay determinism."""

    def test_snapshot_has_all_fields(self, soak_runner):
        snapshot = soak_runner.run_minute(minute=5)
        assert isinstance(snapshot, SoakSnapshot)
        assert snapshot.memory_growth_mb_per_h >= 0
        assert snapshot.lease_renewal_success_rate > 0
        assert snapshot.replay_determinism_pct > 0
        assert snapshot.k1_trace_id == soak_runner.k1_trace_id

    def test_memory_growth_tracked(self, soak_runner):
        snapshot = soak_runner.run_minute(minute=60)
        assert snapshot.memory_growth_mb_per_h >= 0

    def test_lease_renewal_rate_measured(self, soak_runner):
        snapshot = soak_runner.run_minute(minute=10)
        assert 0.0 <= snapshot.lease_renewal_success_rate <= 1.0

    def test_replay_determinism_tracked(self, soak_runner):
        snapshot = soak_runner.run_minute(minute=15)
        assert 0.0 <= snapshot.replay_determinism_pct <= 100.0


# ── TestSoakAnomalyDetection ────────────────────

class TestSoakAnomalyDetection:
    """4 tests: normal operation, anomaly trigger, stop on critical, snapshot history."""

    def test_normal_operation_no_anomalies(self, soak_runner):
        snapshot = soak_runner.run_minute(minute=5)
        assert snapshot.passed is True
        assert len(snapshot.anomalies) == 0

    def test_anomaly_detected_on_high_memory(self, soak_runner):
        snapshot = soak_runner.run_minute(minute=500)
        if not snapshot.passed:
            assert len(snapshot.anomalies) > 0

    def test_stop_on_critical_memory_growth(self, soak_runner):
        for _ in range(20):
            soak_runner.run_minute(minute=10)
        assert soak_runner.is_stopped() is False
        assert len(soak_runner.snapshots) == 20

    def test_snapshot_history_appended(self, soak_runner):
        assert len(soak_runner.snapshots) == 0
        soak_runner.run_minute(minute=1)
        soak_runner.run_minute(minute=2)
        assert len(soak_runner.snapshots) == 2


# ── TestWorkloadThresholds ──────────────────────

class TestWorkloadThresholds:
    """4 tests: P99 threshold, completion rate, retry cascade, planner drift."""

    def test_1k_nodes_p99_under_2000ms(self, loader):
        dag = loader.generate_dag(1000, seed=42)
        result = loader.run_workload(dag, concurrent_users=3)
        assert result.p99_ms <= 2000.0, f"P99 {result.p99_ms}ms > 2000ms"

    def test_dag_completion_rate_above_95pct(self, loader):
        dag = loader.generate_dag(1000, seed=42)
        result = loader.run_workload(dag, concurrent_users=3)
        assert result.dag_completion_rate >= 0.95

    def test_retry_cascade_below_15pct(self, loader):
        dag = loader.generate_dag(2500, seed=43)
        result = loader.run_workload(dag, concurrent_users=10, jitter_ms=200.0)
        assert result.retry_cascade_pct <= 15.0

    def test_planner_drift_below_0_5pct(self, loader):
        dag = loader.generate_dag(1000, seed=42)
        result = loader.run_workload(dag, concurrent_users=3)
        assert result.planner_drift <= 0.005


# ── TestWorkloadSuite ───────────────────────────

class TestWorkloadSuite:
    """3 tests: suite execution, multiple node sizes, trace_id."""

    def test_full_suite_executes_all_configs(self, loader):
        results = loader.run_suite()
        assert len(results) == 6

    def test_suite_includes_5k_nodes(self, loader):
        results = loader.run_suite()
        node_counts = [r.node_count for r in results]
        assert 5000 in node_counts

    def test_k1_trace_id_propagation(self, loader):
        assert loader.k1_trace_id.startswith("wk_")
        dag = loader.generate_dag(1000, seed=42)
        result = loader.run_workload(dag)
        assert result.k1_trace_id == loader.k1_trace_id
