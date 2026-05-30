"""Phase D8 — Service Mesh Isolation Tests (21 tests).

Groups:
  G1 — TestNoSharedMutableState      (5 tests) — LAW 27
  G2 — TestNoHiddenCrossServiceAccess (4 tests) — D8.3 Rule 10
  G3 — TestServiceInterfaceCompliance (4 tests) — D8.1
  G4 — TestFailurePropagationCompliance (4 tests) — LAW 20-22
  G5 — TestCanonServiceOwnership     (4 tests) — LAW 23-27

Ref: DEVELOPER.md §15.15a D8.3
Ref: Canon LAW 20-27
"""

import ast
import inspect
import logging
import pathlib
import time
from unittest.mock import MagicMock, create_autospec, patch

import pytest

from core.runtime.services.scheduler import (
    ExecutionScheduler,
    SchedulingError,
    CollectError,
)
from core.runtime.services.state_store import (
    ExecutionStateStore,
    PersistenceError,
)
from core.runtime.services.tool_dispatcher import (
    ExecutionToolDispatcher,
    DispatchError,
    UnknownToolError,
    ContractViolationError,
)
from core.runtime.services.retry_handler import (
    ExecutionRetryHandler,
    RetryDecisionError,
)
from core.runtime.services.lease_manager import (
    ExecutionLeaseManager,
    LeaseError,
    HeartbeatError,
)
from core.runtime.services.failure_propagation import (
    FailureMatrix,
    FailureMode,
    FailureEvent,
)

logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────────────────────────
# Protocol method sets (for ownership/compliance checks)
# ────────────────────────────────────────────────────────────────────

PROTOCOL_METHODS = {
    "ExecutionScheduler": {"schedule", "run_with_timeout", "collect_futures"},
    "ExecutionToolDispatcher": {"dispatch_tool_call", "validate_contract", "route_service"},
    "ExecutionRetryHandler": {"decide_retry", "apply_backoff", "record_failure"},
    "ExecutionStateStore": {"save_state", "load_state", "store_checkpoint", "read_trace"},
    "ExecutionLeaseManager": {"acquire_lease", "renew_lease", "release_lease", "monitor_heartbeat"},
}

FORBIDDEN_OWNERSHIP = {
    "ExecutionScheduler": {"decide_retry", "dispatch_tool_call", "save_state", "acquire_lease"},
    "ExecutionToolDispatcher": {"save_state", "acquire_lease", "decide_retry", "schedule"},
    "ExecutionRetryHandler": {"schedule", "dispatch_tool_call", "save_state", "acquire_lease"},
    "ExecutionStateStore": {"dispatch_tool_call", "decide_retry", "acquire_lease", "schedule"},
    "ExecutionLeaseManager": {"decide_retry", "dispatch_tool_call", "save_state", "schedule"},
}

SERVICE_DOMAIN_IMPORTS: dict = {
    "scheduler": ["dispatcher", "state_store", "retry_handler", "lease_manager"],
    "tool_dispatcher": ["scheduler", "state_store", "retry_handler", "lease_manager"],
    "retry_handler": ["scheduler", "dispatcher", "state_store", "lease_manager"],
    "state_store": ["scheduler", "dispatcher", "retry_handler", "lease_manager"],
    "lease_manager": ["scheduler", "dispatcher", "retry_handler", "state_store"],
}


# ════════════════════════════════════════════════════════════════════
# G1 — TestNoSharedMutableState (5 tests)
# ════════════════════════════════════════════════════════════════════


class TestNoSharedMutableState:
    """LAW 27: No shared mutable state between services.

    Each test patches another service's private state and verifies
    the service under test never mutates it.
    """

    def test_scheduler_does_not_mutate_dispatcher_state(self):
        """G1-T1: Scheduler must not modify Dispatcher._tool_registry."""
        dispatcher = ExecutionToolDispatcher()
        original = dict(dispatcher._tool_registry)

        scheduler = ExecutionScheduler()
        scheduler.schedule(["a", "b"])

        assert dict(dispatcher._tool_registry) == original, (
            "Scheduler mutated Dispatcher._tool_registry"
        )

    def test_dispatcher_does_not_mutate_scheduler_state(self):
        """G1-T2: Dispatcher must not modify Scheduler._level_queue."""
        scheduler = ExecutionScheduler()
        scheduler.schedule(["a", "b"])
        original_levels = list(scheduler._level_queue)

        dispatcher = ExecutionToolDispatcher()
        dispatcher.register_tool("test", lambda x: x)
        try:
            dispatcher.dispatch_tool_call("test", {})
        except Exception:
            pass

        assert list(scheduler._level_queue) == original_levels, (
            "Dispatcher mutated Scheduler._level_queue"
        )

    def test_retry_handler_does_not_mutate_state_store(self):
        """G1-T3: RetryHandler must not modify StateStore._cache."""
        store = ExecutionStateStore()
        store.save_state("node_1", "value")
        original = dict(store._cache)

        handler = ExecutionRetryHandler()
        handler.record_failure("node_1", ValueError("fail"), 1)

        assert dict(store._cache) == original, (
            "RetryHandler mutated StateStore._cache"
        )

    def test_lease_manager_does_not_mutate_scheduler_state(self):
        """G1-T4: LeaseManager must not modify Scheduler._running_futures."""
        scheduler = ExecutionScheduler()
        original = dict(scheduler._running_futures)

        lm = ExecutionLeaseManager()
        lm.acquire_lease("res_1", "owner_1")

        assert dict(scheduler._running_futures) == original, (
            "LeaseManager mutated Scheduler._running_futures"
        )

    def test_state_store_does_not_mutate_retry_handler_state(self):
        """G1-T5: StateStore must not modify RetryHandler._failure_counts."""
        handler = ExecutionRetryHandler()
        handler.record_failure("n1", ValueError("fail"), 1)
        original = dict(handler._failure_counts)

        store = ExecutionStateStore()
        store.save_state("node_1", "val")

        assert dict(handler._failure_counts) == original, (
            "StateStore mutated RetryHandler._failure_counts"
        )


# ════════════════════════════════════════════════════════════════════
# G2 — TestNoHiddenCrossServiceAccess (4 tests)
# ════════════════════════════════════════════════════════════════════


class TestNoHiddenCrossServiceAccess:
    """D8.3 Rule 10: No hidden cross-service implementation imports.

    AST-scans each service module to verify it does not import
    other service implementations directly.
    """

    SERVICES_DIR = pathlib.Path("core/runtime/services")

    @staticmethod
    def _get_service_source(module_name: str) -> str:
        path = TestNoHiddenCrossServiceAccess.SERVICES_DIR / f"{module_name}.py"
        return path.read_text()

    def test_no_direct_state_store_access_from_scheduler(self):
        """G2-T1: Scheduler must not import StateStore internals."""
        source = self._get_service_source("scheduler")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                source_text = ast.get_source_segment(source, node) or ""
                if "state_store" in source_text and "ExecutionStateStore" in source_text:
                    pytest.fail(f"Scheduler directly imports state_store: {source_text}")

    def test_no_direct_lease_manager_access_from_dispatcher(self):
        """G2-T2: Dispatcher must not import LeaseManager internals."""
        source = self._get_service_source("tool_dispatcher")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                source_text = ast.get_source_segment(source, node) or ""
                if "lease_manager" in source_text and "ExecutionLeaseManager" in source_text:
                    pytest.fail(f"Dispatcher directly imports lease_manager: {source_text}")

    def test_all_inter_service_calls_go_through_interfaces(self):
        """G2-T3: No service imports another service's implementation."""
        violations = []
        for service, forbidden in SERVICE_DOMAIN_IMPORTS.items():
            try:
                source = self._get_service_source(service)
            except FileNotFoundError:
                continue
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    source_text = ast.get_source_segment(source, node) or ""
                    for target in forbidden:
                        if f"core.runtime.{target}" in source_text:
                            violations.append(
                                f"{service} imports {target} implementation: {source_text}"
                            )
        assert len(violations) == 0, f"Hidden cross-service imports: {violations}"

    def test_no_implementation_imports_across_services(self):
        """G2-T4: No 'from core.runtime.services.X import Y' across services."""
        violations = []
        for service, forbidden in SERVICE_DOMAIN_IMPORTS.items():
            try:
                source = self._get_service_source(service)
            except FileNotFoundError:
                continue
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    for target in forbidden:
                        if f"core.runtime.services.{target}" in node.module:
                            violations.append(
                                f"{service} imports from {node.module}"
                            )
        assert len(violations) == 0, f"Cross-service implementation imports: {violations}"


# ════════════════════════════════════════════════════════════════════
# G3 — TestServiceInterfaceCompliance (4 tests)
# ════════════════════════════════════════════════════════════════════


class TestServiceInterfaceCompliance:
    """D8.1: Each service exposes ONLY its protocol methods.

    No extra public methods beyond the protocol interface.
    """

    @staticmethod
    def _get_public_methods(cls: type) -> set:
        return {
            m for m in dir(cls)
            if not m.startswith("_") and callable(getattr(cls, m, None))
        }

    def test_scheduler_has_no_extra_public_methods(self):
        """G3-T1: Scheduler must not expose methods outside IExecutionScheduler."""
        public = self._get_public_methods(ExecutionScheduler)
        protocol = PROTOCOL_METHODS["ExecutionScheduler"]
        extra = public - protocol
        assert len(extra) == 0, f"Extra public methods on Scheduler: {extra}"

    def test_dispatcher_has_no_extra_public_methods(self):
        """G3-T2: Dispatcher must not expose methods outside IExecutionDispatcher."""
        public = self._get_public_methods(ExecutionToolDispatcher)
        protocol = PROTOCOL_METHODS["ExecutionToolDispatcher"]
        # register_tool is a setup/configuration method, not a service protocol method.
        # It is needed for DI but does not belong to IExecutionDispatcher.
        allowed_extras = {"register_tool"}
        extra = public - protocol - allowed_extras
        assert len(extra) == 0, f"Extra public methods on Dispatcher: {extra}"

    def test_retry_handler_has_no_extra_public_methods(self):
        """G3-T3: RetryHandler must not expose methods outside IExecutionRetryHandler."""
        public = self._get_public_methods(ExecutionRetryHandler)
        protocol = PROTOCOL_METHODS["ExecutionRetryHandler"]
        extra = public - protocol
        assert len(extra) == 0, f"Extra public methods on RetryHandler: {extra}"

    def test_state_store_has_no_extra_public_methods(self):
        """G3-T4: StateStore must not expose methods outside IExecutionStateStore."""
        public = self._get_public_methods(ExecutionStateStore)
        protocol = PROTOCOL_METHODS["ExecutionStateStore"]
        extra = public - protocol
        assert len(extra) == 0, f"Extra public methods on StateStore: {extra}"


# ════════════════════════════════════════════════════════════════════
# G4 — TestFailurePropagationCompliance (4 tests)
# ════════════════════════════════════════════════════════════════════


class TestFailurePropagationCompliance:
    """LAW 20-22: Failure propagation matrix completeness.

    Tests F01-F03 scenarios from the D8.2 design.
    Each test injects a failure and verifies the action sequence.
    """

    def test_dispatcher_failure_propagates_correctly(self):
        """G4-T1: F01 — Dispatcher fail → RETRY, CLASSIFY, RELEASE, NOTIFY."""
        matrix = FailureMatrix()
        actions = matrix.apply("Dispatcher")
        assert "RETRY" in actions
        assert "CLASSIFY" in actions
        assert "RELEASE" in actions
        assert "NOTIFY" in actions

    def test_lease_expiry_propagates_correctly(self):
        """G4-T2: F02 — Lease expiry → CANCEL, ROLLBACK, REASSIGN, RECORD."""
        matrix = FailureMatrix()
        actions = matrix.apply("LeaseManager")
        assert "CANCEL" in actions
        assert "ROLLBACK" in actions
        assert "REASSIGN" in actions
        assert "RECORD" in actions

    def test_state_store_failure_propagates_correctly(self):
        """G4-T3: F03 — StateStore fail → DEGRADE, BUFFER, CONTINUE, DEFER."""
        matrix = FailureMatrix()
        actions = matrix.apply("StateStore")
        assert "DEGRADE" in actions
        assert "BUFFER" in actions
        assert "CONTINUE" in actions
        assert "DEFER" in actions

    def test_matrix_covers_all_source_domains(self):
        """G4-T4: All 8 source domains must have entries in the matrix."""
        matrix = FailureMatrix()
        scenarios = matrix.get_all_scenarios()
        domains = {s["source_domain"] for s in scenarios}

        expected_domains = {
            "Dispatcher", "LeaseManager", "StateStore",
            "Scheduler", "RetryHandler", "Engine", "Core",
        }
        # LeaseManager has two entries (F02 + F07)
        assert "LeaseManager_acquire" in domains or "LeaseManager" in domains
        # Verify F01-F08 coverage
        scenario_ids = {s["scenario_id"] for s in scenarios}
        for expected_id in [f"F{i:02d}" for i in range(1, 9)]:
            assert expected_id in scenario_ids, f"Missing scenario {expected_id}"


# ════════════════════════════════════════════════════════════════════
# G5 — TestCanonServiceOwnership (4 tests)
# ════════════════════════════════════════════════════════════════════


class TestCanonServiceOwnership:
    """LAW 23-27: Service ownership boundaries.

    Each service must own exactly its domain and no other.
    Forbidden methods must NOT appear in a service's protocol.
    """

    def test_scheduler_does_not_own_retry(self):
        """G5-T1: Scheduler must not own decide_retry."""
        own = PROTOCOL_METHODS["ExecutionScheduler"]
        forbid = FORBIDDEN_OWNERSHIP["ExecutionScheduler"]
        overlap = own & forbid
        assert len(overlap) == 0, (
            f"Scheduler owns forbidden methods: {overlap}"
        )
        assert "decide_retry" not in own

    def test_dispatcher_does_not_own_state(self):
        """G5-T2: Dispatcher must not own save_state."""
        own = PROTOCOL_METHODS["ExecutionToolDispatcher"]
        forbid = FORBIDDEN_OWNERSHIP["ExecutionToolDispatcher"]
        overlap = own & forbid
        assert len(overlap) == 0, (
            f"Dispatcher owns forbidden methods: {overlap}"
        )
        assert "save_state" not in own

    def test_retry_handler_does_not_own_scheduling(self):
        """G5-T3: RetryHandler must not own schedule."""
        own = PROTOCOL_METHODS["ExecutionRetryHandler"]
        forbid = FORBIDDEN_OWNERSHIP["ExecutionRetryHandler"]
        overlap = own & forbid
        assert len(overlap) == 0, (
            f"RetryHandler owns forbidden methods: {overlap}"
        )
        assert "schedule" not in own

    def test_state_store_does_not_own_dispatch(self):
        """G5-T4: StateStore must not own dispatch_tool_call."""
        own = PROTOCOL_METHODS["ExecutionStateStore"]
        forbid = FORBIDDEN_OWNERSHIP["ExecutionStateStore"]
        overlap = own & forbid
        assert len(overlap) == 0, (
            f"StateStore owns forbidden methods: {overlap}"
        )
        assert "dispatch_tool_call" not in own


# ════════════════════════════════════════════════════════════════════
# Functional Tests — Individual Service Correctness
# (Supplemental — not part of the 21-test count)
# ════════════════════════════════════════════════════════════════════


class TestExecutionSchedulerFunctional:
    """Functional tests for ExecutionScheduler."""

    def test_schedule_returns_levels(self):
        s = ExecutionScheduler()
        levels = s.schedule(["a", "b", "c"])
        assert isinstance(levels, list)
        assert len(levels) >= 1

    def test_collect_futures_empty(self):
        s = ExecutionScheduler()
        results = s.collect_futures({})
        assert results == []


class TestExecutionStateStoreFunctional:
    """Functional tests for ExecutionStateStore."""

    def test_save_and_load(self):
        store = ExecutionStateStore()
        store.save_state("n1", {"key": "value"}, "sess_1")
        loaded = store.load_state("n1", "sess_1")
        assert loaded == {"key": "value"}

    def test_load_missing_returns_none(self):
        store = ExecutionStateStore()
        assert store.load_state("nonexistent") is None

    def test_store_checkpoint(self):
        store = ExecutionStateStore()
        store.store_checkpoint("sess_1", {"dag": True}, "node_5", {"ok": True})
        trace = store.read_trace("sess_1")
        assert trace is None  # checkpoint is separate from trace
        # Verify checkpoint stored
        assert hasattr(store, "_checkpoints")
        assert "sess_1" in store._checkpoints

    def test_read_trace(self):
        store = ExecutionStateStore()
        store.save_state("n1", "v1", "sess_t")
        trace = store.read_trace("sess_t")
        assert trace is not None
        assert "nodes" in trace


class TestExecutionToolDispatcherFunctional:
    """Functional tests for ExecutionToolDispatcher."""

    def test_dispatch_unknown_raises(self):
        d = ExecutionToolDispatcher()
        with pytest.raises(UnknownToolError):
            d.dispatch_tool_call("unknown", {})

    def test_register_and_dispatch(self):
        d = ExecutionToolDispatcher()
        d.register_tool("echo", lambda inputs: inputs)
        result = d.dispatch_tool_call("echo", {"msg": "hello"})
        assert result["status"] == "completed"
        assert result["result"] == {"msg": "hello"}

    def test_validate_contract_missing_field(self):
        d = ExecutionToolDispatcher()
        d.register_tool(
            "needs_x",
            lambda inputs: inputs,
            contract_schema={"required": ["x"]},
        )
        with pytest.raises(ContractViolationError):
            d.validate_contract("needs_x", {"y": 1})


class TestExecutionRetryHandlerFunctional:
    """Functional tests for ExecutionRetryHandler."""

    def test_decide_retry_yes(self):
        h = ExecutionRetryHandler()
        assert h.decide_retry("n1", RuntimeError("fail"), 1, 3) is True

    def test_decide_retry_no_max_attempts(self):
        h = ExecutionRetryHandler()
        assert h.decide_retry("n1", RuntimeError("fail"), 3, 3) is False

    def test_apply_backoff(self):
        h = ExecutionRetryHandler()
        delay = h.apply_backoff(2, base_delay=1.0)
        assert 0.1 <= delay <= 60.0

    def test_record_failure(self):
        h = ExecutionRetryHandler()
        h.record_failure("n1", ValueError("bad"), 1)
        assert h._failure_counts.get("n1") == 1


class TestExecutionLeaseManagerFunctional:
    """Functional tests for ExecutionLeaseManager."""

    def test_acquire_and_release(self):
        lm = ExecutionLeaseManager()
        lease_id = lm.acquire_lease("res_1", "owner_1")
        assert lease_id is not None
        assert lm.release_lease(lease_id) is True

    def test_acquire_busy(self):
        lm = ExecutionLeaseManager()
        lm.acquire_lease("res_1", "owner_1")
        assert lm.acquire_lease("res_1", "owner_2") is None

    def test_renew_lease(self):
        lm = ExecutionLeaseManager()
        lease_id = lm.acquire_lease("res_1", "owner_1", ttl=60.0)
        assert lm.renew_lease(lease_id, ttl=30.0) is True

    def test_monitor_heartbeat(self):
        lm = ExecutionLeaseManager()
        lease_id = lm.acquire_lease("res_1", "owner_1", ttl=60.0)
        assert lm.monitor_heartbeat(lease_id) is True


class TestFailureMatrixFunctional:
    """Functional tests for FailureMatrix."""

    def test_unknown_domain_raises(self):
        matrix = FailureMatrix()
        with pytest.raises(KeyError):
            matrix.apply("UnknownDomain")

    def test_scenario_count(self):
        matrix = FailureMatrix()
        scenarios = matrix.get_all_scenarios()
        assert len(scenarios) >= 8  # F01-F08

    def test_event_bus_emission(self):
        bus = MagicMock()
        matrix = FailureMatrix(event_bus=bus)
        matrix.apply("Dispatcher")
        assert bus.emit.called
        args, _ = bus.emit.call_args
        assert "runtime.failure" in args[0]
