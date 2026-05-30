"""Phase F4 — DashboardDataProvider implementation.  # LAW-5 # LAW-12

Implements IDashboardDataProvider: get_execution_timeline,
get_dag_visualization, get_worker_topology, get_failure_explorer.

All methods return snapshot data only — no side effects (RULE 1).

Ref: Canon LAW 5 (Observability), LAW 12 (Traceability), RULE 1
Ref: artifacts/design/f4/protocols/01_observability_protocols.py::IDashboardDataProvider
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

from core.runtime.models.observability_models import (
    DAGVisualizationResult,
    ExecutionTimelineSegment,
    ExecutionTimelineEvent,
    FailureExplorerResult,
    WorkerTopologySnapshot,
    WorkerTopologyView,
    TraceSpan,
)

logger = logging.getLogger("emo_ai.observability.dashboard")


class DashboardDataProvider:  # ←→ IDashboardDataProvider  # §15.13
    """Concrete implementation of IDashboardDataProvider.

    Read-only queries for the Runtime Dashboard.
    All methods are pure — no side effects (RULE 1).
    """

    def __init__(self) -> None:
        self._timelines: Dict[str, List[ExecutionTimelineEvent]] = {}
        self._dag_nodes: Dict[str, List[Dict[str, str]]] = {}
        self._dag_edges: Dict[str, List[Tuple[str, str]]] = {}
        self._workers: Dict[str, WorkerTopologySnapshot] = {}
        self._failures: Dict[str, FailureExplorerResult] = {}
        self._spans: Dict[str, TraceSpan] = {}

    # ── get_execution_timeline ──────────────────────────────────

    def get_execution_timeline(  # LAW-12
        self,
        execution_id: str,
        since_ns: Optional[int] = None,
    ) -> ExecutionTimelineSegment:
        events = self._timelines.get(execution_id, [])
        if since_ns is not None:
            events = [e for e in events if e.timestamp_ns >= since_ns]

        nodes = [
            {
                "node_id": e.node_id,
                "transition": e.state_transition.value,
                "worker_id": e.worker_id,
                "span_id": e.span_id,
                "error": e.error_message,
            }
            for e in events
        ]

        error_count = sum(1 for e in events if e.state_transition.value == "running_to_failed")
        total_ms = 0.0
        if events:
            first = events[0].timestamp_ns
            last = events[-1].timestamp_ns
            total_ms = (last - first) / 1_000_000

        return ExecutionTimelineSegment(
            execution_id=execution_id,
            nodes=nodes,
            total_duration_ms=total_ms,
            error_count=error_count,
        )

    # ── get_dag_visualization ───────────────────────────────────

    def get_dag_visualization(  # RULE-1
        self,
        dag_id: str,
        execution_id: Optional[str] = None,
    ) -> DAGVisualizationResult:
        nodes = self._dag_nodes.get(dag_id, [])
        edges = self._dag_edges.get(dag_id, [])

        lookup_key = execution_id or dag_id
        timeline = self._timelines.get(lookup_key, [])
        status_map: Dict[str, str] = {}
        for e in timeline:
            status_map[e.node_id] = e.state_transition.value

        enriched_nodes = []
        for n in nodes:
            node_copy = dict(n)
            if n.get("id") in status_map:
                node_copy["status"] = status_map[n["id"]]
            enriched_nodes.append(node_copy)

        return DAGVisualizationResult(
            dag_id=dag_id,
            nodes=enriched_nodes,
            edges=edges,
            critical_path_ms=self._compute_critical_path(enriched_nodes, edges),
        )

    # ── get_worker_topology ─────────────────────────────────────

    def get_worker_topology(  # LAW-5
        self,
        worker_ids: Optional[List[str]] = None,
    ) -> WorkerTopologyView:
        workers = list(self._workers.values())
        if worker_ids is not None:
            id_set = set(worker_ids)
            workers = [w for w in workers if w.worker_id in id_set]

        worker_dicts = [
            {
                "worker_id": w.worker_id,
                "status": w.status.value,
                "active_leases": str(w.active_leases),
                "resource_utilization": f"{w.resource_utilization:.2f}",
                "health_score": f"{w.health_score:.2f}",
            }
            for w in workers
        ]

        healthy = sum(1 for w in workers if w.status.value == "healthy")
        degraded = sum(1 for w in workers if w.status.value == "degraded")
        offline = sum(1 for w in workers if w.status.value in ("offline", "draining"))

        return WorkerTopologyView(
            workers=worker_dicts,
            healthy_count=healthy,
            degraded_count=degraded,
            offline_count=offline,
        )

    # ── get_failure_explorer ────────────────────────────────────

    def get_failure_explorer(  # LAW-5
        self,
        trace_id: str,
        span_id: Optional[str] = None,
    ) -> FailureExplorerResult:
        failure = self._failures.get(trace_id)
        if failure is not None:
            return failure

        key = f"{trace_id}:{span_id}" if span_id else trace_id
        failure = self._failures.get(key)
        if failure is not None:
            return failure

        return FailureExplorerResult(
            failure_id=trace_id,
            trace_id=trace_id,
            root_span_id=span_id,
            error_message="No failure data found for trace",
            affected_spans=[],
            suggested_remedy="Verify trace_id is correct",
        )

    # ── Data injection (for testing / EventBus subscribers) ─────

    def record_timeline_event(self, event: ExecutionTimelineEvent) -> None:
        execution_id = event.node_id.split(":")[0] if ":" in event.node_id else event.node_id
        if execution_id not in self._timelines:
            self._timelines[execution_id] = []
        self._timelines[execution_id].append(event)

    def register_dag(
        self,
        dag_id: str,
        nodes: List[Dict[str, str]],
        edges: Optional[List[Tuple[str, str]]] = None,
    ) -> None:
        self._dag_nodes[dag_id] = nodes
        self._dag_edges[dag_id] = edges or []

    def update_worker(self, snapshot: WorkerTopologySnapshot) -> None:
        self._workers[snapshot.worker_id] = snapshot

    def record_failure(self, result: FailureExplorerResult) -> None:
        self._failures[result.trace_id] = result
        if result.root_span_id:
            self._failures[f"{result.trace_id}:{result.root_span_id}"] = result

    def record_span(self, span: TraceSpan) -> None:
        self._spans[span.span_id] = span

    def reset(self) -> None:
        self._timelines.clear()
        self._dag_nodes.clear()
        self._dag_edges.clear()
        self._workers.clear()
        self._failures.clear()

    @staticmethod
    def _compute_critical_path(
        nodes: List[Dict[str, str]],
        edges: List[Tuple[str, str]],
    ) -> float:
        if not nodes:
            return 0.0

        duration_map: Dict[str, float] = {}
        for n in nodes:
            try:
                duration_map[n["id"]] = float(n.get("duration_ms", 0))
            except (ValueError, KeyError):
                duration_map[n.get("id", "")] = 0.0

        longest_path: Dict[str, float] = {}
        for n_id in duration_map:
            longest_path[n_id] = duration_map[n_id]

        for _ in range(len(nodes)):
            for src, dst in edges:
                if src in longest_path and dst in longest_path:
                    candidate = longest_path[src] + duration_map.get(dst, 0)
                    if candidate > longest_path[dst]:
                        longest_path[dst] = candidate

        return max(longest_path.values()) if longest_path else 0.0
