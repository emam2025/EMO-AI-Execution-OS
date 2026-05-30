"""Tests for Phase E1 — Firecracker Runtime.

MicroVM-based execution isolation.
Skips if Firecracker prerequisites are not met.
"""

import pytest

from core.runtime.sandbox.firecracker_runtime import FirecrackerRuntime, FirecrackerResult


# Create a runtime without valid paths — will report not available
fc_runtime = FirecrackerRuntime()


class TestFirecrackerRuntime:
    def test_init(self):
        r = FirecrackerRuntime(kernel="vmlinux.bin", rootfs="rootfs.ext4")
        assert r._kernel == "vmlinux.bin"
        assert r._rootfs == "rootfs.ext4"

    def test_is_available_returns_bool(self):
        r = FirecrackerRuntime()
        assert isinstance(r.is_available(), bool)

    def test_execute_not_available(self):
        r = FirecrackerRuntime()
        result = r.execute("echo hello")
        assert result.error != ""

    def test_cleanup_all_no_crash(self):
        r = FirecrackerRuntime()
        count = r.cleanup_all()
        assert count == 0

    def test_list_active(self):
        r = FirecrackerRuntime()
        assert r.list_active() == {}

    @pytest.mark.skipif(fc_runtime.is_available(), reason="Firecracker is available — skip non-available test")
    def test_execute_without_prereqs(self):
        r = FirecrackerRuntime(kernel="/nonexistent/vmlinux", rootfs="/nonexistent/rootfs")
        result = r.execute("echo test")
        assert result.error != ""
        assert result.exit_code == -1

    def test_check_prerequisites_no_crash(self):
        r = FirecrackerRuntime(kernel="/nonexistent/vmlinux", rootfs="/nonexistent/rootfs")
        r._check_prerequisites()
        assert r._prerequisites_met is False
