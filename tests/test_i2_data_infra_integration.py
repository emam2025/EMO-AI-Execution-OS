"""Phase I2 — Data Infrastructure Integration Tests.  # LAW-5 LAW-11 LAW-14 LAW-15 LAW-16 LAW-20 LAW-21 LAW-22 RULE-1 RULE-2 RULE-3 RULE-4 RULE-5

Integration tests for PostgreSQLManager, DistributedLog, RuntimeAnalytics,
DataMigrator, ACIDStateMachine, and DataTraceCorrelator.

Ref: Canon LAW 5, LAW 11, LAW 14-16, LAW 20-22, RULE 1-5
Ref: artifacts/design/i2/
"""

from __future__ import annotations

import pytest

from core.runtime.data.postgresql_manager import PostgreSQLManager
from core.runtime.data.distributed_log import DistributedLog
from core.runtime.data.runtime_analytics import RuntimeAnalytics
from core.runtime.data.data_migrator import DataMigrator
from core.runtime.data.acid_state_machine import ACIDStateMachine, ACIDState, ACIDTransition
from core.runtime.data.trace_correlator import DataTraceCorrelator
from core.runtime.event_bus import InMemoryEventBus


DATA_TRACE_ID = "data_test_integration_001"


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


# ═══════════════════════════════════════════════════════════════════════════
# TestACIDGuardEnforcement (5 tests)
# ═══════════════════════════════════════════════════════════════════════════


class TestACIDGuardEnforcement:
    def test_execute_tx_serializable_passes(self, pg: PostgreSQLManager):
        result = pg.execute_tx(
            [{"sql": "INSERT INTO t VALUES (1)", "rows": 1}],
            "SERIALIZABLE", DATA_TRACE_ID,
        )
        assert result["committed"]
        assert result["tx_id"]

    def test_execute_tx_repeatable_read_passes(self, pg: PostgreSQLManager):
        result = pg.execute_tx(
            [{"sql": "INSERT INTO t VALUES (1)", "rows": 1}],
            "REPEATABLE_READ", DATA_TRACE_ID,
        )
        assert result["committed"]

    def test_execute_tx_blocks_read_committed(self, pg: PostgreSQLManager):
        result = pg.execute_tx(
            [{"sql": "INSERT INTO t VALUES (1)", "rows": 1}],
            "READ_COMMITTED", DATA_TRACE_ID,
        )
        # G2 requires REPEATABLE_READ or SERIALIZABLE
        assert not result["committed"]
        assert "insufficient" in result.get("rollback_reason", "")

    def test_execute_tx_blocks_missing_trace_id(self, pg: PostgreSQLManager):
        result = pg.execute_tx(
            [{"sql": "INSERT INTO t VALUES (1)", "rows": 1}],
            "SERIALIZABLE", "",
        )
        assert not result["committed"]

    def test_execute_tx_rolls_back_on_query_error(self, pg: PostgreSQLManager):
        result = pg.execute_tx(
            [{"sql": "INSERT INTO t VALUES (1)", "rows": 1, "error": True}],
            "SERIALIZABLE", DATA_TRACE_ID,
        )
        assert not result["committed"]


# ═══════════════════════════════════════════════════════════════════════════
# TestMigrationDeterminism (5 tests)
# ═══════════════════════════════════════════════════════════════════════════


class TestMigrationDeterminism:
    def test_extract_produces_hash(self, migrator: DataMigrator):
        result = migrator.extract_legacy_sqlite("/path/db", ["t1", "t2"], DATA_TRACE_ID)
        assert result["extracted"]
        assert result["snapshot_hash"]

    def test_extract_same_path_same_hash(self, migrator: DataMigrator):
        r1 = migrator.extract_legacy_sqlite("/path/db", ["t1"], DATA_TRACE_ID)
        r2 = migrator.extract_legacy_sqlite("/path/db", ["t1"], DATA_TRACE_ID)
        assert r1["snapshot_hash"] == r2["snapshot_hash"]

    def test_transform_produces_mapping_hash(self, migrator: DataMigrator):
        result = migrator.transform_schema(
            {"tables": {"old": "INTEGER"}},
            {"tables": {"new": "INTEGER"}},
            [{"source_table": "old", "source_column": "id",
              "target_table": "new", "target_column": "id"}],
            DATA_TRACE_ID,
        )
        assert result["transformed"]
        assert result["mapping_hash"]

    def test_load_batches(self, migrator: DataMigrator):
        result = migrator.load_postgres(
            {"t1": [{"id": i} for i in range(50)]},
            {"host": "localhost", "port": 5432},
            batch_size=10, data_trace_id=DATA_TRACE_ID,
        )
        assert result["loaded"]
        assert result["batches_committed"] == 5

    def test_verify_migration(self, migrator: DataMigrator):
        result = migrator.verify_migration("hash_abc", "t1", 100, DATA_TRACE_ID)
        assert "verified" in result
        assert "integrity_pct" in result


# ═══════════════════════════════════════════════════════════════════════════
# TestLogReplicationSafety (5 tests)
# ═══════════════════════════════════════════════════════════════════════════


class TestLogReplicationSafety:
    def test_append_and_read(self, log: DistributedLog):
        result = log.append_entry("runtime.execution", {"a": 1}, DATA_TRACE_ID)
        assert result["entry_id"]
        assert result["offset"] == 0

    def test_read_range_returns_entries(self, log: DistributedLog):
        log.append_entry("test.stream", {"a": 1}, DATA_TRACE_ID)
        log.append_entry("test.stream", {"b": 2}, DATA_TRACE_ID)
        log.append_entry("test.stream", {"c": 3}, DATA_TRACE_ID)
        result = log.read_range("test.stream", 0, 1, DATA_TRACE_ID)
        assert result["count"] == 2
        assert len(result["entries"]) == 2

    def test_compact_removes_old(self, log: DistributedLog):
        import time
        log.append_entry("compact.test", {"data": "old"}, DATA_TRACE_ID)
        time.sleep(0.1)
        result = log.compact_segments("compact.test", 0.0, DATA_TRACE_ID)
        assert result["compacted"]
        assert result["entries_removed"] == 1

    def test_sync_replicas(self, log: DistributedLog):
        log.append_entry("sync.test", {"x": 1}, DATA_TRACE_ID)
        result = log.sync_replicas("sync.test", ["node1", "node2"], DATA_TRACE_ID)
        assert result["nodes_synced"] == 2

    def test_append_requires_dict(self, log: DistributedLog):
        result = log.append_entry("test", "not_a_dict", DATA_TRACE_ID)
        assert "error" in result


# ═══════════════════════════════════════════════════════════════════════════
# TestAnalyticsComputation (5 tests)
# ═══════════════════════════════════════════════════════════════════════════


class TestAnalyticsComputation:
    def test_compute_throughput(self, analytics: RuntimeAnalytics):
        result = analytics.compute_throughput("w1", [{"value": 10.0}, {"value": 20.0}], DATA_TRACE_ID)
        assert result["total_operations"] == 2
        assert result["avg_latency_ms"] == 15.0

    def test_detect_anomalies(self, analytics: RuntimeAnalytics):
        metrics = [{"name": "latency", "value": 150.0}]
        baselines = {"latency": 50.0}
        result = analytics.detect_anomalies("w1", metrics, baselines, DATA_TRACE_ID)
        assert result["anomaly_count"] == 1

    def test_aggregate_sum(self, analytics: RuntimeAnalytics):
        result = analytics.aggregate_metrics(
            "w1", [{"value": 1}, {"value": 2}, {"value": 3}], "sum", DATA_TRACE_ID,
        )
        assert result["aggregated_value"] == 6.0

    def test_aggregate_avg(self, analytics: RuntimeAnalytics):
        result = analytics.aggregate_metrics(
            "w1", [{"value": 10}, {"value": 20}], "avg", DATA_TRACE_ID,
        )
        assert result["aggregated_value"] == 15.0

    def test_publish_dashboard(self, analytics: RuntimeAnalytics):
        result = analytics.publish_dashboard(
            "dash_001",
            [{"type": "chart", "title": "Throughput", "refresh_sec": 30}],
            DATA_TRACE_ID,
        )
        assert result["published"]
        assert result["widget_count"] == 1


# ═══════════════════════════════════════════════════════════════════════════
# TestSchemaManagement (4 tests)
# ═══════════════════════════════════════════════════════════════════════════


class TestSchemaManagement:
    def test_migrate_schema(self, pg: PostgreSQLManager):
        result = pg.migrate_schema("mig_001", ["CREATE TABLE t1 (id INT)"], DATA_TRACE_ID)
        assert result["migration_applied"]
        assert result["applied_version"] == 1

    def test_migrate_idempotent(self, pg: PostgreSQLManager):
        pg.migrate_schema("mig_idem", ["CREATE TABLE t1 (id INT)"], DATA_TRACE_ID)
        result = pg.migrate_schema("mig_idem", ["CREATE TABLE t1 (id INT)"], DATA_TRACE_ID)
        assert not result["migration_applied"]  # idempotent

    def test_partition_table(self, pg: PostgreSQLManager):
        result = pg.partition_table("deployments", "region", "range", DATA_TRACE_ID)
        assert result["partitioned"]
        assert result["partition_count"] > 0

    def test_partition_requires_keys(self, pg: PostgreSQLManager):
        result = pg.partition_table("", "", "range", DATA_TRACE_ID)
        assert not result["partitioned"]


# ═══════════════════════════════════════════════════════════════════════════
# TestEventBusPropagation (3 tests)
# ═══════════════════════════════════════════════════════════════════════════


class TestEventBusPropagation:
    def test_pg_emits_event(self, pg: PostgreSQLManager, event_bus: InMemoryEventBus):
        pg.execute_tx([{"sql": "INSERT INTO t VALUES (1)", "rows": 1}],
                       "SERIALIZABLE", DATA_TRACE_ID)
        events = event_bus.get_events("runtime.data.postgresql", limit=10)
        assert len(events) > 0

    def test_log_emits_event(self, log: DistributedLog, event_bus: InMemoryEventBus):
        log.append_entry("test.stream", {"x": 1}, DATA_TRACE_ID)
        events = event_bus.get_events("runtime.data.log", limit=10)
        assert len(events) > 0

    def test_analytics_emits_event(self, analytics: RuntimeAnalytics, event_bus: InMemoryEventBus):
        analytics.compute_throughput("w1", [{"value": 1.0}], DATA_TRACE_ID)
        events = event_bus.get_events("runtime.data.analytics", limit=10)
        assert len(events) > 0
