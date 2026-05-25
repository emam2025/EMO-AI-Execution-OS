"""Phase I3 — Recovery Trace ID Propagation Tests.  # LAW-5 LAW-8 LAW-12

Tests that recovery_trace_id is correctly generated and propagated across
I2 → I3 → I1 → F2 → F4 layers, never lost between reliability operations.

Ref: Canon LAW 5 (Observability), LAW 8 (Recoverability), LAW 12 (Traceability)
Ref: artifacts/design/i3/04_integration_blueprint.md §3
"""

from __future__ import annotations

import pytest

from core.runtime.reliability.trace_correlator import RecoveryTraceCorrelator
from core.runtime.reliability.failover_orchestrator import FailoverOrchestrator
from core.runtime.reliability.disaster_recovery import DisasterRecovery
from core.runtime.reliability.rolling_update_manager import RollingUpdateManager
from core.runtime.reliability.runtime_migrator import RuntimeMigrator
from core.runtime.event_bus import InMemoryEventBus


@pytest.fixture
def correlator() -> RecoveryTraceCorrelator:
    return RecoveryTraceCorrelator()


@pytest.fixture
def event_bus() -> InMemoryEventBus:
    return InMemoryEventBus()


@pytest.fixture
def failover(event_bus: InMemoryEventBus) -> FailoverOrchestrator:
    return FailoverOrchestrator(event_bus=event_bus)


@pytest.fixture
def dr() -> DisasterRecovery:
    return DisasterRecovery()


@pytest.fixture
def updater() -> RollingUpdateManager:
    return RollingUpdateManager()


@pytest.fixture
def migrator() -> RuntimeMigrator:
    return RuntimeMigrator()


@pytest.fixture
def recovery_trace_id(correlator: RecoveryTraceCorrelator) -> str:
    return correlator.generate_recovery_trace_id("data_abc123", "integration")


# ── TestTraceIdGeneration ────────────────────────────────────────────────────


class TestTraceIdGeneration:
    def test_generates_valid_format(self, correlator: RecoveryTraceCorrelator):
        tid = correlator.generate_recovery_trace_id("data_abc", "failover")
        assert tid.startswith("rec_")
        assert len(tid) > 10

    def test_different_operations_different_ids(self, correlator: RecoveryTraceCorrelator):
        t1 = correlator.generate_recovery_trace_id("data_abc", "failover")
        t2 = correlator.generate_recovery_trace_id("data_abc", "dr")
        assert t1 != t2

    def test_different_data_ids_different(self, correlator: RecoveryTraceCorrelator):
        t1 = correlator.generate_recovery_trace_id("data_a", "failover")
        t2 = correlator.generate_recovery_trace_id("data_b", "failover")
        assert t1 != t2

    def test_uniqueness(self, correlator: RecoveryTraceCorrelator):
        ids = {correlator.generate_recovery_trace_id("data_x", "op") for _ in range(10)}
        assert len(ids) == 10


# ── TestTracePropagation ─────────────────────────────────────────────────────


class TestTracePropagation:
    def test_propagates_to_failover(self, correlator: RecoveryTraceCorrelator, recovery_trace_id: str):
        result = correlator.propagate_to_failover(recovery_trace_id, "fail_001")
        assert result["target_layer"] == "i3_failover"
        assert correlator.correlation_for(recovery_trace_id, "i3_failover") == "fail_001"

    def test_propagates_to_dr(self, correlator: RecoveryTraceCorrelator, recovery_trace_id: str):
        result = correlator.propagate_to_dr(recovery_trace_id, "rp_001")
        assert result["target_layer"] == "i3_disaster_recovery"

    def test_propagates_to_rolling_update(self, correlator: RecoveryTraceCorrelator, recovery_trace_id: str):
        result = correlator.propagate_to_rolling_update(recovery_trace_id, "dep_001")
        assert result["target_layer"] == "i3_rolling_update"

    def test_propagates_to_migration(self, correlator: RecoveryTraceCorrelator, recovery_trace_id: str):
        result = correlator.propagate_to_migration(recovery_trace_id, "mig_001")
        assert result["target_layer"] == "i3_migration"

    def test_propagates_to_i1(self, correlator: RecoveryTraceCorrelator, recovery_trace_id: str):
        result = correlator.propagate_to_i1(recovery_trace_id, "infra_001")
        assert result["target_layer"] == "i1_infra"

    def test_propagates_to_i2(self, correlator: RecoveryTraceCorrelator, recovery_trace_id: str):
        result = correlator.propagate_to_i2(recovery_trace_id, "data_001")
        assert result["target_layer"] == "i2_data"

    def test_propagates_to_f2_and_f4(self, correlator: RecoveryTraceCorrelator, recovery_trace_id: str):
        correlator.propagate_to_f2(recovery_trace_id, "dep_001")
        correlator.propagate_to_f4(recovery_trace_id)
        assert correlator.correlation_for(recovery_trace_id, "f2_control_plane") == "dep_001"
        assert "f4_observability" in correlator.trace_chain(recovery_trace_id).get("layers", {})


# ── TestEndToEndPropagation ──────────────────────────────────────────────────


class TestEndToEndPropagation:
    def test_failover_with_trace(self, failover: FailoverOrchestrator, correlator: RecoveryTraceCorrelator):
        tid = correlator.generate_recovery_trace_id("data_e2e", "failover")
        result = failover.trigger_failover("cluster_prod", "node_05", "degraded", tid)
        correlator.propagate_to_failover(tid, result.get("failover_id", ""))
        assert correlator.correlation_for(tid, "i3_failover")

    def test_dr_with_trace(self, dr: DisasterRecovery, correlator: RecoveryTraceCorrelator):
        tid = correlator.generate_recovery_trace_id("data_e2e", "dr")
        rp = dr.capture_recovery_point({"state": "ok"}, 100, {"node_id": "n1"}, tid)
        correlator.propagate_to_dr(tid, rp["recovery_point_id"])
        assert correlator.correlation_for(tid, "i3_disaster_recovery")

    def test_update_with_trace(self, updater: RollingUpdateManager, correlator: RecoveryTraceCorrelator):
        tid = correlator.generate_recovery_trace_id("data_e2e", "update")
        result = updater.prepare_canary("v2.0", 10.0, {"schema_version": "1"}, tid)
        correlator.propagate_to_rolling_update(tid, result["deployment_id"])
        assert correlator.correlation_for(tid, "i3_rolling_update")

    def test_migration_with_trace(self, migrator: RuntimeMigrator, correlator: RecoveryTraceCorrelator):
        tid = correlator.generate_recovery_trace_id("data_e2e", "migrate")
        result = migrator.dry_run_migration("sqlite", "postgresql",
                                             {"schema_version": "1", "api_version": "1",
                                              "data_format": "json", "protocol": "v1"}, tid)
        correlator.propagate_to_migration(tid, result["migration_id"])
        assert correlator.correlation_for(tid, "i3_migration")

    def test_full_pipeline(self, correlator: RecoveryTraceCorrelator):
        """I2 → I3 → I1 → F2 → F4 full trace."""
        data_tid = "data_pipeline"
        tid = correlator.generate_recovery_trace_id(data_tid, "pipeline")
        correlator.propagate_to_i2(tid, data_tid)
        correlator.propagate_to_failover(tid, "fail_pipeline")
        correlator.propagate_to_dr(tid, "rp_pipeline")
        correlator.propagate_to_rolling_update(tid, "dep_pipeline")
        correlator.propagate_to_i1(tid, "infra_pipeline")
        correlator.propagate_to_f2(tid, "res_pipeline")
        correlator.propagate_to_f4(tid)

        chain = correlator.trace_chain(tid)
        assert len(chain["layers"]) == 7
        assert "i2_data" in chain["layers"]
        assert "i3_failover" in chain["layers"]
        assert "i3_disaster_recovery" in chain["layers"]
        assert "i3_rolling_update" in chain["layers"]
        assert "i1_infra" in chain["layers"]
        assert "f2_control_plane" in chain["layers"]
        assert "f4_observability" in chain["layers"]

    def test_resolve_data_trace_id(self, correlator: RecoveryTraceCorrelator):
        tid = correlator.generate_recovery_trace_id("data_resolve", "test")
        correlator.propagate_to_i2(tid, "data_resolve")
        resolved = correlator.resolve_data_trace_id(tid)
        assert resolved == "data_resolve"


# ── TestCorrelationResolution ────────────────────────────────────────────────


class TestCorrelationResolution:
    def test_trace_chain_empty_for_unknown(self, correlator: RecoveryTraceCorrelator):
        assert correlator.trace_chain("unknown") == {}

    def test_reset_clears_all(self, correlator: RecoveryTraceCorrelator):
        tid = correlator.generate_recovery_trace_id("data_x", "test")
        correlator.propagate_to_f2(tid, "dep")
        assert len(correlator.all_traces()) > 0
        correlator.reset()
        assert len(correlator.all_traces()) == 0

    def test_trace_chain_returns_layers(self, correlator: RecoveryTraceCorrelator):
        tid = correlator.generate_recovery_trace_id("data_y", "test")
        correlator.propagate_to_failover(tid, "fail_001")
        correlator.propagate_to_f4(tid)
        chain = correlator.trace_chain(tid)
        assert "i3_failover" in chain["layers"]
        assert "f4_observability" in chain["layers"]
