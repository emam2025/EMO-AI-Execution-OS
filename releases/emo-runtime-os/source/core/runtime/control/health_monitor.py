"""GAP 2 — HealthMonitor: service and worker health tracking.

Monitors all system components and reports unhealthy ones.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("emo_ai.control.health")


class HealthMonitor:
    """Monitors health of all system components.

    Tracks heartbeats, checks timeouts, and reports status
    for services, workers, and infrastructure.
    """

    def __init__(self, heartbeat_ttl: float = 30.0):
        self._heartbeat_ttl = heartbeat_ttl
        self._heartbeats: Dict[str, float] = {}
        self._status: Dict[str, str] = {}
        self._alerts: List[Dict[str, Any]] = []

    def record_heartbeat(self, component: str) -> None:
        """Record a heartbeat from a component."""
        self._heartbeats[component] = time.time()
        self._status[component] = "healthy"

    def mark_unhealthy(self, component: str, reason: str) -> None:
        """Mark a component as unhealthy."""
        self._status[component] = "unhealthy"
        self._alerts.append({
            "component": component,
            "status": "unhealthy",
            "reason": reason,
            "timestamp": time.time(),
        })

    def mark_degraded(self, component: str, reason: str) -> None:
        """Mark a component as degraded."""
        self._status[component] = "degraded"
        self._alerts.append({
            "component": component,
            "status": "degraded",
            "reason": reason,
            "timestamp": time.time(),
        })

    def is_healthy(self, component: str) -> bool:
        """Check if a component is healthy."""
        status = self._status.get(component, "unknown")
        if status == "unhealthy":
            return False
        hb = self._heartbeats.get(component)
        if hb and time.time() - hb > self._heartbeat_ttl:
            return False
        return status != "unhealthy"

    def check_all(self) -> List[str]:
        """Check all tracked components. Return list of unhealthy names."""
        unhealthy = []
        now = time.time()
        for component, last_hb in list(self._heartbeats.items()):
            if now - last_hb > self._heartbeat_ttl:
                unhealthy.append(component)
                self._status[component] = "unhealthy"
        for component, status in list(self._status.items()):
            if status == "unhealthy":
                unhealthy.append(component)
        return list(set(unhealthy))

    def status(self) -> Dict[str, str]:
        """Return the status of all tracked components."""
        result = dict(self._status)
        for component in self._heartbeats:
            if component not in result:
                result[component] = "healthy"
        return result

    def recent_alerts(self, limit: int = 20) -> List[Dict[str, Any]]:
        return self._alerts[-limit:]
