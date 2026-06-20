"""Lifecycle Protocols.

Defines interfaces for health checking and graceful lifecycle management.

Ref: P10.2 — Reliability & Graceful Lifecycle
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from core.models.lifecycle import HealthCheckResult


class IHealthChecker(Protocol):
    """Protocol for component health checking."""

    def check_liveness(self) -> HealthCheckResult: ...

    def check_readiness(self) -> HealthCheckResult: ...


class ILifecycleManager(Protocol):
    """Protocol for graceful lifecycle management."""

    async def start(self) -> None: ...

    async def shutdown(self) -> None: ...

    def register_component(self, name: str, component: Any) -> None: ...
