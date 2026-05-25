"""EXEC-DIRECTIVE-025 Task 4 — Phase 4 & D8 Isolation Compliance Tests.

15 tests covering:
  K4-I1  to K4-I3:  CapabilityGuard enforcement
  K4-I4  to K4-I6:  IOPolicyEngine enforcement
  K4-I7  to K4-I9:  SandboxExecutor kill-safe
  K4-I10 to K4-I12: ResourceEnforcer lifecycle
  K4-I13 to K4-I15: Cross-layer isolation integrity

Ref: DEVELOPER.md §15.15a/b, Canon LAW 20-27, RULE 1-4
Ref: EXEC-DIRECTIVE-025 Task 4
"""

from __future__ import annotations

import time
from typing import Any, Dict, List

import pytest

from core.runtime.isolation.isolation_runtime import IsolationRuntime
from core.runtime.isolation.capability_guard import CapabilityGuard, CapabilityStatus
from core.runtime.isolation.resource_enforcer import ResourceEnforcer, ResourceLimitExceeded
from core.runtime.isolation.sandbox_executor import SandboxExecutor
from core.runtime.isolation.io_policy_engine import IOPolicyEngine
from core.runtime.sandbox.sandbox_context import SandboxContext, FilesystemMode, NetworkMode
from core.runtime.io.network_isolation import NetworkIsolation
from core.runtime.io.filesystem_isolation import FilesystemIsolation
from core.runtime.io.io_policy_engine import IOViolation
from core.runtime.mesh.service_mesh import ServiceMesh
from core.runtime.mesh.failure_propagator import FailurePropagator
from core.runtime.mesh.service_registry import ServiceRegistry, ServiceInstance, ServiceStatus
from core.security.capabilities.capability_registry import CapabilityRegistry
from core.security.capabilities.capability_model import Capability, AccessMode
from core.runtime.resources.quota_manager import QuotaManager, QuotaExceeded


@pytest.fixture
def registry() -> CapabilityRegistry:
    reg = CapabilityRegistry()
    reg.register("test_tool", Capability(
        network=False, filesystem=AccessMode.NONE, subprocess=False,
        max_cpu=1.0, max_memory=512*1024*1024,
        allowed_paths=[], allowed_domains=[],
        description="",
    ))
    reg.register("full_tool", Capability(
        network=True, filesystem=AccessMode.FULL, subprocess=True,
        max_cpu=4.0, max_memory=2048*1024*1024,
        allowed_paths=["/tmp"], allowed_domains=["*"],
        description="",
    ))
    return reg


@pytest.fixture
def isolation(registry: CapabilityRegistry) -> IsolationRuntime:
    return IsolationRuntime(
        capability_guard=CapabilityGuard(registry=registry),
        resource_enforcer=ResourceEnforcer(),
        sandbox_executor=SandboxExecutor(),
        io_policy_engine=IOPolicyEngine(),
        network_isolation=NetworkIsolation(),
        filesystem_isolation=FilesystemIsolation(),
    )


class TestK4CapabilityGuard:
    """K4-I1 to K4-I3: CapabilityGuard enforcement."""

    def test_k4_i1_blocks_unknown_tool(self, registry: CapabilityRegistry) -> None:
        guard = CapabilityGuard(registry=registry)
        result = guard.validate("nonexistent_tool", {}, None)
        assert result.allowed is False
        assert "No capability registered" in result.reason

    def test_k4_i2_allows_registered_tool(self, registry: CapabilityRegistry) -> None:
        guard = CapabilityGuard(registry=registry)
        result = guard.validate("test_tool", {}, None)
        assert result.allowed is True

    def test_k4_i3_blocks_context_mismatch(self, registry: CapabilityRegistry) -> None:
        guard = CapabilityGuard(registry=registry)
        ctx = SandboxContext(
            cpu_limit=1.0, memory_limit=512*1024*1024, timeout=10.0,
            filesystem_mode=FilesystemMode.FULL, network_mode=NetworkMode.BLOCKED,
        )
        result = guard.validate("test_tool", {}, ctx)
        assert result.allowed is False
        assert any("filesystem" in v.lower() for v in result.violations)


class TestK4IOPolicy:
    """K4-I4 to K4-I6: IOPolicyEngine enforcement."""

    def test_k4_i4_blocks_unpermitted_io(self) -> None:
        engine = IOPolicyEngine()
        engine.block("test_tool", "network.get")
        with pytest.raises(IOViolation):
            engine.check("test_tool", "network.get", "http://evil.com")

    def test_k4_i5_allows_permitted_io(self) -> None:
        engine = IOPolicyEngine()
        engine.allow("test_tool", "file.read")
        try:
            engine.check("test_tool", "file.read", "/tmp/test.txt")
            allowed = True
        except IOViolation:
            allowed = False
        assert allowed is True

    def test_k4_i6_network_blocks_private_ip(self) -> None:
        net = NetworkIsolation()
        with pytest.raises(Exception):
            net.check_request("test_tool", "http://169.254.169.254/")


class TestK4SandboxExecutor:
    """K4-I7 to K4-I9: SandboxExecutor kill-safe."""

    def test_k4_i7_execute_returns_dict(self) -> None:
        executor = SandboxExecutor()
        ctx = SandboxContext(
            cpu_limit=0.5, memory_limit=128*1024*1024, timeout=5.0,
            filesystem_mode=FilesystemMode.NONE, network_mode=NetworkMode.BLOCKED,
        )
        result = executor.execute("echo_script", {"script": "echo hello"}, ctx)
        assert isinstance(result, dict)

    def test_k4_i8_execute_direct_timeout_kill(self) -> None:
        executor = SandboxExecutor()
        ctx = SandboxContext(
            cpu_limit=0.5, memory_limit=128*1024*1024, timeout=1.0,
            filesystem_mode=FilesystemMode.NONE, network_mode=NetworkMode.BLOCKED,
        )

        def slow_func(inp: Any) -> str:
            time.sleep(10)
            return "done"

        start = time.perf_counter()
        result = executor.execute_direct(slow_func, {}, ctx, exec_id="test_kill")
        elapsed = (time.perf_counter() - start) * 1000
        assert elapsed < 5000

    def test_k4_i9_kill_returns_bool(self) -> None:
        executor = SandboxExecutor()
        result = executor.kill("nonexistent_id")
        assert isinstance(result, bool)


class TestK4ResourceEnforcer:
    """K4-I10 to K4-I12: ResourceEnforcer lifecycle."""

    def test_k4_i10_pre_check_passes(self) -> None:
        enforcer = ResourceEnforcer()
        try:
            enforcer.check_before_scheduling("exec_1", "test_tool",
                                             estimated_cpu=0.1, estimated_memory=1024)
            passed = True
        except QuotaExceeded:
            passed = False
        assert passed is True

    def test_k4_i11_enforce_returns_bool(self) -> None:
        enforcer = ResourceEnforcer()
        result = enforcer.enforce("exec_test", cpu=0.01, memory=1024, wall_time=0.1)
        assert isinstance(result, bool)

    def test_k4_i12_finish_returns_usage(self) -> None:
        enforcer = ResourceEnforcer()
        enforcer.check_before_scheduling("exec_finish", "test_tool",
                                         estimated_cpu=0.1, estimated_memory=1024)
        usage = enforcer.finish("exec_finish")
        assert usage is not None


class TestK4CrossLayer:
    """K4-I13 to K4-I15: Cross-layer isolation integrity."""

    def test_k4_i13_runtime_blocks_via_capability(self, isolation: IsolationRuntime) -> None:
        result = isolation.execute("nonexistent_tool", {})
        assert result.get("status") == "blocked"
        assert "capability" in result.get("reason", "").lower()

    def test_k4_i14_service_mesh_routes_via_protocol(self) -> None:
        mesh = ServiceMesh()
        results: List[str] = []
        mesh.register_local_handler("test_svc", "ping",
                                     lambda p: {"status": "pong"})
        result = mesh.call("test_svc", "ping", {"data": 1})
        assert result == {"status": "pong"}

    def test_k4_i15_failure_propagates_without_crash(self) -> None:
        propagator = FailurePropagator()
        try:
            propagator.on_failure("svc_a", lambda f: None)
            propagator.propagate("svc_a", "inst_1", "timeout")
            propagator.propagate("svc_b", "inst_2", "crash")
            assert propagator.failure_count("svc_a") == 1
            assert propagator.failure_count("svc_b") == 1
        except Exception:
            pytest.fail("Failure propagation raised unexpected exception")
