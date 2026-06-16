"""D8.1 — Official Service Interface Protocol Existence Tests.

Verifies that all 6 D8.1 Protocol classes exist and are runtime-checkable.
Protocol-only — no concrete implementations, no business logic.

Ref: DEVELOPER.md §15.15a D8.1
Ref: Canon LAW 2 (Interface Authority)
"""

from typing import Protocol


class TestSchedulerProtocol:
    def test_scheduler_protocol_exists(self) -> None:
        from core.interfaces.scheduler import IExecutionScheduler

        assert issubclass(IExecutionScheduler, Protocol)
        assert hasattr(IExecutionScheduler, "schedule")
        assert hasattr(IExecutionScheduler, "run_with_timeout")
        assert hasattr(IExecutionScheduler, "collect_futures")


class TestStateStoreProtocol:
    def test_state_store_protocol_exists(self) -> None:
        from core.interfaces.state_store import IExecutionStateStore

        assert issubclass(IExecutionStateStore, Protocol)
        assert hasattr(IExecutionStateStore, "save_state")
        assert hasattr(IExecutionStateStore, "load_state")
        assert hasattr(IExecutionStateStore, "store_checkpoint")
        assert hasattr(IExecutionStateStore, "read_trace")


class TestDispatcherProtocol:
    def test_dispatcher_protocol_exists(self) -> None:
        from core.interfaces.dispatcher import IExecutionDispatcher

        assert issubclass(IExecutionDispatcher, Protocol)
        assert hasattr(IExecutionDispatcher, "dispatch_tool_call")
        assert hasattr(IExecutionDispatcher, "validate_contract")
        assert hasattr(IExecutionDispatcher, "route_service")


class TestRetryHandlerProtocol:
    def test_retry_handler_protocol_exists(self) -> None:
        from core.interfaces.retry import IExecutionRetryHandler

        assert issubclass(IExecutionRetryHandler, Protocol)
        assert hasattr(IExecutionRetryHandler, "decide_retry")
        assert hasattr(IExecutionRetryHandler, "apply_backoff")
        assert hasattr(IExecutionRetryHandler, "record_failure")


class TestLeaseManagerProtocol:
    def test_lease_manager_protocol_exists(self) -> None:
        from core.interfaces.lease import IExecutionLeaseManager

        assert issubclass(IExecutionLeaseManager, Protocol)
        assert hasattr(IExecutionLeaseManager, "acquire_lease")
        assert hasattr(IExecutionLeaseManager, "renew_lease")
        assert hasattr(IExecutionLeaseManager, "release_lease")
        assert hasattr(IExecutionLeaseManager, "monitor_heartbeat")


class TestServiceMeshAggregate:
    def test_service_mesh_aggregate_exists(self) -> None:
        from core.interfaces.mesh import IServiceMesh

        assert issubclass(IServiceMesh, Protocol)
        assert hasattr(IServiceMesh, "scheduler")
        assert hasattr(IServiceMesh, "state_store")
        assert hasattr(IServiceMesh, "dispatcher")
        assert hasattr(IServiceMesh, "retry_handler")
        assert hasattr(IServiceMesh, "lease_manager")
        assert hasattr(IServiceMesh, "get_service")
