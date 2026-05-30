"""Phase 4.2 — CapabilityGuard isolation tests.

Tests:
  - Rejects unauthorized tools (no capability registered)
  - Rejects capability/context mismatch
  - Accepts valid capability+context pairs
  - Returns structured CapabilityStatus

Ref: DEVELOPER.md §15.15b §4.2
Ref: Canon RULE 3 (Capability First)
"""

from core.runtime.isolation.capability_guard import (
    CapabilityGuard,
    CapabilityStatus,
)
from core.runtime.sandbox.sandbox_context import (
    SandboxContext,
    FilesystemMode,
    NetworkMode,
)
from core.security.capabilities.capability_model import (
    Capability,
    AccessMode,
)
from core.security.capabilities.capability_registry import CapabilityRegistry


def _make_registry() -> CapabilityRegistry:
    reg = CapabilityRegistry()
    reg.register(
        "web_fetch",
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
        "file_reader",
        Capability(
            network=False,
            filesystem=AccessMode.READ,
            subprocess=False,
            max_cpu=60.0,
            max_memory=512 * 1024 * 1024,
            allowed_paths=["/tmp/allowed"],
        ),
    )
    reg.register(
        "full_access",
        Capability(
            network=True,
            filesystem=AccessMode.FULL,
            subprocess=True,
            max_cpu=120.0,
            max_memory=1024 * 1024 * 1024,
        ),
    )
    reg.register(
        "no_fs_no_net",
        Capability(
            network=False,
            filesystem=AccessMode.NONE,
            subprocess=False,
            max_cpu=10.0,
            max_memory=64 * 1024 * 1024,
        ),
    )
    return reg


def _make_guard(registry=None):
    return CapabilityGuard(registry=registry or _make_registry())


class TestCapabilityGuardRejectsUnauthorized:
    """Task 1: test_capability_guard_rejects_unauthorized.py"""

    def test_rejects_unregistered_tool(self):
        """RULE 3: NO capability → NO execution."""
        status = _make_guard().validate("unknown_tool", {})
        assert not status.allowed
        assert "No capability registered" in status.reason

    def test_rejects_filesystem_mismatch(self):
        """Capability denies FS but context requests FULL."""
        context = SandboxContext(filesystem_mode=FilesystemMode.FULL)
        status = _make_guard().validate("no_fs_no_net", {}, context)
        assert not status.allowed
        assert any("Filesystem" in v for v in status.violations)

    def test_rejects_network_mismatch(self):
        """Capability has no network but context requests FULL."""
        context = SandboxContext(network_mode=NetworkMode.FULL)
        status = _make_guard().validate("no_fs_no_net", {}, context)
        assert not status.allowed
        assert any("Network" in v for v in status.violations)

    def test_rejects_cpu_exceeds_capability(self):
        """Context cpu > capability max."""
        context = SandboxContext(cpu_limit=999.0)
        status = _make_guard().validate("no_fs_no_net", {}, context)
        assert not status.allowed
        assert "CPU" in status.reason

    def test_rejects_memory_exceeds_capability(self):
        """Context memory > capability max."""
        context = SandboxContext(memory_limit=999 * 1024 * 1024)
        status = _make_guard().validate("no_fs_no_net", {}, context)
        assert not status.allowed
        assert "memory" in status.reason.lower()

    def test_returns_structured_status(self):
        """CapabilityStatus has all fields."""
        status = _make_guard().validate("unknown_tool", {})
        assert isinstance(status, CapabilityStatus)
        assert hasattr(status, "allowed")
        assert hasattr(status, "capability")
        assert hasattr(status, "reason")
        assert hasattr(status, "violations")


class TestCapabilityGuardAcceptsValid:

    def test_accepts_known_tool_no_context(self):
        """Basic validation without SandboxContext."""
        status = _make_guard().validate("web_fetch", {})
        assert status.allowed
        assert status.capability is not None

    def test_accepts_matching_filesystem(self):
        """Capability and context both allow filesystem read."""
        context = SandboxContext(filesystem_mode=FilesystemMode.READ_ONLY)
        guard = _make_guard()
        status = guard.validate("file_reader", {"path": "/tmp/allowed/foo"}, context)
        assert status.allowed

    def test_accepts_full_access(self):
        """Full capability with matching context."""
        context = SandboxContext(
            filesystem_mode=FilesystemMode.FULL,
            network_mode=NetworkMode.FULL,
        )
        guard = _make_guard()
        status = guard.validate("full_access", {}, context)
        assert status.allowed

    def test_accepts_no_context_tool_without_fs_net(self):
        """Tool without FS/net capability, context with minimal."""
        guard = _make_guard()
        status = guard.validate("no_fs_no_net", {"expression": "2+2"})
        assert status.allowed

    def test_rejects_path_not_in_capability(self):
        """Context path not in capability allowed_paths."""
        context = SandboxContext(
            filesystem_mode=FilesystemMode.READ_ONLY,
            allowed_paths=["/tmp/not_allowed"],
        )
        guard = _make_guard()
        status = guard.validate("file_reader", {}, context)
        assert not status.allowed
        assert any("Path" in v for v in status.violations)
