"""Phase F4 — Observability Layer package.  # LAW-5 # LAW-12

Exports all observability components for CompositionRoot wiring.

Phase F4 additions (EXEC-DIRECTIVE-PHASE-F4-001):
  - DistributedTracer:      Trace/span creation + reconstruction
  - RuntimeDashboardService: Health, metrics, real-time subscription
  - ExecutionTimelineBuilder: Chronological event reconstruction
  - FailureExplorer:         Root cause analysis + export
  - WorkerTopologyViewer:    Cluster graph + lease mapping + partition detection

Ref: Canon LAW 5 (Observability), LAW 12 (Traceability)
Ref: ROADMAP Phase F4
"""

from core.runtime.observability.trace_collector import TraceCollector
from core.runtime.observability.telemetry_aggregator import TelemetryAggregator
from core.runtime.observability.dashboard_data_provider import DashboardDataProvider
from core.runtime.observability.alert_router import AlertRouter
from core.runtime.observability.aggregation_state_machine import (
    AggregationState,
    AggregationStateMachine,
)
from core.runtime.observability.backpressure_sampler import BackpressureSampler
from core.runtime.observability.distributed_tracer import DistributedTracer
from core.runtime.observability.dashboard_service import RuntimeDashboardService
from core.runtime.observability.timeline_builder import ExecutionTimelineBuilder
from core.runtime.observability.failure_explorer import FailureExplorer
from core.runtime.observability.topology_viewer import WorkerTopologyViewer

__all__ = [
    "TraceCollector",
    "TelemetryAggregator",
    "DashboardDataProvider",
    "AlertRouter",
    "AggregationState",
    "AggregationStateMachine",
    "BackpressureSampler",
    "DistributedTracer",
    "RuntimeDashboardService",
    "ExecutionTimelineBuilder",
    "FailureExplorer",
    "WorkerTopologyViewer",
]
