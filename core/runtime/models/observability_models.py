"""Phase F4 — Observability Layer: Runtime Models.  # LAW-5 # LAW-12

Mirrors artifacts/design/f4/models/02_trace_and_telemetry_models.py
and protocols/01_observability_protocols.py for runtime importability.

Shared types used by all F4 components.

Ref: Canon LAW 5 (Observability Mandatory), LAW 12 (Traceability)
Ref: DEVELOPER.md §15.8, §15.13
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple


# ════════════════════════════════════════════════════════════════════
# Enums
# ════════════════════════════════════════════════════════════════════


class SpanStatus(str, Enum):  # LAW-12 — canonical enum used across all layers
    OK = "ok"
    ERROR = "error"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"
    TIMEOUT = "timeout"
    UNSET = "unset"
    PENDING = "pending"


class Severity(str, Enum):  # LAW-5
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"
    DEBUG = "debug"


class WindowStrategy(str, Enum):  # LAW-5
    SLIDING_5S = "sliding_5s"
    TUMBLING_1M = "tumbling_1m"
    SESSION = "session"


class TelemetryEventType(str, Enum):  # LAW-5
    SPAN_END = "span_end"
    STATE_TRANSITION = "state_transition"
    ALERT_FIRED = "alert_fired"
    METRIC_SAMPLE = "metric_sample"


class NodeStateTransition(str, Enum):  # LAW-12
    PENDING_TO_RUNNING = "pending_to_running"
    RUNNING_TO_COMPLETED = "running_to_completed"
    RUNNING_TO_FAILED = "running_to_failed"
    RUNNING_TO_CANCELLED = "running_to_cancelled"
    PENDING_TO_SKIPPED = "pending_to_skipped"


class WorkerHealthStatus(str, Enum):  # LAW-5
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    OFFLINE = "offline"
    DRAINING = "draining"


# ════════════════════════════════════════════════════════════════════
# TraceSpan
# ════════════════════════════════════════════════════════════════════


@dataclass
class TraceSpan:  # LAW-12
    trace_id: str
    span_id: str
    parent_id: Optional[str] = None
    operation_name: str = ""
    start_ns: int = 0
    end_ns: int = 0
    status: SpanStatus = SpanStatus.UNKNOWN
    attributes: Dict[str, str] = field(default_factory=dict)
    domain: str = ""
    worker_id: str = ""

    @property
    def duration_ns(self) -> int:
        if self.end_ns > self.start_ns:
            return self.end_ns - self.start_ns
        return 0

    @property
    def correlation_id(self) -> str:
        return f"{self.trace_id}:{self.span_id}"


# ════════════════════════════════════════════════════════════════════
# ExecutionTimelineEvent
# ════════════════════════════════════════════════════════════════════


@dataclass
class ExecutionTimelineEvent:  # LAW-12
    sequence_id: int = 0
    node_id: str = ""
    state_transition: NodeStateTransition = NodeStateTransition.PENDING_TO_RUNNING
    timestamp_ns: int = 0
    worker_id: str = ""
    span_id: str = ""
    error_message: str = ""

    @property
    def correlation_id(self) -> str:
        return f"evt:{self.sequence_id}:{self.span_id}" if self.span_id else f"evt:{self.sequence_id}"


# ════════════════════════════════════════════════════════════════════
# DAGVisualizationNode
# ════════════════════════════════════════════════════════════════════


@dataclass
class DAGVisualizationNode:  # LAW-5
    id: str = ""
    label: str = ""
    status: str = "pending"
    duration_ms: float = 0.0
    dependencies: List[str] = field(default_factory=list)
    error_trace: str = ""


# ════════════════════════════════════════════════════════════════════
# WorkerTopologySnapshot
# ════════════════════════════════════════════════════════════════════


@dataclass
class WorkerTopologySnapshot:  # LAW-5
    worker_id: str = ""
    status: WorkerHealthStatus = WorkerHealthStatus.HEALTHY
    active_leases: int = 0
    resource_utilization: float = 0.0
    memory_utilization: float = 0.0
    health_score: float = 1.0
    affinity_tags: List[str] = field(default_factory=list)


# ════════════════════════════════════════════════════════════════════
# AlertPayload
# ════════════════════════════════════════════════════════════════════


@dataclass
class AlertPayload:  # LAW-5
    alert_id: str = ""
    severity: Severity = Severity.INFO
    source_domain: str = ""
    condition_met: str = ""
    suppression_key: str = ""
    routing_target: str = ""
    metric_value: float = 0.0
    threshold: float = 0.0
    timestamp_ns: int = 0


# ════════════════════════════════════════════════════════════════════
# AggregatedMetric / AggregationSummary  (from protocol shared types)
# ════════════════════════════════════════════════════════════════════


@dataclass
class AggregatedMetric:  # LAW-5
    metric_name: str
    window_key: str
    count: int = 0
    sum: float = 0.0
    min: float = 0.0
    max: float = 0.0
    avg: float = 0.0
    p50: float = 0.0
    p99: float = 0.0


@dataclass
class AggregationSummary:  # LAW-5
    window_key: str
    span_count: int = 0
    alert_count: int = 0
    error_count: int = 0
    metrics: List[AggregatedMetric] = field(default_factory=list)
    dropped_count: int = 0
    lag_ms: float = 0.0


# ════════════════════════════════════════════════════════════════════
# Dashboard data contracts (from protocol shared types)
# ════════════════════════════════════════════════════════════════════


@dataclass
class ExecutionTimelineSegment:  # §15.13
    execution_id: str
    nodes: List[Dict[str, str]] = field(default_factory=list)
    total_duration_ms: float = 0.0
    error_count: int = 0


@dataclass
class WorkerTopologyView:  # §15.13
    workers: List[Dict[str, str]] = field(default_factory=list)
    healthy_count: int = 0
    degraded_count: int = 0
    offline_count: int = 0


@dataclass
class FailureExplorerResult:  # §15.13
    failure_id: str
    trace_id: str
    root_span_id: Optional[str] = None
    error_message: str = ""
    affected_spans: List[str] = field(default_factory=list)
    suggested_remedy: str = ""


@dataclass
class DAGVisualizationResult:  # §15.13
    dag_id: str
    nodes: List[Dict[str, str]] = field(default_factory=list)
    edges: List[Tuple[str, str]] = field(default_factory=list)
    critical_path_ms: float = 0.0


# ════════════════════════════════════════════════════════════════════
# AlertRule / AlertReceipt (from protocol shared types)
# ════════════════════════════════════════════════════════════════════


@dataclass
class AlertRule:  # LAW-5
    alert_id: str
    metric_name: str
    operator: str
    threshold: float
    severity: Severity
    suppression_key: str = ""
    cooldown_sec: float = 60.0


@dataclass
class AlertReceipt:  # LAW-5
    alert_id: str
    severity: Severity
    timestamp_ns: int
    suppressed: bool = False
    routed_to: str = ""
    acknowledgement: str = ""
