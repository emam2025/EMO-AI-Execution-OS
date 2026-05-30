"""Phase I2 — Data Infrastructure Models.  # LAW-5 LAW-11 LAW-14 LAW-15 LAW-16 LAW-20 LAW-21 LAW-22 RULE-1 RULE-2 RULE-3 RULE-4 RULE-5

Shared dataclasses and enums for all I2 components: IPostgreSQLManager,
IDistributedLog, IRuntimeAnalytics, and IDataMigrator.

Ref: Canon LAW 5 (Observability), LAW 11 (No Global State)
Ref: Canon LAW 14 (DAG Integrity), LAW 15 (Cost Budgets)
Ref: Canon LAW 16 (Worker Fairness)
Ref: Canon LAW 20 (Failure Detection), LAW 21 (Failure Propagation)
Ref: Canon LAW 22 (Service Isolation)
Ref: Canon RULE 1-5
Ref: artifacts/design/i2/models/02_storage_and_sharding_models.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class MigrationStatus(str, Enum):
    PENDING = "pending"
    EXTRACTING = "extracting"
    TRANSFORMING = "transforming"
    LOADING = "loading"
    VERIFIED = "verified"
    FAILED = "failed"


class PartitionStrategy(str, Enum):
    RANGE = "range"
    LIST = "list"
    HASH = "hash"


class ReplicationMode(str, Enum):
    SYNC = "synchronous"
    ASYNC = "asynchronous"
    QUORUM = "quorum"


class IsolationLevel(str, Enum):
    READ_COMMITTED = "READ_COMMITTED"
    REPEATABLE_READ = "REPEATABLE_READ"
    SERIALIZABLE = "SERIALIZABLE"


class LogStream(str, Enum):
    EXECUTION = "runtime.execution"
    DB_CHANGES = "db.changes"
    SCHEMA_MIGRATIONS = "schema.migrations"
    ANALYTICS_METRICS = "analytics.metrics"
    AUDIT_TRAIL = "audit.trail"


class AnomalySeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class MigrationGuardResult(str, Enum):
    PASSED = "passed"
    BLOCKED_CHECKSUM = "blocked_checksum_mismatch"
    BLOCKED_STALE = "blocked_stale_snapshot"
    BLOCKED_QUORUM = "blocked_quorum_not_reached"
    BLOCKED_ISOLATION = "blocked_isolation_level"
    BLOCKED_PARTITION = "blocked_partition_key"


@dataclass
class StorageConfig:
    connection_pool_min: int = 5
    connection_pool_max: int = 20
    max_retries: int = 3
    retry_delay_sec: float = 1.0
    partition_strategy: PartitionStrategy = PartitionStrategy.RANGE
    replication_mode: ReplicationMode = ReplicationMode.QUORUM
    default_isolation_level: IsolationLevel = IsolationLevel.READ_COMMITTED
    statement_timeout_sec: float = 30.0
    lock_timeout_sec: float = 5.0
    data_trace_id: str = ""
    namespace: str = "emo-production"
    host: str = "localhost"
    port: int = 5432
    database: str = "emo_runtime"
    pool_prefill: bool = True
    health_check_interval_sec: float = 30.0


@dataclass
class LogEntry:
    entry_id: str = ""
    stream: str = ""
    offset: int = 0
    payload: Dict[str, Any] = field(default_factory=dict)
    payload_hash: str = ""
    timestamp_ns: int = 0
    source_node: str = ""
    ack_status: str = "pending"
    data_trace_id: str = ""
    metadata: Dict[str, str] = field(default_factory=dict)


@dataclass
class LogSegment:
    segment_id: str = ""
    stream: str = ""
    start_offset: int = 0
    end_offset: int = 0
    entry_count: int = 0
    size_bytes: int = 0
    created_at_ns: int = 0
    expires_at_ns: int = 0
    compacted: bool = False


@dataclass
class ReplicaSyncStatus:
    node_id: str = ""
    stream: str = ""
    last_synced_offset: int = 0
    target_offset: int = 0
    lag_ms: float = 0.0
    synced: bool = False
    last_error: str = ""
    data_trace_id: str = ""


@dataclass
class AnalyticsWindow:
    window_id: str = ""
    start_time_ns: int = 0
    end_time_ns: int = 0
    duration_ms: float = 0.0
    metrics_agg: Dict[str, float] = field(default_factory=lambda: {
        "throughput_ops_sec": 0.0,
        "avg_latency_ms": 0.0,
        "p99_latency_ms": 0.0,
        "error_rate": 0.0,
        "total_operations": 0,
    })
    anomaly_flags: List[Dict[str, Any]] = field(default_factory=list)
    cost_estimate: float = 0.0
    data_trace_id: str = ""
    source_nodes: List[str] = field(default_factory=list)


@dataclass
class AnomalyRecord:
    anomaly_id: str = ""
    window_id: str = ""
    metric_name: str = ""
    observed_value: float = 0.0
    baseline_value: float = 0.0
    deviation_pct: float = 0.0
    severity: AnomalySeverity = AnomalySeverity.LOW
    detected_at_ns: int = 0
    data_trace_id: str = ""


@dataclass
class MigrationManifest:
    migration_id: str = ""
    source_sqlite_path: str = ""
    target_postgres_db: str = ""
    tables_to_migrate: List[str] = field(default_factory=list)
    schema_mapping_rules: List[Dict[str, Any]] = field(default_factory=list)
    target_schema: Dict[str, Any] = field(default_factory=dict)
    snapshot_hash: str = ""
    mapping_hash: str = ""
    status: MigrationStatus = MigrationStatus.PENDING
    row_count_source: int = 0
    row_count_target: int = 0
    integrity_pct: float = 0.0
    duration_ms: float = 0.0
    data_trace_id: str = ""
    errors: List[str] = field(default_factory=list)


@dataclass
class PartitionMap:
    table_name: str = ""
    partition_key: str = ""
    strategy: PartitionStrategy = PartitionStrategy.RANGE
    partitions: List[Dict[str, Any]] = field(default_factory=list)
    default_partition: str = ""
    data_trace_id: str = ""


@dataclass
class DashboardConfig:
    dashboard_id: str = ""
    title: str = ""
    widgets: List[Dict[str, Any]] = field(default_factory=list)
    refresh_interval_sec: float = 30.0
    data_trace_id: str = ""
    created_at_ns: int = 0
    updated_at_ns: int = 0
