"""6.1 — SystemStateBrain: global truth model of the entire system.

Not a cache. Not a snapshot.
This is the single source of truth for the control plane's view
of the system at any moment.

Contains:
  - Worker topology (which workers exist, their state, load)
  - Active executions (what's running, where, since when)
  - Node health (live/degraded/down per node)
  - Mesh topology (which nodes are connected, latency, routes)
  - Load metrics (CPU, memory, execution rate per node)
  - Failure clusters (which nodes/tasks are failing together)

All mutations go through events so the system remains observable.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from core.security.capabilities import TrustLevel


@dataclass
class WorkerInfo:
    """Truth record for a single worker."""
    worker_id: str
    node_id: str = ""
    status: str = "unknown"
    cpu_load: float = 0.0
    memory_used: int = 0
    active_tasks: int = 0
    capacity: int = 5
    error_rate: float = 0.0
    started_at: float = 0.0
    last_heartbeat: float = 0.0
    tags: Dict[str, str] = field(default_factory=dict)
    trust_level: TrustLevel = TrustLevel.TRUSTED


@dataclass
class ExecutionInfo:
    """Truth record for a single execution."""
    execution_id: str
    dag_id: str = ""
    worker_id: str = ""
    node_id: str = ""
    status: str = "pending"
    submitted_at: float = 0.0
    started_at: float = 0.0
    completed_at: float = 0.0
    error: str = ""
    retry_count: int = 0
    strategy: str = "balanced"


@dataclass
class NodeInfo:
    """Truth record for a mesh node."""
    node_id: str
    host: str = ""
    port: int = 0
    status: str = "unknown"
    latency_ms: float = 0.0
    worker_count: int = 0
    last_seen: float = 0.0
    version: str = ""


@dataclass
class FailureCluster:
    """A group of related failures in the system."""
    cluster_id: str
    nodes: List[str] = field(default_factory=list)
    executions: List[str] = field(default_factory=list)
    error_pattern: str = ""
    first_seen: float = 0.0
    last_seen: float = 0.0
    count: int = 0


@dataclass
class LoadMetrics:
    """Aggregate load metrics for a node or the whole system."""
    cpu_avg: float = 0.0
    memory_avg: int = 0
    execution_rate: float = 0.0
    error_rate: float = 0.0
    queue_depth: int = 0
    active_workers: int = 0
    total_workers: int = 0


class SystemStateBrain:
    """The global truth model of the entire system.

    Design rules:
      - State is event-derived (mutations fire callbacks)
      - State is readable without locks (snapshot pattern)
      - State is the ONLY source of truth for decisions
    """

    def __init__(self):
        self._lock = threading.Lock()

        # Core state
        self._workers: Dict[str, WorkerInfo] = {}
        self._executions: Dict[str, ExecutionInfo] = {}
        self._nodes: Dict[str, NodeInfo] = {}
        self._failure_clusters: Dict[str, FailureCluster] = {}
        self._load_metrics: Dict[str, LoadMetrics] = {}
        self._events: List[Callable] = []
        self._started_at: float = time.time()

    # ── Events ────────────────────────────────────────────────────

    def on_state_change(self, callback: Callable) -> None:
        """Register a callback for state changes."""
        self._events.append(callback)

    def _emit(self, event_type: str, data: Dict[str, Any]) -> None:
        for cb in self._events:
            try:
                cb({"type": event_type, "data": data, "timestamp": time.time()})
            except Exception:
                pass

    # ── Workers ───────────────────────────────────────────────────

    def register_worker(self, worker_id: str, node_id: str = "",
                        capacity: int = 5, tags: Optional[Dict[str, str]] = None,
                        trust_level: Optional[TrustLevel] = None) -> WorkerInfo:
        with self._lock:
            info = WorkerInfo(
                worker_id=worker_id,
                node_id=node_id,
                status="active",
                capacity=capacity,
                started_at=time.time(),
                last_heartbeat=time.time(),
                tags=tags or {},
                trust_level=trust_level or TrustLevel.TRUSTED,
            )
            self._workers[worker_id] = info
        self._emit("worker_registered", {"worker_id": worker_id, "node_id": node_id, "trust_level": info.trust_level.value})
        return info

    def remove_worker(self, worker_id: str) -> bool:
        with self._lock:
            if worker_id not in self._workers:
                return False
            del self._workers[worker_id]
        self._emit("worker_removed", {"worker_id": worker_id})
        return True

    def update_worker_heartbeat(self, worker_id: str, cpu_load: float = 0.0,
                                 memory_used: int = 0) -> bool:
        with self._lock:
            w = self._workers.get(worker_id)
            if w is None:
                return False
            w.last_heartbeat = time.time()
            w.cpu_load = cpu_load
            w.memory_used = memory_used
            w.status = "active"
        return True

    def get_worker(self, worker_id: str) -> Optional[WorkerInfo]:
        with self._lock:
            w = self._workers.get(worker_id)
            return w  # returns None or the dataclass (immutable-enough)

    def all_workers(self) -> Dict[str, WorkerInfo]:
        with self._lock:
            return dict(self._workers)

    def workers_by_node(self, node_id: str) -> List[WorkerInfo]:
        with self._lock:
            return [w for w in self._workers.values() if w.node_id == node_id]

    def healthy_workers(self) -> List[WorkerInfo]:
        with self._lock:
            now = time.time()
            return [
                w for w in self._workers.values()
                if w.status == "active" and (now - w.last_heartbeat) < 30.0
            ]

    # ── Executions ────────────────────────────────────────────────

    def register_execution(self, execution_id: str, dag_id: str = "",
                            strategy: str = "balanced") -> ExecutionInfo:
        with self._lock:
            info = ExecutionInfo(
                execution_id=execution_id,
                dag_id=dag_id,
                status="submitted",
                submitted_at=time.time(),
                strategy=strategy,
            )
            self._executions[execution_id] = info
        self._emit("execution_registered", {"execution_id": execution_id})
        return info

    def update_execution(self, execution_id: str, **updates) -> bool:
        with self._lock:
            ex = self._executions.get(execution_id)
            if ex is None:
                return False
            for k, v in updates.items():
                if hasattr(ex, k):
                    setattr(ex, k, v)
        self._emit("execution_updated", {"execution_id": execution_id, **updates})
        return True

    def get_execution(self, execution_id: str) -> Optional[ExecutionInfo]:
        with self._lock:
            ex = self._executions.get(execution_id)
            return ex

    def active_executions(self) -> List[ExecutionInfo]:
        with self._lock:
            return [e for e in self._executions.values() if e.status == "running"]

    def all_executions(self) -> Dict[str, ExecutionInfo]:
        with self._lock:
            return dict(self._executions)

    # ── Nodes ─────────────────────────────────────────────────────

    def register_node(self, node_id: str, host: str = "", port: int = 0) -> NodeInfo:
        with self._lock:
            info = NodeInfo(
                node_id=node_id,
                host=host,
                port=port,
                status="active",
                last_seen=time.time(),
            )
            self._nodes[node_id] = info
        self._emit("node_registered", {"node_id": node_id})
        return info

    def update_node_health(self, node_id: str, status: str = "",
                            latency_ms: float = 0.0) -> bool:
        with self._lock:
            n = self._nodes.get(node_id)
            if n is None:
                return False
            if status:
                n.status = status
            n.latency_ms = latency_ms
            n.last_seen = time.time()
        return True

    def get_node(self, node_id: str) -> Optional[NodeInfo]:
        with self._lock:
            n = self._nodes.get(node_id)
            return n

    def all_nodes(self) -> Dict[str, NodeInfo]:
        with self._lock:
            return dict(self._nodes)

    def healthy_nodes(self) -> List[NodeInfo]:
        with self._lock:
            now = time.time()
            return [
                n for n in self._nodes.values()
                if n.status == "active" and (now - n.last_seen) < 60.0
            ]

    # ── Failure Clusters ──────────────────────────────────────────

    def record_failure(self, node_id: str, execution_id: str, error: str) -> str:
        """Record a failure and find/create its cluster."""
        cluster_id = f"fc-{node_id}-{hash(error) % 10000}"
        with self._lock:
            now = time.time()
            if cluster_id in self._failure_clusters:
                fc = self._failure_clusters[cluster_id]
                if node_id not in fc.nodes:
                    fc.nodes.append(node_id)
                if execution_id not in fc.executions:
                    fc.executions.append(execution_id)
                fc.count += 1
                fc.last_seen = now
                fc.error_pattern = error[:200]
            else:
                fc = FailureCluster(
                    cluster_id=cluster_id,
                    nodes=[node_id],
                    executions=[execution_id],
                    error_pattern=error[:200],
                    first_seen=now,
                    last_seen=now,
                    count=1,
                )
                self._failure_clusters[cluster_id] = fc
        self._emit("failure_recorded", {"cluster_id": cluster_id, "node_id": node_id})
        return cluster_id

    def failure_clusters(self) -> Dict[str, FailureCluster]:
        with self._lock:
            return dict(self._failure_clusters)

    # ── Load Metrics ──────────────────────────────────────────────

    def update_load_metrics(self, node_id: str, metrics: LoadMetrics) -> None:
        with self._lock:
            self._load_metrics[node_id] = metrics

    def get_load_metrics(self, node_id: str) -> Optional[LoadMetrics]:
        with self._lock:
            return self._load_metrics.get(node_id)

    def aggregate_load(self) -> LoadMetrics:
        with self._lock:
            if not self._load_metrics:
                return LoadMetrics()
            total = LoadMetrics()
            count = len(self._load_metrics)
            for m in self._load_metrics.values():
                total.cpu_avg += m.cpu_avg
                total.memory_avg += m.memory_avg
                total.execution_rate += m.execution_rate
                total.error_rate += m.error_rate
                total.queue_depth += m.queue_depth
                total.active_workers += m.active_workers
                total.total_workers += m.total_workers
            if count:
                total.cpu_avg /= count
                total.memory_avg //= count
                total.execution_rate /= count
                total.error_rate /= count
            return total

    # ── Snapshot ──────────────────────────────────────────────────

    def snapshot(self) -> Dict[str, Any]:
        """Return a complete snapshot of the system state.

        This is the "truth model" that the reconciler and orchestrator
        use to make decisions.
        """
        with self._lock:
            return {
                "timestamp": time.time(),
                "uptime": time.time() - self._started_at,
                "workers": {
                    wid: {
                        "status": w.status,
                        "node_id": w.node_id,
                        "cpu_load": w.cpu_load,
                        "active_tasks": w.active_tasks,
                        "capacity": w.capacity,
                    }
                    for wid, w in self._workers.items()
                },
                "executions": {
                    eid: {
                        "status": e.status,
                        "worker_id": e.worker_id,
                        "node_id": e.node_id,
                        "retry_count": e.retry_count,
                    }
                    for eid, e in self._executions.items()
                },
                "nodes": {
                    nid: {
                        "status": n.status,
                        "latency_ms": n.latency_ms,
                        "worker_count": sum(1 for w in self._workers.values() if w.node_id == nid),
                    }
                    for nid, n in self._nodes.items()
                },
                "load_metrics": {
                    nid: {
                        "cpu_avg": m.cpu_avg,
                        "execution_rate": m.execution_rate,
                        "error_rate": m.error_rate,
                    }
                    for nid, m in self._load_metrics.items()
                },
                "failure_clusters": {
                    cid: {
                        "count": c.count,
                        "nodes": c.nodes,
                        "error_pattern": c.error_pattern[:60],
                    }
                    for cid, c in self._failure_clusters.items()
                },
            }
