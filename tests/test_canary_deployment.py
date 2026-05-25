"""Tests for Canary Deployment — metrics, replay integrity, isolation, rollback."""

# LAW-5: Observable — test metric collection accuracy
# LAW-8: Traceable — test that every check carries canary_trace_id
# LAW-11: No Global State — test that each user session is isolated
# LAW-12: Traceable — test full trace chain integrity
# RULE-1: Deterministic — test that same inputs produce same outputs

import time
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest

from core.observability.canary_metrics import (
    CanaryMetricsCollector,
    CanaryMetricsSnapshot,
)
from core.recovery.canary_replay import (
    CanaryReplayAuditor,
    DeterminismAuditResult,
)
from scripts.canary.canary_config import (
    DEFAULT_CANARY_CONFIG,
    CanaryConfig,
    CanaryUser,
    ResourceLimits,
    TracingFlags,
)
from scripts.canary.canary_launcher import CanaryLauncher
from scripts.canary.canary_observer import (
    AnomalySeverity,
    CanaryObserver,
)


# ── Fixtures ────────────────────────────────────────────────────

@pytest.fixture
def event_bus():
    bus = MagicMock()
    bus.publish = MagicMock()
    return bus


@pytest.fixture
def canary_launcher(event_bus):
    return CanaryLauncher(config=DEFAULT_CANARY_CONFIG, event_bus=event_bus)


@pytest.fixture
def metrics_collector(event_bus):
    return CanaryMetricsCollector(
        event_bus=event_bus,
        canary_trace_id="cny_test_trace_001",
    )


@pytest.fixture
def replay_auditor(event_bus):
    return CanaryReplayAuditor(
        event_bus=event_bus,
        canary_trace_id="cny_test_trace_002",
    )


@pytest.fixture
def observer(event_bus):
    return CanaryObserver(
        event_bus=event_bus,
        canary_trace_id="cny_test_observer_001",
    )


# ── TestMetricCollectionAccuracy ────────────────────────────────

class TestMetricCollectionAccuracy:
    """4 tests: default values, custom values, trace_id integrity, snapshot history."""

    def test_collect_default_snapshot_has_all_fields(self, metrics_collector):
        snapshot = metrics_collector.collect_snapshot()
        assert isinstance(snapshot, CanaryMetricsSnapshot)
        assert snapshot.runtime_p50_ms == 45.0
        assert snapshot.runtime_p99_ms == 180.0
        assert snapshot.runtime_dag_completion_rate == 0.995
        assert snapshot.runtime_replay_determinism_pct == 0.998
        assert snapshot.distributed_scheduler_fairness_score == 0.92
        assert snapshot.resource_memory_growth_per_hour == 0.012
        assert snapshot.ai_planner_determinism_drift == 0.003
        assert snapshot.ai_feedback_calibration_stability == 0.97

    def test_collect_custom_values_override_defaults(self, metrics_collector):
        snapshot = metrics_collector.collect_snapshot(
            p99_ms=450.0,
            replay_determinism_pct=0.985,
            memory_growth_per_hour=0.04,
        )
        assert snapshot.runtime_p99_ms == 450.0
        assert snapshot.runtime_replay_determinism_pct == 0.985
        assert snapshot.resource_memory_growth_per_hour == 0.04

    def test_canary_trace_id_integrity(self, metrics_collector):
        snapshot = metrics_collector.collect_snapshot()
        assert snapshot.canary_trace_id == metrics_collector.canary_trace_id
        assert snapshot.canary_trace_id.startswith("cny_")

    def test_snapshot_appended_to_history(self, metrics_collector):
        assert len(metrics_collector.get_history()) == 0
        metrics_collector.collect_snapshot()
        metrics_collector.collect_snapshot(p99_ms=200.0)
        assert len(metrics_collector.get_history()) == 2


# ── TestReplayIntegrityUnderLoad ────────────────────────────────

class TestReplayIntegrityUnderLoad:
    """4 tests: integrity match, integrity breach, checkpoint validation, determinism audit."""

    def test_replay_integrity_match(self, replay_auditor):
        result = replay_auditor.replay_integrity_check(
            session_id="session-001",
            original_trace_hash="abc123",
            replayed_trace_hash="abc123",
        )
        assert result.integrity_match is True
        assert result.session_id == "session-001"
        assert "Integrity OK" in result.details

    def test_replay_integrity_breach_detected(self, replay_auditor):
        result = replay_auditor.replay_integrity_check(
            session_id="session-001",
            original_trace_hash="abc123",
            replayed_trace_hash="def456",
        )
        assert result.integrity_match is False
        assert "INTEGRITY BREACH" in result.details

    def test_checkpoint_validation_consistent(self, replay_auditor):
        state = {"dag_version": "v1", "worker_count": 3, "lease_table": {}}
        result = replay_auditor.checkpoint_validation(
            session_id="session-001",
            pre_run_state=state,
            post_run_state=state,
        )
        assert result.pre_run_consistency is True
        assert result.post_run_consistency is True

    def test_checkpoint_validation_inconsistent(self, replay_auditor):
        good = {"dag_version": "v1", "worker_count": 3, "lease_table": {}}
        bad = {"dag_version": "v1"}
        result = replay_auditor.checkpoint_validation(
            session_id="session-001",
            pre_run_state=good,
            post_run_state=bad,
        )
        assert result.pre_run_consistency is True
        assert result.post_run_consistency is False

    def test_determinism_audit_3_runs_all_match(self, replay_auditor):
        runs = [
            {"tasks": ["a", "b", "c"], "execution_order": ["a", "b", "c"],
             "timing_ms": {"a": 10, "b": 20, "c": 30, "total": 60}},
            {"tasks": ["a", "b", "c"], "execution_order": ["a", "b", "c"],
             "timing_ms": {"a": 11, "b": 21, "c": 31, "total": 63}},
            {"tasks": ["a", "b", "c"], "execution_order": ["a", "b", "c"],
             "timing_ms": {"a": 9, "b": 19, "c": 29, "total": 57}},
        ]
        result = replay_auditor.determinism_audit("dag-001", runs)
        assert result.run_count == 3
        assert result.all_outputs_match is True
        assert result.all_orders_match is True
        assert result.timing_variance_pct < 10.0

    def test_determinism_audit_detects_output_mismatch(self, replay_auditor):
        runs = [
            {"tasks": ["a", "b", "c"], "execution_order": ["a", "b", "c"],
             "timing_ms": {"total": 60}},
            {"tasks": ["a", "b", "d"], "execution_order": ["a", "b", "d"],
             "timing_ms": {"total": 60}},
        ]
        result = replay_auditor.determinism_audit("dag-001", runs)
        assert result.all_outputs_match is False


# ── TestIsolationBoundaryEnforcement ────────────────────────────

class TestIsolationBoundaryEnforcement:
    """4 tests: 3 users isolated, unknown user rejected, separate trace IDs, worker pool labels."""

    def test_three_users_defined(self):
        assert len(DEFAULT_CANARY_CONFIG.users) == 3
        user_ids = {u.user_id for u in DEFAULT_CANARY_CONFIG.users}
        assert user_ids == {"user-alpha", "user-beta", "user-gamma"}

    def test_each_user_has_isolated_repo(self):
        repos = {u.user_id: u.isolated_repo_path for u in DEFAULT_CANARY_CONFIG.users}
        assert len(set(repos.values())) == 3

    def test_each_user_has_dedicated_worker_pool(self):
        pools = {u.user_id: u.worker_pool_label for u in DEFAULT_CANARY_CONFIG.users}
        assert len(set(pools.values())) == 3

    def test_each_user_has_bounded_resource_limits(self):
        for user in DEFAULT_CANARY_CONFIG.users:
            limits = user.resource_limits
            assert limits.cpu_cores > 0
            assert limits.memory_mb > 0
            assert limits.max_concurrent_dags > 0
            assert limits.max_retries >= 0
            assert limits.timeout_sec > 0

    def test_launch_unknown_user_raises_error(self, canary_launcher):
        with pytest.raises(ValueError, match="Unknown canary user"):
            canary_launcher.launch_session("user-unknown")

    def test_each_session_gets_unique_canary_trace_id(self, canary_launcher):
        obs_a = canary_launcher.launch_session("user-alpha")
        obs_b = canary_launcher.launch_session("user-beta")
        assert obs_a.canary_trace_id != obs_b.canary_trace_id
        assert obs_a.canary_trace_id.startswith("cny_")
        assert obs_b.canary_trace_id.startswith("cny_")


# ── TestRollbackTriggerConditions ───────────────────────────────

class TestRollbackTriggerConditions:
    """3 tests: P99 breach triggers FATAL, replay drift triggers FATAL, memory leak triggers FATAL."""

    def test_p99_breach_500ms_triggers_fatal_alert(self, observer):
        snapshot = observer.collect_metrics("user-alpha")
        # Simulate P99 breach by replacing snapshot
        from dataclasses import replace
        breached = replace(snapshot, p99_ms=600.0)
        report = observer.detect_anomaly(breached)
        assert report is not None
        assert report.severity == AnomalySeverity.FATAL
        assert report.metric_name == "p99_ms"
        assert report.observed_value == 600.0

    def test_replay_determinism_below_98pct_triggers_fatal_alert(self, observer):
        snapshot = observer.collect_metrics("user-beta")
        from dataclasses import replace
        breached = replace(snapshot, replay_determinism_pct=0.95)
        report = observer.detect_anomaly(breached)
        assert report is not None
        assert report.severity == AnomalySeverity.FATAL
        assert report.metric_name == "replay_determinism_pct"

    def test_memory_growth_over_5pct_triggers_fatal_alert(self, observer):
        snapshot = observer.collect_metrics("user-gamma")
        from dataclasses import replace
        breached = replace(snapshot, memory_growth_per_hour=0.07)
        report = observer.detect_anomaly(breached)
        assert report is not None
        assert report.severity == AnomalySeverity.FATAL
        assert report.metric_name == "memory_growth_per_hour"

    def test_healthy_metrics_no_alert(self, observer):
        snapshot = observer.collect_metrics("user-alpha")
        report = observer.detect_anomaly(snapshot)
        assert report is None

    def test_trigger_alert_publishes_to_event_bus(self, event_bus):
        observer = CanaryObserver(event_bus=event_bus, canary_trace_id="cny_test_003")
        snapshot = observer.collect_metrics("user-alpha")
        from dataclasses import replace
        breached = replace(snapshot, p99_ms=700.0)
        report = observer.detect_anomaly(breached)
        assert report is not None
        observer.trigger_alert(report)
        assert len(observer.get_alert_history()) == 1


# ── TestCanaryTracePropagation ──────────────────────────────────

class TestCanaryTracePropagation:
    """Tests LAW-12 canary_trace_id propagation across all layers."""

    def test_launcher_to_observer_trace_chain(self, canary_launcher):
        obs = canary_launcher.launch_session("user-alpha")
        assert obs.canary_trace_id.startswith("cny_")
        assert len(obs.canary_trace_id) >= 28

    def test_metrics_collector_trace_id(self, metrics_collector):
        snapshot = metrics_collector.collect_snapshot()
        assert snapshot.canary_trace_id == metrics_collector.canary_trace_id

    def test_replay_auditor_trace_id(self, replay_auditor):
        result = replay_auditor.replay_integrity_check(
            session_id="s1", original_trace_hash="a", replayed_trace_hash="a",
        )
        assert result.canary_trace_id == replay_auditor.canary_trace_id

    def test_strict_canary_mode_default(self):
        assert DEFAULT_CANARY_CONFIG.strict_canary_mode is True
