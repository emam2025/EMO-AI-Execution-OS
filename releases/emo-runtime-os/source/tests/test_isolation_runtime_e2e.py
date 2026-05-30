"""Phase 4.5 — IsolationRuntime E2E integration tests.

Tests the full 5-step RULE 3 execution flow:
  1. CapabilityGuard.validate()
  2. ResourceEnforcer.check_before_scheduling()
  3. SandboxManager.create_sandbox()
  4. SandboxExecutor.execute() / execute_direct()
  5. ResourceEnforcer.finish()

Ref: DEVELOPER.md §15.15b §4.5
Ref: Canon RULE 1-4
Ref: Canon LAW 10, LAW 13
"""

import time

import pytest

from core.runtime.isolation.isolation_runtime import IsolationRuntime
from core.runtime.isolation.capability_guard import CapabilityGuard
from core.runtime.isolation.resource_enforcer import ResourceEnforcer
from core.runtime.isolation.sandbox_executor import SandboxExecutor
from core.runtime.isolation.io_policy_engine import IOPolicyEngine
from core.runtime.sandbox.sandbox_context import (
    SandboxContext,
    FilesystemMode,
    NetworkMode,
)
from core.runtime.sandbox.sandbox_manager import SandboxManager
from core.security.capabilities.capability_model import (
    Capability,
    AccessMode,
)
from core.security.capabilities.capability_registry import CapabilityRegistry
from core.runtime.io.io_policy_engine import IOPolicy, IOViolation
from core.runtime.io.network_isolation import NetworkIsolation, NetworkPolicy, NetworkBlocked
from core.runtime.io.filesystem_isolation import (
    FilesystemIsolation,
    FilesystemPolicy,
    AccessLevel,
)
from core.runtime.resources.quota_manager import QuotaManager, Quota


def _make_registry() -> CapabilityRegistry:
    reg = CapabilityRegistry()
    reg.register(
        "simple_tool",
        Capability(
            network=False,
            filesystem=AccessMode.NONE,
            subprocess=False,
            max_cpu=30.0,
            max_memory=256 * 1024 * 1024,
        ),
    )
    reg.register(
        "network_tool",
        Capability(
            network=True,
            filesystem=AccessMode.NONE,
            subprocess=False,
            max_cpu=30.0,
            max_memory=256 * 1024 * 1024,
            allowed_domains=["example.com"],
        ),
    )
    reg.register(
        "blocked_tool",
        Capability(
            network=False,
            filesystem=AccessMode.NONE,
            subprocess=False,
            max_cpu=30.0,
            max_memory=256 * 1024 * 1024,
        ),
    )
    return reg


def _make_runtime(registry=None) -> IsolationRuntime:
    return IsolationRuntime(
        capability_guard=CapabilityGuard(registry=registry or _make_registry()),
    )


class TestIsolationRuntimeE2EFlow:
    """Task 4: test_isolation_runtime_e2e_flow.py"""

    def test_full_execution_flow_simple_tool(self):
        """Full RULE 3 5-step flow with a simple tool via execute_direct."""
        runtime = _make_runtime()

        def identity(inputs):
            return {"received": inputs}

        result = runtime.execute("simple_tool", {"key": "value"}, runner=identity)
        assert result.get("status") == "completed"
        assert result.get("result") == {"received": {"key": "value"}}
        assert "execution_id" in result

    def test_capability_blocked_flow(self):
        """Step 1 blocks execution when capability is violated."""
        runtime = _make_runtime()
        result = runtime.execute("unknown_tool", {"url": "http://evil.com"})
        assert result.get("status") == "blocked"
        assert result.get("reason") == "capability_violation"

    def test_io_check_delegation(self):
        """IO check delegates to IOPolicyEngine (RULE 2)."""
        runtime = _make_runtime()
        runtime.io_policy_engine.allow("test_tool", "file.read")
        runtime.check_io("test_tool", "file.read", "/tmp/test.txt")

    def test_io_check_blocked(self):
        """IO check raises when operation is blocked (RULE 2)."""
        runtime = _make_runtime()
        runtime.io_policy_engine.block("test_tool", "network.get")
        with pytest.raises(IOViolation):
            runtime.check_io("test_tool", "network.get", "http://evil.com")

    def test_network_check_delegation(self):
        """Network check delegates to NetworkIsolation."""
        runtime = _make_runtime()
        runtime.network_isolation.set_policy(
            "test_tool",
            NetworkPolicy(allow_outbound=True),
        )
        runtime.check_network("test_tool", "http://example.com/api")

    def test_network_check_blocked(self):
        """Network check raises when domain is blocked."""
        runtime = _make_runtime()
        with pytest.raises(NetworkBlocked):
            runtime.check_network("test_tool", "http://evil.com")

    def test_filesystem_read_check(self):
        """Filesystem read check delegates to FilesystemIsolation."""
        runtime = _make_runtime()
        runtime.filesystem_isolation.set_policy(
            "test_tool",
            FilesystemPolicy(
                access_level=AccessLevel.READ,
                allowed_paths=["/tmp/allowed"],
            ),
        )
        result = runtime.check_filesystem_read("test_tool", "/tmp/allowed/foo.txt")
        assert result is not None

    def test_shutdown_cleanup(self):
        """shutdown() destroys sandboxes without error."""
        runtime = _make_runtime()
        runtime.shutdown()

    def test_blocked_tool_no_network(self):
        """Tool with NONE network produces blocked result for network context."""
        runtime = _make_runtime()
        context = SandboxContext(network_mode=NetworkMode.FULL)
        result = runtime.execute(
            "blocked_tool",
            {"url": "http://example.com"},
            sandbox_context=context,
        )
        assert result.get("status") == "blocked"

    def test_blocked_tool_no_filesystem(self):
        """Tool with NONE filesystem produces blocked result for FS context."""
        runtime = _make_runtime()
        context = SandboxContext(filesystem_mode=FilesystemMode.FULL)
        result = runtime.execute(
            "blocked_tool",
            {"path": "/tmp/test.txt"},
            sandbox_context=context,
        )
        assert result.get("status") == "blocked"
