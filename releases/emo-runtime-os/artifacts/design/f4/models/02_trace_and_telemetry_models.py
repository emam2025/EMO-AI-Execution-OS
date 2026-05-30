"""Phase F4 — Observability Layer: Trace & Telemetry Models.

All dataclasses and enums for distributed tracing, execution timelines,
DAG visualisation, worker topology, and alerting.

Ref: Canon LAW 5 (Observability Mandatory), LAW 12 (Traceability)
Ref: DEVELOPER.md §15.8, §15.13
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


# ════════════════════════════════════════════════════════════════════
# Shared Enums
# ════════════════════════════════════════════════════════════════════


class SpanStatus(str, Enum):  # LAW-12
    OK = "ok"
    ERROR = "error"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


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


class Severity(str, Enum):  # LAW-5
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"
    DEBUG = "debug"


# ════════════════════════════════════════════════════════════════════
# TraceSpan — Core distributed trace unit
# ════════════════════════════════════════════════════════════════════


@dataclass
class TraceSpan:  # LAW-12
    """A single unit of work in a distributed trace.

    Every span MUST have:
      - trace_id  (global execution trace identifier)
      - span_id   (unique within the trace)
      - parent_id (None for root spans)

    Fields:
      operation_name : human-readable label (e.g. "scheduler.match")
      start_ns       : monotonic start time in nanoseconds
      end_ns         : monotonic end time (0 until end_span())
      status         : completion status (SpanStatus)
      attributes     : arbitrary key-value metadata
      domain         : originating subsystem (f1, d8, f3, f4)
      worker_id      : worker that executed this span (optional)
    """

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
        """Composite key for cross-domain correlation.

        Format: {trace_id}:{span_id}
        LAW 12: No span without correlation_id.
        """
        return f"{self.trace_id}:{self.span_id}"


# ════════════════════════════════════════════════════════════════════
# ExecutionTimelineEvent — Sequential node state transitions
# ════════════════════════════════════════════════════════════════════


@dataclass
class ExecutionTimelineEvent:  # LAW-12, §15.13
    """A single recorded event in an execution timeline.

    Every execution produces an ordered sequence of these events.
    The sequence is deterministic (RULE 1) for the same DAG + input.

    Fields:
      sequence_id       : monotonic order within the execution
      node_id           : DAG node identifier
      state_transition  : what happened (NodeStateTransition)
      timestamp_ns      : wall-clock timestamp for ordering
      worker_id         : worker that processed the node
      span_id           : link to the correlating TraceSpan
      error_message     : populated on RUNNING_TO_FAILED
    """

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
# DAGVisualizationNode — Renderable DAG node with status
# ════════════════════════════════════════════════════════════════════


@dataclass
class DAGVisualizationNode:  # LAW-5, §15.13
    """A single node in the DAG visualisation.

    Fields:
      id             : unique node identifier
      label          : display name
      status         : current NodeState (or equivalent)
      duration_ms    : execution duration in milliseconds
      dependencies   : list of parent node IDs
      error_trace    : optional error details (populated on failure)
    """

    id: str = ""
    label: str = ""
    status: str = "pending"
    duration_ms: float = 0.0
    dependencies: List[str] = field(default_factory=list)
    error_trace: str = ""


# ════════════════════════════════════════════════════════════════════
# WorkerTopologySnapshot — Live worker status for topology view
# ════════════════════════════════════════════════════════════════════


@dataclass
class WorkerTopologySnapshot:  # LAW-5, §15.13
    """A snapshot of a single worker for the Worker Topology Viewer.

    Fields:
      worker_id           : unique worker identifier
      status              : WorkerHealthStatus
      active_leases       : number of currently held leases
      resource_utilization: CPU utilisation 0.0–1.0
      memory_utilization  : memory utilisation 0.0–1.0
      health_score        : composite 0.0 (dead) – 1.0 (perfect)
      affinity_tags       : scheduling affinity tags (mirrors F3)
    """

    worker_id: str = ""
    status: WorkerHealthStatus = WorkerHealthStatus.HEALTHY
    active_leases: int = 0
    resource_utilization: float = 0.0
    memory_utilization: float = 0.0
    health_score: float = 1.0
    affinity_tags: List[str] = field(default_factory=list)


# ════════════════════════════════════════════════════════════════════
# AlertPayload — Structured alert for IAlertRouter
# ════════════════════════════════════════════════════════════════════


@dataclass
class AlertPayload:  # LAW-5, §15.13
    """Payload for an alert fired by the observability layer.

    Fields:
      alert_id       : unique alert identifier
      severity       : Severity level
      source_domain  : originating subsystem (f1/d8/f3/f4)
      condition_met  : human-readable description of the condition
      suppression_key: composite key for deduplication
      routing_target : EventBus topic or log sink
      metric_value   : value that triggered the alert
      threshold      : threshold that was crossed
      timestamp_ns   : when the alert was fired
    """

    alert_id: str = ""
    severity: Severity = Severity.INFO
    source_domain: str = ""
    condition_met: str = ""
    suppression_key: str = ""
    routing_target: str = ""
    metric_value: float = 0.0
    threshold: float = 0.0
    timestamp_ns: int = 0
