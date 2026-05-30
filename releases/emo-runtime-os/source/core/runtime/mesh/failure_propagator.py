"""GAP 1 — FailurePropagator: runtime failure propagation across the mesh.

Extends the D8.2 FailurePropagationPolicy with actual runtime
propagation — not just policy evaluation but real notification
of failures between services in the mesh.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, List, Optional

from core.runtime.mesh.mesh_protocol import MeshEnvelope, MeshMessageType, MeshProtocol
from core.runtime.mesh.service_registry import ServiceRegistry, ServiceStatus

logger = logging.getLogger("emo_ai.mesh.failure_propagator")


class FailurePropagator:
    """Propagates failures between services at runtime.

    When a service fails, this propagator:
      1. Records the failure
      2. Notifies dependent services
      3. Updates registry status
      4. Calls registered failure callbacks
    """

    def __init__(
        self,
        registry: Optional[ServiceRegistry] = None,
    ):
        self._registry = registry or ServiceRegistry()
        self._protocol = MeshProtocol()
        self._callbacks: Dict[str, List[Callable]] = {}
        self._failure_history: List[Dict[str, Any]] = []

    def on_failure(self, service: str, callback: Callable) -> None:
        """Register a callback for when a specific service fails."""
        if service not in self._callbacks:
            self._callbacks[service] = []
        self._callbacks[service].append(callback)

    def propagate(
        self,
        service: str,
        instance_id: str,
        error: str,
        notify_dependents: bool = True,
    ) -> List[str]:
        """Propagate a failure through the mesh.

        Args:
            service: Name of the failed service.
            instance_id: ID of the failed instance.
            error: Error description.
            notify_dependents: Whether to notify dependent services.

        Returns:
            List of services that were notified.
        """
        # Record the failure
        failure = {
            "service": service,
            "instance_id": instance_id,
            "error": error,
            "timestamp": time.time(),
        }
        self._failure_history.append(failure)

        # Update registry status
        instance = self._registry.get_instance(service, instance_id)
        if instance:
            instance.status = ServiceStatus.DOWN

        # Call registered callbacks
        notified = []
        if notify_dependents:
            for svc, callbacks in self._callbacks.items():
                for cb in callbacks:
                    try:
                        cb(failure)
                        notified.append(svc)
                    except Exception as e:
                        logger.error(
                            "Failure callback for %s raised: %s", svc, e,
                        )

        logger.warning(
            "Failure propagated: %s/%s — %s (notified: %s)",
            service, instance_id, error, notified,
        )
        return notified

    def recent_failures(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Return the most recent failures."""
        return self._failure_history[-limit:]

    def failure_count(self, service: str) -> int:
        """Return the number of recorded failures for a service."""
        return sum(
            1 for f in self._failure_history if f["service"] == service
        )
