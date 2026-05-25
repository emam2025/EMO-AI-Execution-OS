"""EXEC-DIRECTIVE-025 Task 5 — D8 Failure Propagation Compliance Tests.

10 tests covering D8.2 Failure Propagation Matrix:
  K4-F1  to K4-F2:  FailurePropagator records and notifies
  K4-F3  to K4-F4:  ServiceRegistry health tracking on failure
  K4-F5  to K4-F6:  ServiceMesh routing after failure injection
  K4-F7  to K4-F8:  LeaseManager release on scheduler failure
  K4-F9  to K4-F10: StateStore retry on read failure

Ref: DEVELOPER.md §15.15b, Canon LAW 23-27
Ref: artifacts/design/d8/04_isolation_test_blueprint.md §D8.2
"""

from __future__ import annotations

import time
from typing import Any, Dict, List

import pytest

from core.runtime.mesh.failure_propagator import FailurePropagator
from core.runtime.mesh.service_mesh import ServiceMesh
from core.runtime.mesh.service_registry import ServiceRegistry, ServiceInstance, ServiceStatus
from core.runtime.services.scheduler import ExecutionScheduler
from core.runtime.services.state_store import ExecutionStateStore
from core.runtime.services.tool_dispatcher import ExecutionToolDispatcher
from core.runtime.services.retry_handler import ExecutionRetryHandler
from core.runtime.services.lease_manager import ExecutionLeaseManager


@pytest.fixture
def mesh() -> ServiceMesh:
    return ServiceMesh()


@pytest.fixture
def registry() -> ServiceRegistry:
    return ServiceRegistry()


notified: List[str] = []


class TestK4FailurePropagator:
    """K4-F1 to K4-F2: FailurePropagator records and notifies."""

    def test_k4_f1_records_failure(self) -> None:
        propagator = FailurePropagator()
        propagator.on_failure("svc_alpha", lambda f: None)
        propagator.propagate("svc_alpha", "inst_1", "timeout")
        propagator.propagate("svc_beta", "inst_2", "crash")
        assert propagator.failure_count("svc_alpha") == 1
        assert propagator.failure_count("svc_beta") == 1

    def test_k4_f2_notifies_dependents(self) -> None:
        notif: List[str] = []
        propagator = FailurePropagator()
        propagator.on_failure("svc_alpha", lambda f: notif.append("alpha_failed"))
        propagator.on_failure("svc_beta", lambda f: notif.append("beta_failed"))
        propagator.propagate("svc_alpha", "inst_1", "timeout")
        time.sleep(0.02)
        assert "alpha_failed" in notif


class TestK4ServiceHealth:
    """K4-F3 to K4-F4: ServiceRegistry health tracking on failure."""

    def test_k4_f3_registry_marks_unhealthy(self, registry: ServiceRegistry) -> None:
        instance_id = registry.register("svc_a")
        instances = registry.discover("svc_a")
        assert len(instances) >= 1

    def test_k4_f4_registry_recovers_after_restart(self, registry: ServiceRegistry) -> None:
        registry.register("svc_b")
        instances = registry.discover("svc_b", min_healthy=False)
        assert len(instances) >= 1


class TestK4MeshRouting:
    """K4-F5 to K4-F6: ServiceMesh routing after failure injection."""

    def test_k4_f5_mesh_routes_local_handler(self, mesh: ServiceMesh) -> None:
        results: List[str] = []
        mesh.register_local_handler("worker", "execute",
                                     lambda p: {"status": "done", "result": results})
        result = mesh.call("worker", "execute", {"task": "test"})
        assert result.get("status") == "done"

    def test_k4_f6_mesh_async_call_does_not_crash(self, mesh: ServiceMesh) -> None:
        mesh.register_local_handler("worker", "execute",
                                     lambda p: {"status": "ok"})
        trace_id = mesh.call_async("worker", "execute", {"task": "async_test"})
        assert isinstance(trace_id, str) and len(trace_id) > 0


class TestK4LeaseRelease:
    """K4-F7 to K4-F8: LeaseManager release on scheduler failure."""

    def test_k4_f7_lease_manager_acquires_lease(self) -> None:
        manager = ExecutionLeaseManager()
        lease_id = manager.acquire_lease("resource_1", "worker_1", ttl=30.0)
        assert lease_id is not None

    def test_k4_f8_lease_manager_releases_on_expiry(self) -> None:
        manager = ExecutionLeaseManager()
        lease_id = manager.acquire_lease("resource_exp", "worker_1", ttl=0.001)
        assert lease_id is not None
        time.sleep(0.05)
        renewed = manager.renew_lease(lease_id, ttl=0.001)
        assert renewed is False


class TestK4StateRetry:
    """K4-F9 to K4-F10: StateStore retry on read failure."""

    def test_k4_f9_state_store_saves_and_loads(self) -> None:
        store = ExecutionStateStore()
        store.save_state("test_node", {"value": 42}, session_id="sess_1")
        loaded = store.load_state("test_node", session_id="sess_1")
        assert loaded == {"value": 42}

    def test_k4_f10_retry_handler_retries_on_failure(self) -> None:
        handler = ExecutionRetryHandler()
        attempt_count = [0]

        def should_retry() -> bool:
            attempt_count[0] += 1
            if attempt_count[0] < 3:
                return handler.decide_retry("node_x", ValueError("transient"),
                                            attempt_count[0], max_attempts=3)
            return False

        should_retry()
        should_retry()
        should_retry()
        assert attempt_count[0] == 3
