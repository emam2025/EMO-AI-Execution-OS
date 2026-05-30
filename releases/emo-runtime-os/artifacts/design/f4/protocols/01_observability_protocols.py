"""Phase F4 — Observability Layer: Formal Protocols.

Four typed protocols covering the full observability lifecycle:
  ITraceCollector       — Distributed trace span lifecycle (LAW 12)
  ITelemetryAggregator  — Event ingestion, metric computation, window flush (LAW 5)
  IDashboardDataProvider — Runtime dashboard data contracts (§15.13)
  IAlertRouter          — Threshold evaluation, routing, deduplication (§15.13)

Ref: Canon LAW 5 (Observability Mandatory), LAW 12 (Traceability)
Ref: Canon RULE 1 (Determinism), RULE 2 (Reversibility), RULE 3 (Recoverability)
Ref: DEVELOPER.md §15.8, §15.13
Ref: ROADMAP Phase F4 — Observability Layer
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Protocol, Tuple


# ════════════════════════════════════════════════════════════════════
# Shared dependency types (complements models/02_*)
# ════════════════════════════════════════════════════════════════════


class SpanStatus(str, Enum):  # LAW-12
    OK = "ok"
    ERROR = "error"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


class Severity(str, Enum):  # LAW-5
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"
    DEBUG = "debug"


# ════════════════════════════════════════════════════════════════════
# ITraceCollector — Distributed trace span lifecycle
# ════════════════════════════════════════════════════════════════════


class ITraceCollector(Protocol):  # LAW-12
    """Manages the lifecycle of distributed trace spans.

    Every span carries trace_id (global trace) and span_id (local).
    parent_id establishes causal ordering (LAW 12 §15.8).
    """

    def start_span(
        self,
        operation_name: str,
        trace_id: str,
        parent_id: Optional[str] = None,
        attributes: Optional[Dict[str, str]] = None,
    ) -> str:
        """Open a new span and return its span_id.

        trace_id links all spans in a single execution trace.
        parent_id must be None for root spans.
        """
        ...

    def end_span(
        self,
        span_id: str,
        status: SpanStatus = SpanStatus.OK,
        attributes: Optional[Dict[str, str]] = None,
    ) -> None:
        """Close a span and record its duration.

        Once ended a span is immutable (RULE 2).
        """
        ...

    def add_attribute(
        self,
        span_id: str,
        key: str,
        value: str,
    ) -> None:
        """Attach a key-value attribute to an active span.

        Attributes enrich context for failure explorer (§15.13).
        """
        ...

    def propagate_context(
        self,
        trace_id: str,
        span_id: str,
        target_domain: str,
    ) -> Dict[str, str]:
        """Return serialisable context headers for cross-domain propagation.

        target_domain is one of: "f1_api", "d8_mesh", "f3_scheduler",
        "f4_observer".  The returned dict is merged into outbound
        EventBus envelopes or RPC headers.
        """
        ...


# ════════════════════════════════════════════════════════════════════
# ITelemetryAggregator — Event ingestion & metric computation
# ════════════════════════════════════════════════════════════════════


class WindowStrategy(str, Enum):  # LAW-5
    SLIDING_5S = "sliding_5s"
    TUMBLING_1M = "tumbling_1m"
    SESSION = "session"  # per-execution-id


class TelemetryEventType(str, Enum):  # LAW-5
    SPAN_END = "span_end"
    STATE_TRANSITION = "state_transition"
    ALERT_FIRED = "alert_fired"
    METRIC_SAMPLE = "metric_sample"


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
    span_count: int
    alert_count: int
    error_count: int
    metrics: List[AggregatedMetric] = field(default_factory=list)
    dropped_count: int = 0
    lag_ms: float = 0.0


class ITelemetryAggregator(Protocol):  # LAW-5
    """Ingests raw telemetry events and produces windowed metrics.

    LAW 5: Every critical span MUST be accounted for.
    Backpressure: adaptive_sampling() drops DEBUG/INFO under load,
    never CRITICAL spans.
    """

    def ingest_event(
        self,
        event_type: TelemetryEventType,
        payload: Dict[str, str],
        trace_id: Optional[str] = None,
    ) -> None:
        """Accept a raw telemetry event for buffering.

        payload keys and types are domain-specific.
        trace_id, if provided, is used for session-window partitioning.
        """
        ...

    def compute_metrics(
        self,
        window_key: str,
        strategy: WindowStrategy = WindowStrategy.TUMBLING_1M,
    ) -> AggregationSummary:
        """Compute aggregated metrics for a given window.

        Returns count, latency percentiles, error ratio.
        Empty windows return zeroed AggregationSummary.
        """
        ...

    def flush_window(self, window_key: str) -> AggregationSummary:
        """Emit summary to persistent store and evict buffered events.

        RULE 3: On flush failure, preserve buffer for retry.
        """
        ...

    def publish_summary(self, summary: AggregationSummary) -> None:
        """Publish computed summary to EventBus topic.

        Topic: runtime.telemetry.summary
        """
        ...


# ════════════════════════════════════════════════════════════════════
# IDashboardDataProvider — Runtime dashboard data contracts
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


class IDashboardDataProvider(Protocol):  # §15.13
    """Read-only queries for the Runtime Dashboard.

    All methods return snapshot data only — no side effects.
    """

    def get_execution_timeline(
        self,
        execution_id: str,
        since_ns: Optional[int] = None,
    ) -> ExecutionTimelineSegment:
        """Return ordered sequence of node state transitions.

        LAW 12: Every transition is traceable to a span_id.
        """
        ...

    def get_dag_visualization(
        self,
        dag_id: str,
        execution_id: Optional[str] = None,
    ) -> DAGVisualizationResult:
        """Return DAG nodes + edges with execution status overlay.

        RULE 1: Same DAG + execution → same visualisation.
        """
        ...

    def get_worker_topology(
        self,
        worker_ids: Optional[List[str]] = None,
    ) -> WorkerTopologyView:
        """Return live worker topology with health & utilisation.

        Used by F2 Control Plane for scaling decisions.
        """
        ...

    def get_failure_explorer(
        self,
        trace_id: str,
        span_id: Optional[str] = None,
    ) -> FailureExplorerResult:
        """Return root cause analysis for a failed trace.

        LAW 5: Every critical failure MUST be explorable.
        """
        ...


# ════════════════════════════════════════════════════════════════════
# IAlertRouter — Threshold evaluation & alert routing
# ════════════════════════════════════════════════════════════════════


@dataclass
class AlertRule:  # LAW-5
    alert_id: str
    metric_name: str
    operator: str  # "gt", "lt", "gte", "lte", "eq"
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


class IAlertRouter(Protocol):  # §15.13
    """Evaluates metrics against rules and routes alerts.

    RULE 3: Duplicate suppression prevents alert storms.
    """

    def evaluate_threshold(
        self,
        metric: AggregatedMetric,
        rule: AlertRule,
    ) -> bool:
        """Compare metric value against rule threshold.

        Operator semantics:
          gt  — value > threshold
          lt  — value < threshold
          gte — value >= threshold
          lte — value <= threshold
          eq  — value == threshold
        """
        ...

    def route_alert(
        self,
        alert_id: str,
        severity: Severity,
        payload: Dict[str, str],
    ) -> AlertReceipt:
        """Route alert to configured target (EventBus topic, log, etc.).

        CRITICAL alerts always route to runtime.alert.critical.
        """
        ...

    def suppress_duplicate(
        self,
        suppression_key: str,
        cooldown_sec: float = 60.0,
    ) -> bool:
        """Return True if this alert should be suppressed.

        Suppression key is composite of (alert_id, source_domain).
        Cooldown resets after cooldown_sec.
        """
        ...

    def acknowledge(
        self,
        alert_id: str,
        acknowledgement: str,
    ) -> AlertReceipt:
        """Mark an alert as acknowledged.

        Once acknowledged the alert is removed from active list.
        """
        ...
