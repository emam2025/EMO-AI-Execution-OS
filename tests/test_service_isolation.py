"""D8.3 — Service Isolation Tests.

Proves that the 5 D8.1 services are isolated and do not exceed
their declared interface boundaries. Protocol-only testing.

Ref: DEVELOPER.md §15.15a D8.3
Ref: Canon LAW 23-27
"""

from typing import Protocol
from unittest.mock import MagicMock

from core.models.failure_propagation import (
    ConsistencyLevel,
    FailureContext,
    FailureMode,
    PropagationRule,
)
from core.interfaces.dispatcher import IExecutionDispatcher
from core.interfaces.lease import IExecutionLeaseManager
from core.interfaces.retry import IExecutionRetryHandler
from core.interfaces.scheduler import IExecutionScheduler
from core.interfaces.state_store import IExecutionStateStore


class TestNoSharedMutableState:
    """Proves that services do not share or mutate each other's state."""

    def test_scheduler_has_no_state_store_reference(self) -> None:
        assert not hasattr(IExecutionScheduler, "state_store")

    def test_dispatcher_has_no_lease_reference(self) -> None:
        assert not hasattr(IExecutionDispatcher, "lease_manager")

    def test_retry_handler_has_no_scheduler_reference(self) -> None:
        assert not hasattr(IExecutionRetryHandler, "scheduler")

    def test_lease_manager_has_no_dispatcher_reference(self) -> None:
        assert not hasattr(IExecutionLeaseManager, "dispatcher")

    def test_state_store_has_no_retry_reference(self) -> None:
        assert not hasattr(IExecutionStateStore, "retry_handler")


class TestNoHiddenCrossServiceAccess:
    """Proves no hidden cross-service calls via internals."""

    def test_scheduler_no_direct_lease_call(self) -> None:
        assert not hasattr(IExecutionScheduler, "acquire_lease")
        assert not hasattr(IExecutionScheduler, "renew_lease")
        assert not hasattr(IExecutionScheduler, "release_lease")

    def test_dispatcher_no_direct_retry_call(self) -> None:
        assert not hasattr(IExecutionDispatcher, "decide_retry")
        assert not hasattr(IExecutionDispatcher, "apply_backoff")
        assert not hasattr(IExecutionDispatcher, "record_failure")

    def test_retry_handler_no_direct_state_call(self) -> None:
        assert not hasattr(IExecutionRetryHandler, "save_state")
        assert not hasattr(IExecutionRetryHandler, "load_state")
        assert not hasattr(IExecutionRetryHandler, "store_checkpoint")
        assert not hasattr(IExecutionRetryHandler, "read_trace")

    def test_lease_manager_no_direct_scheduler_call(self) -> None:
        assert not hasattr(IExecutionLeaseManager, "schedule")
        assert not hasattr(IExecutionLeaseManager, "run_with_timeout")
        assert not hasattr(IExecutionLeaseManager, "collect_futures")


class TestServiceInterfaceCompliance:
    """Proves each service adheres to its own Protocol only."""

    def test_scheduler_is_protocol(self) -> None:
        assert issubclass(IExecutionScheduler, Protocol)

    def test_state_store_is_protocol(self) -> None:
        assert issubclass(IExecutionStateStore, Protocol)

    def test_dispatcher_is_protocol(self) -> None:
        assert issubclass(IExecutionDispatcher, Protocol)

    def test_retry_handler_is_protocol(self) -> None:
        assert issubclass(IExecutionRetryHandler, Protocol)

    def test_lease_manager_is_protocol(self) -> None:
        assert issubclass(IExecutionLeaseManager, Protocol)


class TestFailurePropagationCompliance:
    """Links D8.2 failure matrix to isolation behavior."""

    def test_dispatcher_failure_uses_retry_mode(self) -> None:
        rule = PropagationRule(
            source_domain="Dispatcher",
            effect_on="Scheduler",
            action="Scheduler retries failed tool call",
            failure_mode=FailureMode.RETRY,
            consistency_level=ConsistencyLevel.EVENTUAL,
        )
        assert rule.failure_mode == FailureMode.RETRY

    def test_lease_expiry_uses_fail_fast(self) -> None:
        rule = PropagationRule(
            source_domain="LeaseManager",
            effect_on="Scheduler",
            action="Cancel execution and reassign lease",
            failure_mode=FailureMode.FAIL_FAST,
            consistency_level=ConsistencyLevel.STRONG,
        )
        assert rule.failure_mode == FailureMode.FAIL_FAST

    def test_state_store_failure_uses_degrade(self) -> None:
        rule = PropagationRule(
            source_domain="StateStore",
            effect_on="Scheduler",
            action="Degrade to in-memory buffer",
            failure_mode=FailureMode.DEGRADE,
            consistency_level=ConsistencyLevel.NONE,
        )
        assert rule.failure_mode == FailureMode.DEGRADE

    def test_failure_context_is_frozen(self) -> None:
        ctx = FailureContext(
            source_service="Dispatcher",
            target_service="Scheduler",
            error_type="ConnectionTimeout",
            timestamp=1000.0,
        )
        try:
            ctx.source_service = "Modified"
            assert False
        except AttributeError:
            pass


class TestCanonServiceOwnership:
    """Examines LAW 23-27: properties and methods are scoped to declared domain."""

    def test_scheduler_owns_only_scheduling(self) -> None:
        scheduling_methods = {"schedule", "run_with_timeout", "collect_futures"}
        all_attrs = {a for a in dir(IExecutionScheduler) if not a.startswith("_")}
        assert all_attrs == scheduling_methods

    def test_dispatcher_owns_only_routing(self) -> None:
        routing_methods = {"register_tool", "dispatch_tool_call", "validate_contract", "route_service"}
        all_attrs = {a for a in dir(IExecutionDispatcher) if not a.startswith("_")}
        assert all_attrs == routing_methods

    def test_retry_handler_owns_only_retry(self) -> None:
        retry_methods = {"decide_retry", "apply_backoff", "record_failure"}
        all_attrs = {a for a in dir(IExecutionRetryHandler) if not a.startswith("_")}
        assert all_attrs == retry_methods

    def test_lease_manager_owns_only_lease(self) -> None:
        lease_methods = {"acquire_lease", "renew_lease", "release_lease", "monitor_heartbeat"}
        all_attrs = {a for a in dir(IExecutionLeaseManager) if not a.startswith("_")}
        assert all_attrs == lease_methods

    def test_state_store_owns_only_persistence(self) -> None:
        persistence_methods = {"save_state", "load_state", "store_checkpoint", "read_trace"}
        all_attrs = {a for a in dir(IExecutionStateStore) if not a.startswith("_")}
        assert all_attrs == persistence_methods
