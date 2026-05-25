"""Phase I2 — Data Infrastructure Protocols.  # LAW-5 LAW-11 LAW-14 LAW-15 LAW-16 LAW-20 LAW-21 LAW-22 RULE-1 RULE-2 RULE-3 RULE-4 RULE-5

Formal typing.Protocols for PostgreSQL Manager, Distributed Log,
Runtime Analytics, and Data Migrator. Every interface enforces
observability (LAW 5), stateless/immutable design (LAW 11), and
data integrity (LAW 14-16).

Ref: Canon LAW 5 (Observability Mandatory)
Ref: Canon LAW 11 (No Global State)
Ref: Canon LAW 14 (DAG Integrity), LAW 15 (Cost Budgets)
Ref: Canon LAW 16 (Worker Fairness)
Ref: Canon LAW 20 (Failure Detection), LAW 21 (Failure Propagation)
Ref: Canon LAW 22 (Service Isolation)
Ref: Canon RULE 1 (Determinism), RULE 2 (No Uncontrolled IO)
Ref: Canon RULE 3 (Safety Guards), RULE 4 (Isolation), RULE 5 (Recovery)
Ref: ROADMAP Phase I2 — Data Infrastructure
Ref: DEVELOPER.md §15.9, §15.13
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class IPostgreSQLManager(Protocol):  # LAW-5 LAW-11 LAW-14 RULE-1 RULE-2
    """PostgreSQL schema and partition manager — stateless, idempotent.

    Every schema operation is driven by a declarative migration manifest.
    The manager never mutates global state (LAW 11) and reports all
    lifecycle events to F4 Observability (LAW 5).
    """

    def migrate_schema(  # LAW-14 RULE-1
        self,
        migration_id: str,
        sql_statements: List[str],
        data_trace_id: str,
    ) -> Dict[str, Any]:
        """Apply a schema migration transactionally.

        Args:
            migration_id:   Unique migration identifier.
            sql_statements: Ordered list of SQL DDL/DML statements.
            data_trace_id:  Correlation ID for observability (LAW 5).

        Returns:
            migration_applied: True if migration succeeded.
            applied_version:   Schema version after migration.
            tables_affected:   List of table names touched.
            duration_ms:       Execution time.
            events:            Lifecycle events emitted.

        RULE 1: Same migration_id + sql_statements → same outcome.
        LAW 14: Schema changes must preserve DAG integrity.
        """

    def partition_table(  # LAW-11 RULE-4
        self,
        table_name: str,
        partition_key: str,
        partition_strategy: str,
        data_trace_id: str,
    ) -> Dict[str, Any]:
        """Partition an existing table by the specified key.

        Args:
            table_name:         Target table.
            partition_key:      Column to partition by (e.g. "mission_id", "timestamp").
            partition_strategy: Strategy: "range", "list", "hash".
            data_trace_id:      Correlation ID for observability.

        Returns:
            partitioned:       True if partitioning completed.
            partition_count:   Number of partitions created.
            partition_map:     Mapping of key ranges to partition names.
            events:            Partitioning lifecycle events.

        LAW 11: Partition boundaries are deterministic — no hidden state.
        RULE 4: Partitions are isolated — no cross-partition leaks.
        """

    def execute_tx(  # LAW-20 RULE-3
        self,
        queries: List[Dict[str, Any]],
        isolation_level: str,
        data_trace_id: str,
    ) -> Dict[str, Any]:
        """Execute a transactional batch of queries.

        Args:
            queries:          List of query dicts: {sql, params, timeout_sec}.
            isolation_level:  "READ_COMMITTED", "REPEATABLE_READ", "SERIALIZABLE".
            data_trace_id:    Correlation ID for observability.

        Returns:
            tx_id:            Unique transaction identifier.
            committed:        True if all queries committed.
            rows_affected:    Total rows affected across all queries.
            rollback_reason:  Populated if transaction rolled back.
            duration_ms:      Execution time.

        LAW 20: Transaction failures detected and reported.
        RULE 3: Isolation level must be explicitly set.
        """

    def verify_integrity(  # LAW-14 RULE-1
        self,
        table_name: str,
        expected_checksum: str,
        data_trace_id: str,
    ) -> Dict[str, Any]:
        """Verify table data integrity against expected checksum.

        Args:
            table_name:        Target table.
            expected_checksum: Expected SHA-256 checksum of table contents.
            data_trace_id:     Correlation ID.

        Returns:
            integrity_ok:      True if checksum matches.
            actual_checksum:   Actual SHA-256 checksum.
            row_count:         Number of rows in table.
            size_bytes:        Estimated storage size.

        RULE 1: Same table contents → same checksum (deterministic).
        """


@runtime_checkable
class IDistributedLog(Protocol):  # LAW-5 LAW-11 LAW-21 RULE-2 RULE-5
    """Distributed append-only log with segment compaction and replica sync.

    All log state is ephemeral or backed by durable storage.
    No global in-memory state (LAW 11). Every entry carries observability
    metadata (LAW 5).
    """

    def append_entry(  # LAW-11 RULE-2
        self,
        stream: str,
        payload: Dict[str, Any],
        data_trace_id: str,
    ) -> Dict[str, Any]:
        """Append an entry to a log stream.

        Args:
            stream:         Log stream name (e.g. "runtime.execution", "db.changes").
            payload:        Entry payload as dict.
            data_trace_id:  Correlation ID.

        Returns:
            entry_id:       Unique entry identifier (monotonic).
            stream:         Stream the entry was appended to.
            offset:         Offset within the stream.
            timestamp_ns:   Epoch nanosecond timestamp.
            payload_hash:   SHA-256 hash of payload (RULE 1).

        LAW 11: Log streams are service boundaries — no shared state.
        RULE 2: Payload validated before append.
        """

    def read_range(  # LAW-5
        self,
        stream: str,
        start_offset: int,
        end_offset: int,
        data_trace_id: str,
    ) -> Dict[str, Any]:
        """Read a range of entries from a log stream.

        Args:
            stream:         Log stream name.
            start_offset:   Inclusive start offset.
            end_offset:     Inclusive end offset.
            data_trace_id:  Correlation ID.

        Returns:
            entries:        List of entry dicts with payload, offset, timestamp.
            stream:         Stream queried.
            count:          Number of entries returned.
            has_more:       True if more entries exist beyond end_offset.
        """

    def compact_segments(  # RULE-5
        self,
        stream: str,
        retention_sec: float,
        data_trace_id: str,
    ) -> Dict[str, Any]:
        """Compact old log segments based on retention policy.

        Args:
            stream:         Log stream name.
            retention_sec:  Max age in seconds before compaction.
            data_trace_id:  Correlation ID.

        Returns:
            compacted:      True if compaction completed.
            segments_removed: Number of old segments removed.
            entries_removed:  Total entries removed.
            bytes_reclaimed:  Storage bytes reclaimed.

        RULE 5: Compaction is independent per stream — no cross-stream effects.
        """

    def sync_replicas(  # LAW-21 RULE-4
        self,
        stream: str,
        target_nodes: List[str],
        data_trace_id: str,
    ) -> Dict[str, Any]:
        """Synchronise log entries with replica nodes.

        Args:
            stream:         Log stream name.
            target_nodes:   List of target node identifiers.
            data_trace_id:  Correlation ID.

        Returns:
            synced:         True if all replicas are up to date.
            nodes_synced:   Number of nodes successfully synced.
            entries_synced: Number of entries replicated.
            lag_ms:         Max replication lag in milliseconds.

        LAW 21: Failure propagation is contained — one failed replica
        does not cascade to others.
        RULE 4: Replicas are isolated — sync is non-blocking.
        """


@runtime_checkable
class IRuntimeAnalytics(Protocol):  # LAW-5 LAW-15 LAW-16 RULE-1 RULE-2
    """Runtime analytics engine — throughput, anomaly detection, dashboards.

    All computations are deterministic (RULE 1) and respect cost budgets
    (LAW 15) and worker fairness (LAW 16).
    """

    def compute_throughput(  # LAW-15 RULE-1
        self,
        window_id: str,
        metrics: List[Dict[str, Any]],
        data_trace_id: str,
    ) -> Dict[str, Any]:
        """Compute throughput metrics for a time window.

        Args:
            window_id:      Analytics window identifier.
            metrics:        List of metric dicts: {timestamp, value, unit, source}.
            data_trace_id:  Correlation ID.

        Returns:
            window_id:      Window identifier.
            operations_per_sec: Computed throughput.
            avg_latency_ms: Average latency in window.
            p99_latency_ms: P99 latency in window.
            total_operations: Total operations counted.
            cost_estimate:  Estimated compute cost (LAW 15).

        RULE 1: Same metrics → same throughput (deterministic).
        LAW 15: Cost estimate must be reported with every computation.
        """

    def detect_anomalies(  # LAW-5 RULE-3
        self,
        window_id: str,
        metrics: List[Dict[str, Any]],
        baselines: Dict[str, float],
        data_trace_id: str,
    ) -> Dict[str, Any]:
        """Detect anomalies in metrics against baselines.

        Args:
            window_id:      Analytics window identifier.
            metrics:        List of metric dicts.
            baselines:      Baseline thresholds: {metric_name: threshold_value}.
            data_trace_id:  Correlation ID.

        Returns:
            window_id:      Window identifier.
            anomalies:      List of anomaly dicts: {metric, value, baseline, severity}.
            anomaly_count:  Total anomalies detected.
            critical_count: Anomalies exceeding critical threshold.

        RULE 3: Anomaly detection is guarded by baseline validation.
        """

    def aggregate_metrics(  # LAW-5 LAW-16 RULE-1
        self,
        window_id: str,
        raw_metrics: List[Dict[str, Any]],
        aggregation_fn: str,
        data_trace_id: str,
    ) -> Dict[str, Any]:
        """Aggregate raw metrics using specified function.

        Args:
            window_id:      Analytics window identifier.
            raw_metrics:    List of raw metric dicts.
            aggregation_fn: Aggregation function: "sum", "avg", "min", "max", "count".
            data_trace_id:  Correlation ID.

        Returns:
            window_id:      Window identifier.
            aggregated_value: Computed aggregate.
            aggregation_fn:  Function used.
            input_count:     Number of input metrics.
            output_count:    Number of output data points.

        LAW 16: Aggregation weights are fair — no source gets priority.
        RULE 1: Same inputs + function → same result.
        """

    def publish_dashboard(  # LAW-5
        self,
        dashboard_id: str,
        widgets: List[Dict[str, Any]],
        data_trace_id: str,
    ) -> Dict[str, Any]:
        """Publish a dashboard update with computed metrics.

        Args:
            dashboard_id:  Dashboard identifier.
            widgets:       List of widget configs: {type, title, metrics, refresh_sec}.
            data_trace_id: Correlation ID.

        Returns:
            published:     True if dashboard published.
            dashboard_id:  Dashboard identifier.
            widget_count:  Number of widgets updated.
            published_at_ns: Publication timestamp.

        LAW 5: All dashboard publications are observable.
        """


@runtime_checkable
class IDataMigrator(Protocol):  # LAW-5 LAW-11 LAW-14 RULE-1 RULE-2 RULE-5
    """SQLite → PostgreSQL data migrator — deterministic and verifiable.

    The migrator guarantees that the same sqlite_snapshot + schema_mapping
    produces the same PostgreSQL state every time (RULE 1).
    """

    def extract_legacy_sqlite(  # LAW-11 RULE-2
        self,
        sqlite_path: str,
        tables: List[str],
        data_trace_id: str,
    ) -> Dict[str, Any]:
        """Extract data from legacy SQLite database.

        Args:
            sqlite_path:    Path to SQLite database file.
            tables:         List of table names to extract.
            data_trace_id:  Correlation ID.

        Returns:
            extracted:      True if extraction succeeded.
            tables_count:   Number of tables extracted.
            rows_total:     Total rows extracted.
            snapshot_hash:  SHA-256 hash of extracted snapshot (RULE 1).
            size_bytes:     Size of extracted data.

        LAW 11: Extraction is read-only — no mutation of source.
        RULE 2: Input validated before extraction.
        """

    def transform_schema(  # LAW-14 RULE-1
        self,
        sqlite_schema: Dict[str, Any],
        target_schema: Dict[str, Any],
        mapping_rules: List[Dict[str, Any]],
        data_trace_id: str,
    ) -> Dict[str, Any]:
        """Transform SQLite schema to PostgreSQL target schema.

        Args:
            sqlite_schema:  Source schema from SQLite.
            target_schema:  Target PostgreSQL schema definition.
            mapping_rules:  List of mapping rules: {source_table, source_column,
                           target_table, target_column, transform_fn}.
            data_trace_id:  Correlation ID.

        Returns:
            transformed:     True if transformation completed.
            mapping_hash:    SHA-256 hash of mapping_rules (RULE 1).
            columns_mapped:  Number of columns mapped.
            tables_created:  Number of target tables created.

        LAW 14: Schema transformation preserves referential integrity.
        RULE 1: Same sqlite_schema + mapping_rules → same target_schema.
        """

    def load_postgres(  # LAW-5 RULE-5
        self,
        transformed_data: Dict[str, Any],
        target_conn_config: Dict[str, Any],
        batch_size: int,
        data_trace_id: str,
    ) -> Dict[str, Any]:
        """Load transformed data into PostgreSQL.

        Args:
            transformed_data:   Data dict: {table_name: [rows]}.
            target_conn_config: Connection config for target PostgreSQL.
            batch_size:         Rows per batch insert.
            data_trace_id:      Correlation ID.

        Returns:
            loaded:             True if all batches loaded.
            tables_loaded:      Number of tables loaded.
            rows_loaded:        Total rows inserted.
            batches_committed:  Number of batches committed.
            duration_ms:        Total load time.

        RULE 5: Failed batches retry independently.
        """

    def verify_migration(  # LAW-5 RULE-1
        self,
        source_hash: str,
        target_table: str,
        expected_row_count: int,
        data_trace_id: str,
    ) -> Dict[str, Any]:
        """Verify migration integrity by comparing source and target.

        Args:
            source_hash:       SHA-256 hash of source data (from extract).
            target_table:      Target PostgreSQL table name.
            expected_row_count:Expected row count.
            data_trace_id:     Correlation ID.

        Returns:
            verified:           True if all checks pass.
            source_hash_matches:True if target hash matches source.
            row_count_matches:  True if row counts match.
            integrity_pct:      Percentage of rows verified.

        RULE 1: Same data → same hash → migration verified.
        """
