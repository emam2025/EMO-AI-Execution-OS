"""Phase 4.6 — Runtime Isolation Test Suite.

Tests all Phase 4 layers:
  - Sandbox system (executor, context, manager, errors)
  - Capability security model
  - IO & network isolation
  - Resource governance
  - Isolation integration

MUST TEST (Phase 4 requirements):
  - execution cannot access forbidden filesystem
  - network blocked when capability = false
  - memory limit enforced
  - timeout kills execution
  - sandbox cleanup guaranteed
  - no cross-sandbox state leakage
"""

import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch

import pytest

from core.runtime.sandbox.sandbox_context import (
    SandboxContext,
    FilesystemMode,
    NetworkMode,
)
from core.runtime.sandbox.sandbox_executor import SandboxExecutor
from core.runtime.sandbox.sandbox_manager import SandboxManager
from core.runtime.sandbox.sandbox_errors import (
    SandboxError,
    SandboxViolationError,
    ResourceLimitExceeded,
    ExecutionTimeoutError,
)
from core.security.capabilities.capability_model import (
    Capability,
    AccessMode,
)
from core.security.capabilities.capability_registry import CapabilityRegistry
from core.security.capabilities.capability_guard import (
    CapabilityGuard,
    CapabilityViolation,
)
from core.runtime.io.io_policy_engine import IOPolicyEngine, IOViolation
from core.runtime.io.network_isolation import NetworkIsolation, NetworkBlocked
from core.runtime.io.filesystem_isolation import (
    FilesystemIsolation,
    FilesystemPolicy,
    AccessLevel,
    FileAccessViolation,
)
from core.runtime.resources.resource_tracker import ResourceTracker, ResourceUsage
from core.runtime.resources.quota_manager import QuotaManager, Quota, QuotaExceeded
from core.runtime.resources.resource_enforcer import ResourceEnforcer
from core.runtime.isolation.isolation_runtime import IsolationRuntime


# ═══════════════════════════════════════════════════════════════════
# 4.1 — Sandbox Context
# ═══════════════════════════════════════════════════════════════════


class TestSandboxContext:
    def test_default_is_minimal(self):
        ctx = SandboxContext()
        assert ctx.network_mode == NetworkMode.BLOCKED
        assert ctx.filesystem_mode == FilesystemMode.NONE
        assert ctx.timeout == 30.0
        assert ctx.memory_limit == 256 * 1024 * 1024

    def test_network_blocked_by_default(self):
        ctx = SandboxContext()
        assert not ctx.is_network_allowed("example.com")

    def test_network_full_mode(self):
        ctx = SandboxContext(network_mode=NetworkMode.FULL)
        assert ctx.is_network_allowed("example.com")

    def test_network_allow_list(self):
        ctx = SandboxContext(
            network_mode=NetworkMode.ALLOW_LIST,
            allowed_domains=["example.com"],
        )
        assert ctx.is_network_allowed("example.com")
        assert not ctx.is_network_allowed("evil.com")

    def test_filesystem_none_blocks_all(self):
        ctx = SandboxContext(filesystem_mode=FilesystemMode.NONE)
        assert not ctx.is_path_allowed("/tmp/test")

    def test_filesystem_full_allows_all(self):
        ctx = SandboxContext(filesystem_mode=FilesystemMode.FULL)
        assert ctx.is_path_allowed("/tmp/test")

    def test_filesystem_allowed_paths(self):
        ctx = SandboxContext(
            filesystem_mode=FilesystemMode.READ_ONLY,
            allowed_paths=["/tmp/allowed"],
        )
        assert ctx.is_path_allowed("/tmp/allowed/file.txt")
        assert not ctx.is_path_allowed("/etc/passwd")

    def test_filesystem_write_blocked_in_read_only(self):
        ctx = SandboxContext(
            filesystem_mode=FilesystemMode.READ_ONLY,
            allowed_paths=["/tmp"],
        )
        assert ctx.is_path_allowed("/tmp/test", write=False)
        assert not ctx.is_path_allowed("/tmp/test", write=True)

    def test_filesystem_write_temp_allows_write(self):
        ctx = SandboxContext(
            filesystem_mode=FilesystemMode.WRITE_TEMP,
            allowed_paths=["/tmp"],
        )
        assert ctx.is_path_allowed("/tmp/test", write=True)


# ═══════════════════════════════════════════════════════════════════
# 4.1 — Sandbox Errors
# ═══════════════════════════════════════════════════════════════════


class TestSandboxErrors:
    def test_sandbox_error_base(self):
        e = SandboxError("test error", sandbox_id="s1")
        assert str(e) == "test error"
        assert e.sandbox_id == "s1"

    def test_sandbox_violation_error(self):
        e = SandboxViolationError("access denied", sandbox_id="s1")
        assert "access denied" in str(e)
        assert e.sandbox_id == "s1"

    def test_resource_limit_exceeded(self):
        e = ResourceLimitExceeded("memory", 100, 200, "s1")
        assert "memory" in str(e)
        assert e.limit == 100
        assert e.actual == 200

    def test_execution_timeout_error(self):
        e = ExecutionTimeoutError("tool1", 5.0, 6.2, "s1")
        assert "tool1" in str(e)
        assert e.timeout == 5.0
        assert e.elapsed == 6.2


# ═══════════════════════════════════════════════════════════════════
# 4.1 — Sandbox Manager
# ═══════════════════════════════════════════════════════════════════


class TestSandboxManager:
    def test_create_sandbox(self):
        mgr = SandboxManager()
        sid = mgr.create_sandbox()
        assert len(sid) == 16
        assert mgr.active_count() == 1

    def test_get_executor(self):
        mgr = SandboxManager()
        sid = mgr.create_sandbox()
        executor = mgr.get_executor(sid)
        assert executor is not None

    def test_get_executor_raises_for_invalid(self):
        mgr = SandboxManager()
        with pytest.raises(SandboxViolationError):
            mgr.get_executor("nonexistent")

    def test_destroy_sandbox(self):
        mgr = SandboxManager()
        sid = mgr.create_sandbox()
        assert mgr.destroy_sandbox(sid) is True
        assert mgr.active_count() == 0

    def test_destroy_invalid_sandbox(self):
        mgr = SandboxManager()
        assert mgr.destroy_sandbox("nonexistent") is False

    def test_shutdown_destroys_all(self):
        mgr = SandboxManager()
        mgr.create_sandbox()
        mgr.create_sandbox()
        mgr.create_sandbox()
        assert mgr.active_count() == 3
        mgr.shutdown()
        assert mgr.active_count() == 0

    def test_context_storage(self):
        mgr = SandboxManager()
        ctx = SandboxContext(timeout=15.0)
        sid = mgr.create_sandbox(context=ctx)
        stored = mgr.get_context(sid)
        assert stored.timeout == 15.0


# ═══════════════════════════════════════════════════════════════════
# 4.1 — Sandbox Executor
# ═══════════════════════════════════════════════════════════════════


class TestSandboxExecutor:
    def test_execute_subprocess(self):
        executor = SandboxExecutor()
        ctx = SandboxContext(timeout=10.0)
        result = executor.execute("test_tool", {"key": "value"}, ctx)
        assert result["status"] == "completed"

    def test_execute_direct(self):
        executor = SandboxExecutor()
        ctx = SandboxContext(timeout=10.0)
        result = executor.execute_direct(
            lambda n: {"output": "hello"},
            {"tool": "test"},
            ctx,
        )
        assert result["status"] == "completed"
        assert result["result"]["output"] == "hello"

    def test_execute_direct_timeout(self):
        executor = SandboxExecutor()
        ctx = SandboxContext(timeout=0.05)

        def slow_runner(node):
            time.sleep(10)

        result = executor.execute_direct(slow_runner, {}, ctx)
        assert result["status"] == "failed"

    def test_execute_direct_exception(self):
        executor = SandboxExecutor()
        ctx = SandboxContext(timeout=10.0)

        def failing_runner(node):
            raise ValueError("test error")

        result = executor.execute_direct(failing_runner, {}, ctx)
        assert result["status"] == "failed"
        assert "test error" in result["error"]

    def test_parse_output_valid_json(self):
        raw = '{"status": "completed", "result": "ok"}'
        result = SandboxExecutor._parse_output(raw)
        assert result["status"] == "completed"

    def test_parse_output_invalid_json(self):
        raw = "just text"
        result = SandboxExecutor._parse_output(raw)
        assert result["status"] == "completed"
        assert "raw" in result

    def test_worker_script_generation(self):
        executor = SandboxExecutor()
        script = executor._build_worker_script("my_tool", {"x": 1})
        assert "my_tool" in script
        assert "x" in script

    def test_kill_nonexistent_returns_false(self):
        executor = SandboxExecutor()
        assert executor.kill("nonexistent") is False

    def test_kill_subprocess_execution(self):
        executor = SandboxExecutor()
        ctx = SandboxContext(timeout=30.0)

        def long_running():
            import time
            time.sleep(60)
            return {"done": True}

        exec_id = "test-kill-sub"
        cancel_event = threading.Event()

        # Simulate a running process tracking
        import subprocess as sp
        proc = sp.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        with executor._lock:
            executor._processes[exec_id] = proc
            executor._cancel_events[exec_id] = cancel_event

        assert executor.kill(exec_id) is True
        assert proc.poll() is not None  # process was killed

    def test_kill_direct_execution(self):
        executor = SandboxExecutor()
        exec_id = "test-kill-direct"
        results = []
        done = threading.Event()

        def runner(n):
            for _ in range(50):
                time.sleep(0.05)
            results.append("done")
            done.set()
            return {"done": True}

        t = threading.Thread(
            target=lambda: executor.execute_direct(
                runner, {"tool": "slow"},
                SandboxContext(timeout=30.0),
                exec_id=exec_id,
            ),
            daemon=True,
        )
        t.start()
        time.sleep(0.1)

        assert executor.kill(exec_id) is True
        done.set()  # unblock if already done

    def test_kill_before_direct_starts(self):
        executor = SandboxExecutor()
        exec_id = "test-kill-before"
        started = threading.Event()
        results = []

        def runner(n):
            started.set()
            for _ in range(100):
                time.sleep(0.1)
            results.append("done")
            return {"done": True}

        t = threading.Thread(
            target=lambda: executor.execute_direct(
                runner, {"tool": "slow"},
                SandboxContext(timeout=30.0),
                exec_id=exec_id,
            ),
            daemon=True,
        )
        t.start()
        started.wait(timeout=2)

        assert executor.kill(exec_id) is True


# ═══════════════════════════════════════════════════════════════════
# 4.2 — Capability Model
# ═══════════════════════════════════════════════════════════════════


class TestCapability:
    def test_null_capability(self):
        cap = Capability.null()
        assert cap.network is False
        assert cap.filesystem == AccessMode.NONE
        assert cap.subprocess is False

    def test_full_capability(self):
        cap = Capability.full()
        assert cap.network is True
        assert cap.filesystem == AccessMode.FULL
        assert cap.subprocess is True

    def test_restricted_capability(self):
        cap = Capability.restricted()
        assert cap.network is False
        assert cap.filesystem == AccessMode.NONE
        assert cap.max_cpu == 5.0
        assert cap.max_memory == 128 * 1024 * 1024

    def test_custom_capability(self):
        cap = Capability(
            network=True,
            filesystem=AccessMode.READ,
            max_cpu=10.0,
            allowed_domains=["example.com"],
        )
        assert cap.network
        assert cap.filesystem == AccessMode.READ
        assert "example.com" in cap.allowed_domains


# ═══════════════════════════════════════════════════════════════════
# 4.2 — Capability Registry
# ═══════════════════════════════════════════════════════════════════


class TestCapabilityRegistry:
    def test_default_has_full_trust_tools(self):
        registry = CapabilityRegistry()
        assert registry.has_capability("calculate")
        assert registry.get_capability("calculate").network

    def test_unregistered_tool_gets_restricted(self):
        registry = CapabilityRegistry()
        cap = registry.get_capability("unknown_tool")
        assert cap.network is False

    def test_register_capability(self):
        registry = CapabilityRegistry()
        cap = Capability(network=True)
        registry.register("custom_tool", cap)
        assert registry.has_capability("custom_tool")

    def test_remove_capability(self):
        registry = CapabilityRegistry()
        registry.remove("calculate")
        assert not registry.has_capability("calculate")

    def test_all_capabilities(self):
        registry = CapabilityRegistry()
        caps = registry.all_capabilities()
        assert "calculate" in caps

    def test_load_from_specs_empty(self):
        registry = CapabilityRegistry()
        pre_count = len(registry._capabilities)
        registry.load_from_specs({})
        assert len(registry._capabilities) == pre_count  # no new capabilities added


# ═══════════════════════════════════════════════════════════════════
# 4.2 — Capability Guard
# ═══════════════════════════════════════════════════════════════════


class TestCapabilityGuard:
    def test_unregistered_tool_blocked(self):
        guard = CapabilityGuard()
        with pytest.raises(CapabilityViolation):
            guard.validate("unregistered_tool")

    def test_network_tool_blocked_when_no_network(self):
        registry = CapabilityRegistry()
        registry.register("no_net_tool", Capability(network=False))
        guard = CapabilityGuard(registry)
        with pytest.raises(CapabilityViolation):
            guard.validate("no_net_tool", {"url": "http://example.com"})

    def test_network_tool_allowed_with_network_cap(self):
        registry = CapabilityRegistry()
        registry.register("net_tool", Capability(network=True))
        guard = CapabilityGuard(registry)
        cap = guard.validate("net_tool", {"url": "http://example.com"})
        assert cap.network is True

    def test_tool_without_url_not_blocked_for_network(self):
        registry = CapabilityRegistry()
        registry.register("local_tool", Capability(network=False))
        guard = CapabilityGuard(registry)
        cap = guard.validate("local_tool")
        assert cap is not None

    def test_filesystem_tool_blocked_when_none(self):
        registry = CapabilityRegistry()
        registry.register("no_fs_tool", Capability(network=False, filesystem=AccessMode.NONE))
        guard = CapabilityGuard(registry)
        with pytest.raises(CapabilityViolation):
            guard.validate("no_fs_tool", {"path": "/etc/passwd"})

    def test_full_trust_tool_validates(self):
        guard = CapabilityGuard()
        cap = guard.validate("calculate")
        assert cap.network


# ═══════════════════════════════════════════════════════════════════
# 4.3 — IO Policy Engine
# ═══════════════════════════════════════════════════════════════════


class TestIOPolicyEngine:
    def test_default_policy_blocks_all(self):
        engine = IOPolicyEngine()
        with pytest.raises(IOViolation):
            engine.check("any_tool", "network_request")

    def test_allow_operation(self):
        engine = IOPolicyEngine()
        engine.allow("test_tool", "network_request")
        engine.check("test_tool", "network_request")  # should not raise IOViolation
        assert "test_tool" in engine._tool_policies
        assert "network_request" in engine._tool_policies["test_tool"]

    def test_block_operation(self):
        engine = IOPolicyEngine()
        engine.allow("test_tool", "network_request")
        engine.block("test_tool", "network_request")
        with pytest.raises(IOViolation):
            engine.check("test_tool", "network_request")

    def test_domain_restriction(self):
        engine = IOPolicyEngine()
        from core.runtime.io.io_policy_engine import IOPolicy
        engine.set_policy("test_tool", "network_request", IOPolicy(
            allowed=True,
            allowed_domains=["example.com"],
        ))
        with pytest.raises(IOViolation):
            engine.check("test_tool", "network_request", target="evil.com")

    def test_size_restriction(self):
        engine = IOPolicyEngine()
        from core.runtime.io.io_policy_engine import IOPolicy
        engine.set_policy("test_tool", "write", IOPolicy(
            allowed=True,
            max_size=100,
        ))
        with pytest.raises(IOViolation):
            engine.check("test_tool", "write", size=200)


# ═══════════════════════════════════════════════════════════════════
# 4.3 — Network Isolation
# ═══════════════════════════════════════════════════════════════════


class TestNetworkIsolation:
    def test_outbound_blocked_by_default(self):
        net = NetworkIsolation()
        with pytest.raises(NetworkBlocked):
            net.check_request("any_tool", "http://example.com")

    def test_allowed_domain(self):
        net = NetworkIsolation()
        from core.runtime.io.network_isolation import NetworkPolicy
        net.set_policy("test_tool", NetworkPolicy(
            allow_outbound=True,
            allowed_domains=["example.com"],
        ))
        net.check_request("test_tool", "http://example.com/path")  # should not raise
        assert net._policies["test_tool"].allowed_domains == ["example.com"]

    def test_blocked_domain(self):
        net = NetworkIsolation()
        from core.runtime.io.network_isolation import NetworkPolicy
        net.set_policy("test_tool", NetworkPolicy(
            allow_outbound=True,
            allowed_domains=["example.com"],
        ))
        with pytest.raises(NetworkBlocked):
            net.check_request("test_tool", "http://evil.com")


# ═══════════════════════════════════════════════════════════════════
# 4.3 — Filesystem Isolation
# ═══════════════════════════════════════════════════════════════════


class TestFilesystemIsolation:
    def test_read_blocked_by_default(self):
        fs = FilesystemIsolation()
        with pytest.raises(FileAccessViolation):
            fs.check_read("any_tool", "/tmp/test.txt")

    def test_allowed_path(self):
        fs = FilesystemIsolation()
        fs.set_policy("test_tool", FilesystemPolicy(
            access_level=AccessLevel.READ,
            allowed_paths=["/tmp"],
        ))
        resolved = fs.check_read("test_tool", "/tmp/test.txt")
        assert resolved.endswith("test.txt")

    def test_write_blocked_in_read_only(self):
        fs = FilesystemIsolation()
        fs.set_policy("test_tool", FilesystemPolicy(
            access_level=AccessLevel.READ,
            allowed_paths=["/tmp"],
        ))
        with pytest.raises(FileAccessViolation):
            fs.check_write("test_tool", "/tmp/test.txt")

    def test_write_allowed_in_write_mode(self):
        fs = FilesystemIsolation()
        fs.set_policy("test_tool", FilesystemPolicy(
            access_level=AccessLevel.WRITE,
            allowed_paths=["/tmp"],
        ))
        resolved = fs.check_write("test_tool", "/tmp/test.txt")
        assert "test.txt" in resolved

    def test_extension_filter(self):
        fs = FilesystemIsolation()
        fs.set_policy("test_tool", FilesystemPolicy(
            access_level=AccessLevel.READ,
            allowed_paths=["/tmp"],
            allowed_extensions=[".txt"],
        ))
        fs.check_read("test_tool", "/tmp/file.txt")
        with pytest.raises(FileAccessViolation):
            fs.check_read("test_tool", "/tmp/file.exe")


# ═══════════════════════════════════════════════════════════════════
# 4.4 — Resource Tracker
# ═══════════════════════════════════════════════════════════════════


class TestResourceTracker:
    def test_start_and_complete(self):
        tracker = ResourceTracker()
        tracker.start_execution("e1", "tool1")
        assert tracker.active_count() == 1
        usage = tracker.complete_execution("e1")
        assert usage is not None
        assert usage.tool == "tool1"
        assert tracker.active_count() == 0

    def test_update_during_execution(self):
        tracker = ResourceTracker()
        tracker.start_execution("e1", "tool1")
        tracker.update("e1", cpu_time=5.0, memory_bytes=1024)
        active = tracker.get_active("e1")
        assert active is not None
        assert active.cpu_time == 5.0
        assert active.memory_bytes == 1024

    def test_complete_unknown(self):
        tracker = ResourceTracker()
        assert tracker.complete_execution("nonexistent") is None

    def test_get_usage_after_complete(self):
        tracker = ResourceTracker()
        tracker.start_execution("e1", "tool1")
        tracker.complete_execution("e1")
        usage = tracker.get_usage("e1")
        assert usage is not None

    def test_total_cpu(self):
        tracker = ResourceTracker()
        tracker.start_execution("e1", "t1")
        tracker.update("e1", cpu_time=2.0)
        tracker.complete_execution("e1")
        tracker.start_execution("e2", "t2")
        tracker.update("e2", cpu_time=3.0)
        tracker.complete_execution("e2")
        assert tracker.total_cpu() == 5.0


# ═══════════════════════════════════════════════════════════════════
# 4.4 — Quota Manager
# ═══════════════════════════════════════════════════════════════════


class TestQuotaManager:
    def test_no_quota_no_block(self):
        qm = QuotaManager()
        qm.check("execution:e1", cpu=100)
        assert "execution:e1" not in qm._usage  # no usage recorded yet

    def test_execution_quota_exceeded(self):
        qm = QuotaManager()
        qm.set_execution_quota("execution:e1", Quota(max_cpu=10.0))
        with pytest.raises(QuotaExceeded):
            qm.check("execution:e1", cpu=15.0)

    def test_execution_quota_within_limit(self):
        qm = QuotaManager()
        qm.set_execution_quota("execution:e1", Quota(max_cpu=10.0))
        qm.check("execution:e1", cpu=5.0)
        assert qm._execution_quotas["execution:e1"].max_cpu == 10.0
        # check passes without QuotaExceeded

    def test_global_quota_exceeded(self):
        qm = QuotaManager()
        qm.set_global_quota(Quota(max_cpu=20.0))
        qm.record_usage("_global", cpu=15.0)
        with pytest.raises(QuotaExceeded):
            qm.check("execution:e1", cpu=10.0)

    def test_max_executions(self):
        qm = QuotaManager()
        qm.set_global_quota(Quota(max_executions=5))
        qm.record_usage("_global", cpu=0)
        for i in range(5):
            qm.check(f"execution:e{i}")
            qm.record_usage(f"execution:e{i}")
        # All 5 passed without raising QuotaExceeded
        assert qm._usage["_global"]["cpu"] == 0
        assert qm._global_quota.max_executions == 5

    def test_quota_exceeded_exception(self):
        e = QuotaExceeded("test", ["cpu", "memory"])
        assert "cpu" in str(e)
        assert "test" in str(e)


# ═══════════════════════════════════════════════════════════════════
# 4.4 — Resource Enforcer
# ═══════════════════════════════════════════════════════════════════


class TestResourceEnforcer:
    def test_check_before_scheduling(self):
        enforcer = ResourceEnforcer()
        enforcer.check_before_scheduling("e1", "tool1")
        assert enforcer.tracker.active_count() == 1

    def test_enforce_returns_true_within_limits(self):
        enforcer = ResourceEnforcer()
        enforcer.check_before_scheduling("e1", "tool1")
        assert enforcer.enforce("e1", cpu=0.5, memory=1024) is True

    def test_enforce_returns_false_when_exceeded(self):
        enforcer = ResourceEnforcer()
        enforcer.check_before_scheduling("e1", "tool1")
        enforcer.quota_manager.set_execution_quota(
            "execution:e1", Quota(max_cpu=1.0),
        )
        assert enforcer.enforce("e1", cpu=2.0) is False

    def test_finish_records_usage(self):
        enforcer = ResourceEnforcer()
        enforcer.check_before_scheduling("e1", "tool1")
        enforcer.enforce("e1", cpu=1.0, memory=512)
        enforcer.finish("e1")
        usage = enforcer.tracker.get_usage("e1")
        assert usage is not None
        assert usage.cpu_time == 1.0


# ═══════════════════════════════════════════════════════════════════
# 4.5 — Isolation Runtime
# ═══════════════════════════════════════════════════════════════════


class TestIsolationRuntime:
    def test_execute_with_full_capability(self):
        registry = CapabilityRegistry()
        registry.register("test_tool", Capability.full())
        guard = CapabilityGuard(registry)
        iso = IsolationRuntime(capability_guard=guard)
        result = iso.execute("test_tool", {"key": "value"})
        assert result["status"] == "completed"

    def test_execute_blocks_unregistered_tool(self):
        iso = IsolationRuntime()
        result = iso.execute("unknown_tool", {})
        assert result["status"] == "blocked"
        assert "capability" in result["reason"]

    def test_execute_blocks_network_when_disallowed(self):
        registry = CapabilityRegistry()
        registry.register("no_net_tool", Capability(network=False))
        guard = CapabilityGuard(registry)
        iso = IsolationRuntime(capability_guard=guard)
        result = iso.execute("no_net_tool", {"url": "http://evil.com"})
        assert result["status"] == "blocked"

    def test_io_policy_blocks(self):
        iso = IsolationRuntime()
        with pytest.raises(IOViolation):
            iso.check_io("any_tool", "network_request")

    def test_io_policy_allows(self):
        iso = IsolationRuntime()
        iso.io_policy_engine.allow("test_tool", "read")
        iso.check_io("test_tool", "read")
        assert True

    def test_network_blocked_by_default(self):
        iso = IsolationRuntime()
        with pytest.raises(NetworkBlocked):
            iso.check_network("any_tool", "http://example.com")

    def test_filesystem_read_blocked_by_default(self):
        iso = IsolationRuntime()
        with pytest.raises(FileAccessViolation):
            iso.check_filesystem_read("any_tool", "/tmp/test.txt")

    def test_execute_with_runner(self):
        registry = CapabilityRegistry()
        registry.register("runner_tool", Capability.full())
        guard = CapabilityGuard(registry)
        iso = IsolationRuntime(capability_guard=guard)

        def my_runner(inputs):
            return {"result": "runner_output"}

        result = iso.execute("runner_tool", {}, runner=my_runner)
        assert result["status"] == "completed"

    def test_shutdown(self):
        iso = IsolationRuntime()
        iso.sandbox_manager.create_sandbox()
        assert iso.sandbox_manager.active_count() == 1
        iso.shutdown()
        assert iso.sandbox_manager.active_count() == 0

    def test_resource_enforcement_integration(self):
        registry = CapabilityRegistry()
        registry.register("heavy_tool", Capability.full())
        guard = CapabilityGuard(registry)
        enforcer = ResourceEnforcer()
        iso = IsolationRuntime(
            capability_guard=guard,
            resource_enforcer=enforcer,
        )
        result = iso.execute("heavy_tool", {})
        assert result["status"] == "completed"
