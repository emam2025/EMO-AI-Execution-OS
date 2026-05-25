"""Phase I3 — Reliability Integration Tests.  # LAW-3 LAW-8 LAW-20 LAW-21 LAW-22 RULE-1 RULE-3 RULE-4 RULE-5

Integration tests covering split-brain guard enforcement, recovery determinism,
trace correlation, rolling update safety, and event bus propagation.

Ref: Canon LAW 3, LAW 8, LAW 20, LAW 21, LAW 22
Ref: Canon RULE 1, RULE 3, RULE 4, RULE 5
Ref: artifacts/design/i3/04_integration_blueprint.md
"""

from __future__ import annotations

import pytest

from core.runtime.reliability.failover_orchestrator import FailoverOrchestrator
from core.runtime.reliability.disaster_recovery import DisasterRecovery
from core.runtime.reliability.rolling_update_manager import RollingUpdateManager
from core.runtime.reliability.runtime_migrator import RuntimeMigrator
from core.runtime.reliability.reliability_state_machine import ReliabilityStateMachine
from core.runtime.reliability.trace_correlator import RecoveryTraceCorrelator
from core.runtime.event_bus import InMemoryEventBus
from core.models.events import ExecutionEvent


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def event_bus() -> InMemoryEventBus:
    return InMemoryEventBus()


@pytest.fixture
def sm() -> ReliabilityStateMachine:
    return ReliabilityStateMachine()


@pytest.fixture
def correlator() -> RecoveryTraceCorrelator:
    return RecoveryTraceCorrelator()


@pytest.fixture
def failover(event_bus: InMemoryEventBus) -> FailoverOrchestrator:
    return FailoverOrchestrator(event_bus=event_bus, strict_reliability_mode=True)


@pytest.fixture
def dr() -> DisasterRecovery:
    return DisasterRecovery(strict_reliability_mode=True)


@pytest.fixture
def updater() -> RollingUpdateManager:
    return RollingUpdateManager(strict_reliability_mode=True)


@pytest.fixture
def migrator() -> RuntimeMigrator:
    return RuntimeMigrator(strict_reliability_mode=True)


# ── TestSplitBrainGuardEnforcement ───────────────────────────────────────────


class TestSplitBrainGuardEnforcement:
    def test_promote_requires_quorum_majority(self, failover: FailoverOrchestrator):
        with pytest.raises(RuntimeError, match="quorum"):
            failover.promote_replica("cluster_a", "node_02",
                                     quorum_votes=2, data_sync_lag_ms=100.0,
                                     recovery_trace_id="rec_test")

    def test_promote_blocks_excessive_sync_lag(self, failover: FailoverOrchestrator):
        with pytest.raises(RuntimeError, match="sync lag"):
            failover.promote_replica("cluster_a", "node_02",
                                     quorum_votes=4, data_sync_lag_ms=600.0,
                                     recovery_trace_id="rec_test")

    def test_promote_passes_valid_conditions(self, failover: FailoverOrchestrator):
        result = failover.promote_replica("cluster_a", "node_02",
                                          quorum_votes=4, data_sync_lag_ms=100.0,
                                          recovery_trace_id="rec_test")
        assert result["promoted"]
        assert result["new_leader_id"] == "node_02"

    def test_trigger_failover_blocks_lost_quorum(self, failover: FailoverOrchestrator):
        with pytest.raises(RuntimeError, match="quorum is lost"):
            failover.trigger_failover("cluster_a", "node_05",
                                      quorum_status="lost",
                                      recovery_trace_id="rec_test")

    def test_trigger_failover_passes_degraded_quorum(self, failover: FailoverOrchestrator):
        result = failover.trigger_failover("cluster_a", "node_05",
                                           quorum_status="degraded",
                                           recovery_trace_id="rec_test")
        assert result["failover_initiated"]


# ── TestRecoveryDeterminism ──────────────────────────────────────────────────


class TestRecoveryDeterminism:
    def test_same_snapshot_same_hash(self, dr: DisasterRecovery):
        snapshot = {"executions": [{"id": 1, "status": "completed"}]}
        rp1 = dr.capture_recovery_point(snapshot, 100, {"node_id": "n1"}, "rec_1")
        rp2 = dr.capture_recovery_point(snapshot, 100, {"node_id": "n1"}, "rec_2")
        assert rp1["state_hash"] == rp2["state_hash"]

    def test_different_snapshots_different_hashes(self, dr: DisasterRecovery):
        rp1 = dr.capture_recovery_point({"a": 1}, 100, {"node_id": "n1"}, "rec_1")
        rp2 = dr.capture_recovery_point({"a": 2}, 100, {"node_id": "n1"}, "rec_2")
        assert rp1["state_hash"] != rp2["state_hash"]

    def test_restore_requires_checksum_match(self, dr: DisasterRecovery):
        rp = dr.capture_recovery_point({"state": "ok"}, 100, {"node_id": "n1"}, "rec_1")
        with pytest.raises(RuntimeError, match="checksum"):
            dr.restore_from_backup(rp["recovery_point_id"], "loc", "bad_checksum", "rec_2")

    def test_restore_passes_valid_checksum(self, dr: DisasterRecovery):
        rp = dr.capture_recovery_point({"state": "ok"}, 100, {"node_id": "n1"}, "rec_1")
        result = dr.restore_from_backup(rp["recovery_point_id"], "loc",
                                        rp["checksum"], "rec_2")
        assert result["checksum_match"]


# ── TestTraceCorrelation ─────────────────────────────────────────────────────


class TestTraceCorrelation:
    def test_recovery_trace_id_flows_i2_to_i3(self, correlator: RecoveryTraceCorrelator):
        data_trace_id = "data_infra_001"
        tid = correlator.generate_recovery_trace_id(data_trace_id, "failover")
        correlator.propagate_to_i2(tid, data_trace_id)
        assert correlator.resolve_data_trace_id(tid) == data_trace_id

    def test_recovery_trace_id_flows_i3_to_f4(self, correlator: RecoveryTraceCorrelator):
        tid = correlator.generate_recovery_trace_id("data_x", "test")
        correlator.propagate_to_f4(tid)
        chain = correlator.trace_chain(tid)
        assert "f4_observability" in chain.get("layers", {})

    def test_full_chain_resolution(self, correlator: RecoveryTraceCorrelator):
        data_tid = "data_full"
        tid = correlator.generate_recovery_trace_id(data_tid, "pipeline")
        correlator.propagate_to_i2(tid, data_tid)
        correlator.propagate_to_failover(tid, "fail_001")
        correlator.propagate_to_i1(tid, "infra_001")
        correlator.propagate_to_f2(tid, "res_001")
        correlator.propagate_to_f4(tid)
        chain = correlator.trace_chain(tid)
        assert len(chain["layers"]) >= 5

    def test_data_trace_id_resolution(self, correlator: RecoveryTraceCorrelator):
        tid = correlator.generate_recovery_trace_id("data_resolve", "test")
        correlator.propagate_to_i2(tid, "data_resolve")
        assert correlator.resolve_data_trace_id(tid) == "data_resolve"


# ── TestRollingUpdateSafety ──────────────────────────────────────────────────


class TestRollingUpdateSafety:
    def test_canary_requires_compatibility_matrix(self, updater: RollingUpdateManager):
        with pytest.raises(RuntimeError, match="compatibility_matrix"):
            updater.prepare_canary("v2.0", 10.0, {}, "rec_test")

    def test_canary_blocks_invalid_percent(self, updater: RollingUpdateManager):
        with pytest.raises(ValueError, match="canary_percent"):
            updater.prepare_canary("v2.0", 0.0,
                                   {"schema_version": "1", "api_version": "1",
                                    "data_format": "json", "protocol": "v1"},
                                   "rec_test")

    def test_canary_passes(self, updater: RollingUpdateManager):
        result = updater.prepare_canary("v2.0", 10.0,
                                        {"schema_version": "1", "api_version": "1",
                                         "data_format": "json", "protocol": "v1"},
                                        "rec_test")
        assert result["canary_ready"]

    def test_roll_forward_blocks_degraded_cluster(self, updater: RollingUpdateManager):
        with pytest.raises(RuntimeError, match="degraded"):
            updater.roll_forward("v2.0", "rolling_update",
                                 {"healthy_nodes": 3, "degraded_nodes": 2},
                                 "rec_test")

    def test_roll_forward_passes_healthy(self, updater: RollingUpdateManager):
        result = updater.roll_forward("v2.0", "rolling_update",
                                      {"healthy_nodes": 5, "degraded_nodes": 0},
                                      "rec_test")
        assert result["rollout_started"]

    def test_roll_back_passes(self, updater: RollingUpdateManager):
        result = updater.roll_back("v2.0", "v1.0", "health_check_failure", "rec_test")
        assert result["rollback_initiated"]

    def test_monitor_health_detects_failures(self, updater: RollingUpdateManager):
        result = updater.monitor_health("dep_001",
                                        [{"healthy": True}, {"healthy": False}],
                                        "rec_test")
        assert not result["healthy"]
        assert result["checks_failed"] == 1


# ── TestMigrationDeterminism ─────────────────────────────────────────────────


class TestMigrationDeterminism:
    def test_dry_run_detects_incompatibility(self, migrator: RuntimeMigrator):
        with pytest.raises(RuntimeError, match="compatibility"):
            migrator.dry_run_migration("sqlite", "postgresql",
                                       {}, "rec_test")

    def test_dry_run_passes_valid(self, migrator: RuntimeMigrator):
        result = migrator.dry_run_migration("sqlite", "postgresql",
                                            {"schema_version": "1", "api_version": "1",
                                             "data_format": "json", "protocol": "v1"},
                                            "rec_test")
        assert result["dry_run_passed"]

    def test_switch_over_requires_valid_strategy(self, migrator: RuntimeMigrator):
        with pytest.raises(ValueError, match="switch_strategy"):
            migrator.switch_over("postgresql", "hash", "invalid", "rec_test")

    def test_switch_over_passes(self, migrator: RuntimeMigrator):
        result = migrator.switch_over("postgresql", "hash", "atomic", "rec_test")
        assert result["switch_completed"]

    def test_verify_post_migration(self, migrator: RuntimeMigrator):
        result = migrator.verify_post_migration("source_hash", "postgresql",
                                                 "expected", "rec_test")
        assert not result["verified"]  # hash won't match expected


# ── TestEventBusPropagation ──────────────────────────────────────────────────


class TestEventBusPropagation:
    def test_failover_emits_event(self, event_bus: InMemoryEventBus):
        fo = FailoverOrchestrator(event_bus=event_bus)
        fo.trigger_failover("cluster_a", "node_05", "degraded", "rec_test")
        events = event_bus.get_events("runtime.reliability.failover", limit=10)
        assert len(events) >= 1
        assert events[0].payload.get("action") == "FAILOVER_TRIGGERED"

    def test_isolate_node_emits_event(self, event_bus: InMemoryEventBus):
        fo = FailoverOrchestrator(event_bus=event_bus)
        fo.isolate_node("cluster_a", "node_05", "fence", "rec_test")
        events = event_bus.get_events("runtime.reliability.failover", limit=10)
        assert len(events) >= 1

    def test_promote_replica_emits_event(self, event_bus: InMemoryEventBus):
        fo = FailoverOrchestrator(event_bus=event_bus)
        fo.promote_replica("cluster_a", "node_02",
                           quorum_votes=4, data_sync_lag_ms=100.0,
                           recovery_trace_id="rec_test")
        events = event_bus.get_events("runtime.reliability.failover", limit=10)
        assert len(events) >= 1

    def test_event_payload_contains_trace_id(self, event_bus: InMemoryEventBus):
        fo = FailoverOrchestrator(event_bus=event_bus)
        fo.trigger_failover("cluster_a", "node_05", "degraded", "rec_abc123")
        events = event_bus.get_events("runtime.reliability.failover", limit=10)
        assert events[0].payload.get("recovery_trace_id") == "rec_abc123"
