"""D8.3 — Execution Tests.

Tests that verify runtime execution works correctly.
These tests actually instantiate and execute service code.

Ref: Canon LAW 23-27 (Service Ownership)
Ref: Canon LAW 10 (Workers are unreliable)
"""

import pytest

from core.interfaces.failure_propagation import FailurePropagationPolicy


# ── D8.3.7 — Protocol Compliance (Implementation satisfies Protocol) ──


class TestImplementationSatisfiesProtocol:
    """Verify each implementation structurally satisfies its Protocol.

    Uses Protocol structural subtyping: a class satisfies a Protocol
    if it has all the methods with matching signatures.
    """

    def test_scheduler_satisfies_protocol(self):
        from core.interfaces.scheduler import IExecutionScheduler
        from core.runtime.services.scheduler import ExecutionScheduler
        assert isinstance(ExecutionScheduler(), IExecutionScheduler)

    def test_dispatcher_satisfies_protocol(self):
        from core.interfaces.dispatcher import IExecutionDispatcher
        from core.runtime.services.tool_dispatcher import ExecutionToolDispatcher
        assert isinstance(ExecutionToolDispatcher(), IExecutionDispatcher)

    def test_retry_handler_satisfies_protocol(self):
        from core.interfaces.retry import IExecutionRetryHandler
        from core.runtime.services.retry_handler import ExecutionRetryHandler
        assert isinstance(ExecutionRetryHandler(), IExecutionRetryHandler)

    def test_state_store_satisfies_protocol(self):
        from core.interfaces.state_store import IExecutionStateStore
        from core.runtime.services.state_store import ExecutionStateStore
        assert isinstance(ExecutionStateStore(), IExecutionStateStore)

    def test_lease_manager_satisfies_protocol(self):
        from core.interfaces.lease import IExecutionLeaseManager
        from core.runtime.services.lease_manager import ExecutionLeaseManager
        assert isinstance(ExecutionLeaseManager(), IExecutionLeaseManager)


# ── D8.3.8 — Service Health Checks ─────────────────────────────────


class TestServiceHealthChecks:
    """Verify each service has a working health_check() method."""

    def test_scheduler_health_check(self):
        from core.runtime.services.scheduler import ExecutionScheduler
        scheduler = ExecutionScheduler()
        result = scheduler.health_check()
        assert isinstance(result, dict)
        assert result["status"] in ["healthy", "degraded", "unhealthy"]
        assert result["service"] == "scheduler"
        assert "version" in result
        assert "uptime_seconds" in result
        assert "active_tasks" in result
        assert "queue_depth" in result
        assert "last_error" in result

    def test_scheduler_health_check_never_raises(self):
        from core.runtime.services.scheduler import ExecutionScheduler
        scheduler = ExecutionScheduler()
        # Should never raise exceptions
        result = scheduler.health_check()
        assert result is not None


# ── D8.3.9 — Service Instantiation ─────────────────────────────────


class TestServiceInstantiation:
    """Verify each service can be instantiated without errors."""

    def test_scheduler_instantiation(self):
        from core.runtime.services.scheduler import ExecutionScheduler
        scheduler = ExecutionScheduler()
        assert scheduler is not None

    def test_dispatcher_instantiation(self):
        from core.runtime.services.tool_dispatcher import ExecutionToolDispatcher
        dispatcher = ExecutionToolDispatcher()
        assert dispatcher is not None

    def test_retry_handler_instantiation(self):
        from core.runtime.services.retry_handler import ExecutionRetryHandler
        retry_handler = ExecutionRetryHandler()
        assert retry_handler is not None

    def test_state_store_instantiation(self):
        from core.runtime.services.state_store import ExecutionStateStore
        state_store = ExecutionStateStore()
        assert state_store is not None

    def test_lease_manager_instantiation(self):
        from core.runtime.services.lease_manager import ExecutionLeaseManager
        lease_manager = ExecutionLeaseManager()
        assert lease_manager is not None


# ── D8.3.10 — Failure Propagation Execution ────────────────────────


class TestFailurePropagationExecution:
    """Verify failure propagation works at runtime."""

    def test_dispatcher_failure_actions(self):
        matrix = FailurePropagationPolicy()
        actions = matrix.apply("Dispatcher")
        assert isinstance(actions, list)
        assert len(actions) > 0
        assert all(isinstance(a, str) for a in actions)

    def test_lease_manager_failure_actions(self):
        matrix = FailurePropagationPolicy()
        actions = matrix.apply("LeaseManager")
        assert isinstance(actions, list)
        assert len(actions) > 0

    def test_state_store_failure_actions(self):
        matrix = FailurePropagationPolicy()
        actions = matrix.apply("StateStore")
        assert isinstance(actions, list)
        assert len(actions) > 0

    def test_unknown_domain_raises_key_error(self):
        matrix = FailurePropagationPolicy()
        with pytest.raises(KeyError):
            matrix.apply("NonExistentDomain")
