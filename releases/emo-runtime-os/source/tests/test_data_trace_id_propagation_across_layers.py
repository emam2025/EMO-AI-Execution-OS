"""Phase I2 — Data Trace ID Propagation Tests.  # LAW-5 LAW-12

Tests that data_trace_id is correctly generated and propagated across
I1 → I2 → F2 → F4 layers, never lost between data operations.

Ref: Canon LAW 5 (Observability), LAW 12 (Traceability)
Ref: artifacts/design/i2/04_integration_blueprint.md §3
"""

from __future__ import annotations

import pytest

from core.runtime.data.trace_correlator import DataTraceCorrelator
from core.runtime.data.postgresql_manager import PostgreSQLManager
from core.runtime.data.distributed_log import DistributedLog
from core.runtime.data.runtime_analytics import RuntimeAnalytics
from core.runtime.data.data_migrator import DataMigrator
from core.runtime.data.acid_state_machine import ACIDStateMachine
from core.runtime.event_bus import InMemoryEventBus


@pytest.fixture
def correlator() -> DataTraceCorrelator:
    return DataTraceCorrelator()


@pytest.fixture
def event_bus() -> InMemoryEventBus:
    return InMemoryEventBus()


@pytest.fixture
def sm() -> ACIDStateMachine:
    return ACIDStateMachine()


@pytest.fixture
def pg(event_bus: InMemoryEventBus, sm: ACIDStateMachine) -> PostgreSQLManager:
    return PostgreSQLManager(event_bus=event_bus, state_machine=sm)


@pytest.fixture
def log(event_bus: InMemoryEventBus) -> DistributedLog:
    return DistributedLog(event_bus=event_bus)


@pytest.fixture
def analytics(event_bus: InMemoryEventBus) -> RuntimeAnalytics:
    return RuntimeAnalytics(event_bus=event_bus)


@pytest.fixture
def migrator(event_bus: InMemoryEventBus, sm: ACIDStateMachine) -> DataMigrator:
    return DataMigrator(event_bus=event_bus, state_machine=sm)


@pytest.fixture
def data_trace_id(correlator: DataTraceCorrelator) -> str:
    return correlator.generate_data_trace_id("infra_test_001", "integration")


# ── TestTraceIdGeneration ───────────────────────────────────────────────────


class TestTraceIdGeneration:
    def test_generates_valid_format(self, correlator: DataTraceCorrelator):
        tid = correlator.generate_data_trace_id("infra_abc", "migrate")
        assert tid.startswith("data_")
        assert len(tid) > 10

    def test_different_operations_different_ids(self, correlator: DataTraceCorrelator):
        t1 = correlator.generate_data_trace_id("infra_abc", "tx")
        t2 = correlator.generate_data_trace_id("infra_abc", "log")
        assert t1 != t2

    def test_different_infra_ids_different(self, correlator: DataTraceCorrelator):
        t1 = correlator.generate_data_trace_id("infra_a", "tx")
        t2 = correlator.generate_data_trace_id("infra_b", "tx")
        assert t1 != t2

    def test_uniqueness(self, correlator: DataTraceCorrelator):
        ids = {correlator.generate_data_trace_id("infra_x", "op") for _ in range(10)}
        assert len(ids) == 10


# ── TestTracePropagation ────────────────────────────────────────────────────


class TestTracePropagation:
    def test_propagates_to_postgres(self, correlator: DataTraceCorrelator, data_trace_id: str):
        result = correlator.propagate_to_postgres(data_trace_id, "tx_001")
        assert result["target_layer"] == "i2_postgresql"
        assert correlator.correlation_for(data_trace_id, "i2_postgresql") == "tx_001"

    def test_propagates_to_log(self, correlator: DataTraceCorrelator, data_trace_id: str):
        result = correlator.propagate_to_log(data_trace_id, "log_001")
        assert result["target_layer"] == "i2_distributed_log"

    def test_propagates_to_analytics(self, correlator: DataTraceCorrelator, data_trace_id: str):
        result = correlator.propagate_to_analytics(data_trace_id, "win_001")
        assert result["target_layer"] == "i2_analytics"

    def test_propagates_to_migration(self, correlator: DataTraceCorrelator, data_trace_id: str):
        result = correlator.propagate_to_migration(data_trace_id, "mig_001")
        assert result["target_layer"] == "i2_migration"

    def test_propagates_to_f2_and_f4(self, correlator: DataTraceCorrelator, data_trace_id: str):
        correlator.propagate_to_f2(data_trace_id, "dep_001")
        correlator.propagate_to_f4(data_trace_id)
        assert correlator.correlation_for(data_trace_id, "f2_control_plane") == "dep_001"
        assert "f4_observability" in correlator.trace_chain(data_trace_id).get("layers", {})


# ── TestEndToEndPropagation ─────────────────────────────────────────────────


class TestEndToEndPropagation:
    def test_pg_with_trace(self, pg: PostgreSQLManager, correlator: DataTraceCorrelator):
        tid = correlator.generate_data_trace_id("infra_e2e", "pg")
        result = pg.execute_tx([{"sql": "INSERT INTO test VALUES (1)", "rows": 1}],
                                "SERIALIZABLE", tid)
        assert "committed" in result
        correlator.propagate_to_postgres(tid, result.get("tx_id", ""))
        assert correlator.correlation_for(tid, "i2_postgresql")

    def test_log_with_trace(self, log: DistributedLog, correlator: DataTraceCorrelator):
        tid = correlator.generate_data_trace_id("infra_e2e", "log")
        result = log.append_entry("runtime.execution", {"action": "test"}, tid)
        assert result["entry_id"]
        correlator.propagate_to_log(tid, result["entry_id"])
        assert correlator.correlation_for(tid, "i2_distributed_log") == result["entry_id"]

    def test_analytics_with_trace(self, analytics: RuntimeAnalytics, correlator: DataTraceCorrelator):
        tid = correlator.generate_data_trace_id("infra_e2e", "analytics")
        result = analytics.compute_throughput("win_001", [{"value": 10.0}], tid)
        assert result["window_id"]
        correlator.propagate_to_analytics(tid, result["window_id"])

    def test_migration_with_trace(self, migrator: DataMigrator, correlator: DataTraceCorrelator):
        tid = correlator.generate_data_trace_id("infra_e2e", "migrate")
        result = migrator.extract_legacy_sqlite("/path/to/db", ["table1"], tid)
        assert result["extracted"]
        correlator.propagate_to_migration(tid, "mig_e2e")

    def test_full_pipeline(self, correlator: DataTraceCorrelator):
        """I1 → I2 → F2 → F4 full trace."""
        infra_tid = "infra_pipeline"
        tid = correlator.generate_data_trace_id(infra_tid, "pipeline")
        correlator.propagate_to_i1(tid, infra_tid)
        correlator.propagate_to_postgres(tid, "tx_pipeline")
        correlator.propagate_to_log(tid, "log_pipeline")
        correlator.propagate_to_analytics(tid, "win_pipeline")
        correlator.propagate_to_f2(tid, "dep_pipeline")
        correlator.propagate_to_f4(tid)

        chain = correlator.trace_chain(tid)
        assert len(chain["layers"]) == 6
        assert "i1_infra" in chain["layers"]
        assert "i2_postgresql" in chain["layers"]
        assert "i2_distributed_log" in chain["layers"]
        assert "i2_analytics" in chain["layers"]
        assert "f2_control_plane" in chain["layers"]
        assert "f4_observability" in chain["layers"]

    def test_resolve_infra_trace_id(self, correlator: DataTraceCorrelator):
        tid = correlator.generate_data_trace_id("infra_resolve", "test")
        correlator.propagate_to_i1(tid, "infra_resolve")
        resolved = correlator.resolve_infra_trace_id(tid)
        assert resolved == "infra_resolve"


# ── TestCorrelationResolution ───────────────────────────────────────────────


class TestCorrelationResolution:
    def test_trace_chain_empty_for_unknown(self, correlator: DataTraceCorrelator):
        assert correlator.trace_chain("unknown") == {}

    def test_reset_clears_all(self, correlator: DataTraceCorrelator):
        tid = correlator.generate_data_trace_id("infra_x", "test")
        correlator.propagate_to_f2(tid, "dep")
        assert len(correlator.all_traces()) > 0
        correlator.reset()
        assert len(correlator.all_traces()) == 0

    def test_trace_chain_returns_layers(self, correlator: DataTraceCorrelator):
        tid = correlator.generate_data_trace_id("infra_y", "test")
        correlator.propagate_to_postgres(tid, "tx_001")
        correlator.propagate_to_f4(tid)
        chain = correlator.trace_chain(tid)
        assert "i2_postgresql" in chain["layers"]
        assert "f4_observability" in chain["layers"]
