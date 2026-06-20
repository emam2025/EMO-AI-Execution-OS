"""Lifecycle Infrastructure — Graceful Shutdown & Health Checks.

Manages component lifecycle with LIFO shutdown and exception isolation.

Ref: P10.2 — Reliability & Graceful Lifecycle
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.models.lifecycle import ComponentStatus, HealthCheckResult


class LifecycleManager:
    """Manages graceful startup and shutdown of components.

    Components are shut down in reverse registration order (LIFO).
    Exception isolation: one component's failure does not block others.
    """

    def __init__(self) -> None:
        self._components: Dict[str, Any] = {}
        self._component_status: Dict[str, ComponentStatus] = {}
        self._status = ComponentStatus.STOPPED
        self._shutdown_errors: List[Dict[str, Any]] = []

    @property
    def status(self) -> ComponentStatus:
        return self._status

    def register_component(self, name: str, component: Any) -> None:
        """Register a component for lifecycle management."""
        self._components[name] = component
        self._component_status[name] = ComponentStatus.STARTING

    async def start(self) -> None:
        """Start all registered components."""
        if self._status == ComponentStatus.READY:
            return

        self._status = ComponentStatus.STARTING

        for name, component in self._components.items():
            self._component_status[name] = ComponentStatus.READY

        self._status = ComponentStatus.READY

    async def shutdown(self) -> None:
        """Shut down all components in reverse registration order (LIFO).

        Exception isolation: one component's failure is logged but does not
        prevent other components from being shut down.
        """
        if self._status in (ComponentStatus.STOPPING, ComponentStatus.STOPPED):
            return

        self._status = ComponentStatus.STOPPING
        self._shutdown_errors.clear()

        # LIFO: reverse registration order
        component_names = list(self._components.keys())
        reversed_names = list(reversed(component_names))

        for name in reversed_names:
            component = self._components[name]
            self._component_status[name] = ComponentStatus.STOPPING

            try:
                # Try common shutdown methods
                if hasattr(component, "unsubscribe_from_events"):
                    await component.unsubscribe_from_events()
                elif hasattr(component, "close"):
                    await component.close()
                elif hasattr(component, "shutdown"):
                    await component.shutdown()
            except Exception as e:
                self._shutdown_errors.append({
                    "component": name,
                    "error": str(e),
                    "type": type(e).__name__,
                })

            self._component_status[name] = ComponentStatus.STOPPED

        self._status = ComponentStatus.STOPPED

    def get_component_status(self, name: str) -> Optional[ComponentStatus]:
        """Get the status of a specific component."""
        return self._component_status.get(name)

    def get_shutdown_errors(self) -> List[Dict[str, Any]]:
        """Get any errors that occurred during shutdown."""
        return list(self._shutdown_errors)


class HealthChecker:
    """Checks the health of a LifecycleManager and its components."""

    def __init__(self, lifecycle_manager: LifecycleManager) -> None:
        self._lifecycle = lifecycle_manager

    def check_liveness(self) -> HealthCheckResult:
        """Check if the system is alive (not stopped)."""
        status = self._lifecycle.status
        if status == ComponentStatus.STOPPED:
            return HealthCheckResult(
                component_name="system",
                status=ComponentStatus.DEGRADED,
                message="System is stopped",
            )
        return HealthCheckResult(
            component_name="system",
            status=status,
            message="System is alive",
        )

    def check_readiness(self) -> HealthCheckResult:
        """Check if all components are ready to serve requests."""
        status = self._lifecycle.status

        if status != ComponentStatus.READY:
            return HealthCheckResult(
                component_name="system",
                status=status,
                message=f"System is not ready: {status.value}",
            )

        # Check individual components
        degraded_components = []
        for name in self._lifecycle._components:
            comp_status = self._lifecycle.get_component_status(name)
            if comp_status != ComponentStatus.READY:
                degraded_components.append(f"{name}:{comp_status.value}")

        if degraded_components:
            return HealthCheckResult(
                component_name="system",
                status=ComponentStatus.DEGRADING,
                message=f"Degraded components: {', '.join(degraded_components)}",
            )

        return HealthCheckResult(
            component_name="system",
            status=ComponentStatus.READY,
            message="All components ready",
        )
