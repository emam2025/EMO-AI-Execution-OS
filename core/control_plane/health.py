"""6.4 — HealthManager: monitors everything alive in the system.

Monitors:
  - Node health (alive, latency, error rate)
  - Worker health (heartbeat, active tasks, CPU/memory)
  - Mesh topology (node joins/leaves, cluster shape, partitions)
  - Hotspot detection (nodes with abnormal load)
  - Partition detection (network splits)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from core.control_plane.state.system_state import SystemStateBrain

logger = logging.getLogger("emo_ai.control_plane.health")


@dataclass
class HealthReport:
    """Health report for a single node."""
    node_id: str
    alive: bool = True
    latency_ms: float = 0.0
    error_rate: float = 0.0
    worker_count: int = 0
    active_executions: int = 0
    cpu_load: float = 0.0
    memory_used: int = 0
    status: str = "unknown"
    alerts: List[str] = field(default_factory=list)


@dataclass
class TopologyEvent:
    """A change in the mesh topology."""
    event_type: str  # join, leave, partition, heal
    node_id: str = ""
    timestamp: float = 0.0
    details: Dict[str, Any] = field(default_factory=dict)


class HealthManager:
    """Monitors the health of every node and worker.

    Produces health reports and topology events that the
    control plane uses to make decisions.
    """

    def __init__(self, state: Optional[SystemStateBrain] = None):
        self._state = state or SystemStateBrain()
        self._topology_history: List[TopologyEvent] = []
        self._alerts: List[Dict[str, Any]] = []
        self._callbacks: List[Callable] = []

    @property
    def state(self) -> SystemStateBrain:
        return self._state

    def on_alert(self, callback: Callable) -> None:
        """Register a callback for health alerts."""
        self._callbacks.append(callback)

    def _emit_alert(self, alert: Dict[str, Any]) -> None:
        self._alerts.append(alert)
        for cb in self._callbacks:
            try:
                cb(alert)
            except Exception:
                pass

    # ── Node Checks ──────────────────────────────────────────────

    def check_node(self, node_id: str, latency_ms: float = 0.0,
                    error_rate: float = 0.0) -> HealthReport:
        """Check health of a single node.

        Args:
            node_id: The node to check.
            latency_ms: Measured latency to this node.
            error_rate: Observed error rate from this node.

        Returns:
            HealthReport with status and any alerts.
        """
        node = self._state.get_node(node_id)
        if node is None:
            report = HealthReport(
                node_id=node_id,
                alive=False,
                status="unknown",
                alerts=["Node not registered"],
            )
            return report

        alerts: List[str] = []
        now = time.time()
        age = now - node.last_seen

        alive = age < 60.0 and node.status != "down"

        if not alive:
            alerts.append(f"Node unreachable ({age:.0f}s since last seen)")
            self._state.update_node_health(node_id, status="down", latency_ms=latency_ms)
            self._emit_alert({
                "type": "node_down",
                "node_id": node_id,
                "timestamp": now,
                "age": age,
            })
        else:
            self._state.update_node_health(node_id, status="active", latency_ms=latency_ms)

        workers = self._state.workers_by_node(node_id)
        worker_count = len(workers)
        active_execs = sum(
            1 for e in self._state.active_executions()
            if e.node_id == node_id
        )

        # Check for hotspots
        avg_cpu = 0.0
        avg_mem = 0
        for w in workers:
            avg_cpu += w.cpu_load
            avg_mem += w.memory_used
        if worker_count > 0:
            avg_cpu /= worker_count
            avg_mem //= worker_count

        if avg_cpu > 0.8:
            alerts.append(f"High CPU ({avg_cpu:.2f})")
            self._emit_alert({
                "type": "hotspot_cpu",
                "node_id": node_id,
                "cpu": avg_cpu,
                "timestamp": now,
            })

        if error_rate > 0.05:
            alerts.append(f"High error rate ({error_rate:.3f})")
            self._emit_alert({
                "type": "high_error_rate",
                "node_id": node_id,
                "error_rate": error_rate,
                "timestamp": now,
            })

        status = "degraded" if alerts else "healthy"

        return HealthReport(
            node_id=node_id,
            alive=alive,
            latency_ms=latency_ms,
            error_rate=error_rate,
            worker_count=worker_count,
            active_executions=active_execs,
            cpu_load=avg_cpu,
            memory_used=avg_mem,
            status=status,
            alerts=alerts,
        )

    def check_all(self) -> Dict[str, HealthReport]:
        """Check health of every known node."""
        reports = {}
        for nid in self._state.all_nodes():
            reports[nid] = self.check_node(nid)
        return reports

    # ── Topology Tracking ────────────────────────────────────────

    def record_topology_event(self, event_type: str, node_id: str,
                               details: Optional[Dict[str, Any]] = None) -> TopologyEvent:
        """Record a topology change event."""
        event = TopologyEvent(
            event_type=event_type,
            node_id=node_id,
            timestamp=time.time(),
            details=details or {},
        )
        self._topology_history.append(event)
        logger.info("Topology event: %s — %s", event_type, node_id)

        if event_type == "join":
            self._state.register_node(node_id, **(details or {}))
        elif event_type == "leave":
            self._state.update_node_health(node_id, status="down")

        return event

    def topology_events(self, limit: int = 50) -> List[TopologyEvent]:
        """Return recent topology events."""
        return self._topology_history[-limit:]

    def detect_partitions(self) -> List[str]:
        """Detect potential network partitions.

        A partition is suspected when a node's workers are all
        unreachable but other nodes can't reach it either.

        Returns:
            List of node_ids that may be partitioned.
        """
        partitioned = []
        for nid, node in self._state.all_nodes().items():
            if node.status in ("down", "unknown"):
                workers = self._state.workers_by_node(nid)
                if not workers:
                    # No workers assigned — check if other nodes see it
                    # For now: if status is down and no workers, suspect partition
                    if node.last_seen > 0:
                        partitioned.append(nid)
        return partitioned

    # ── Alerts ───────────────────────────────────────────────────

    def recent_alerts(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Return recent health alerts."""
        return self._alerts[-limit:]

    def status_summary(self) -> Dict[str, Any]:
        """Return a summary of overall system health."""
        reports = self.check_all()
        healthy = sum(1 for r in reports.values() if r.status == "healthy")
        degraded = sum(1 for r in reports.values() if r.status == "degraded")
        down = sum(1 for r in reports.values() if not r.alive)
        return {
            "total_nodes": len(reports),
            "healthy": healthy,
            "degraded": degraded,
            "down": down,
            "alerts": len(self._alerts),
            "partitions": self.detect_partitions(),
        }
