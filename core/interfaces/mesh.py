"""D8.1 — IServiceMesh: aggregate interface exposing all 5 services.

LAW 23-26: Mesh aggregates Scheduler, StateStore, Dispatcher, RetryHandler, LeaseManager.
FORBIDDEN: business logic, implementation, concrete references.

Source of Truth: core/runtime/services/mesh.py::ServiceMesh

Ref: DEVELOPER.md §15.15a D8.1
Ref: Canon LAW 23-26
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from core.interfaces.dispatcher import IExecutionDispatcher
    from core.interfaces.lease import IExecutionLeaseManager
    from core.interfaces.retry import IExecutionRetryHandler
    from core.interfaces.scheduler import IExecutionScheduler
    from core.interfaces.state_store import IExecutionStateStore


@runtime_checkable
class IServiceMesh(Protocol):
    """Aggregate interface exposing all 5 D8.1 services.

    Properties:
      scheduler       → IExecutionScheduler  (execution ordering)
      state_store     → IExecutionStateStore  (persistence + traces)
      dispatcher      → IExecutionDispatcher  (execution routing)
      retry_handler   → IExecutionRetryHandler  (retry semantics)
      lease_manager   → IExecutionLeaseManager  (distributed ownership)
    """

    @property
    def scheduler(self) -> IExecutionScheduler:
        ...

    @property
    def state_store(self) -> IExecutionStateStore:
        ...

    @property
    def dispatcher(self) -> IExecutionDispatcher:
        ...

    @property
    def retry_handler(self) -> IExecutionRetryHandler:
        ...

    @property
    def lease_manager(self) -> IExecutionLeaseManager:
        ...

    def get_service(self, name: str) -> Any:
        """Resolve a service by registered name."""
        ...
