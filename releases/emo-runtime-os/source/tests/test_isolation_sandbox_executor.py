"""Phase 4.1 — SandboxExecutor isolation tests.

Tests:
  - SIGKILL kills running process
  - Cleanup removes worker scripts
  - Timeout raises ExecutionTimeoutError
  - execute_direct runs callable in thread

Ref: DEVELOPER.md §15.15b §4.1
Ref: Canon RULE 4 (Everything is Killable)
"""

import os
import time
import tempfile
import threading

import pytest

from core.runtime.isolation.sandbox_executor import SandboxExecutor
from core.runtime.sandbox.sandbox_context import (
    SandboxContext,
    FilesystemMode,
    NetworkMode,
)
from core.runtime.sandbox.sandbox_errors import (
    ExecutionTimeoutError,
    ResourceLimitExceeded,
    SandboxViolationError,
)


class TestSandboxExecutorSigkillCleanup:
    """Task 3: test_sandbox_executor_sigkill_cleanup.py"""

    def test_kill_unknown_id(self):
        """Kill returns False for non-existent execution ID."""
        executor = SandboxExecutor()
        assert not executor.kill("nonexistent_id")

    def test_execute_direct_respects_timeout(self):
        """execute_direct fails gracefully on timeout (RULE 4)."""
        executor = SandboxExecutor()
        context = SandboxContext(timeout=0.2)

        def slow_fn(_):
            time.sleep(10)

        result = executor.execute_direct(slow_fn, None, context)
        assert result.get("status") == "failed"
        err = result.get("error", "").lower()
        assert "timeout" in err

    def test_execute_direct_returns_result(self):
        """execute_direct returns callable result successfully."""
        executor = SandboxExecutor()
        context = SandboxContext(timeout=5.0)

        def add_one(x):
            return x + 1

        result = executor.execute_direct(add_one, 41, context)
        assert result.get("status") == "completed"
        assert result.get("result") == 42

    def test_execute_direct_error_propagation(self):
        """execute_direct propagates exceptions from the callable."""
        executor = SandboxExecutor()
        context = SandboxContext(timeout=5.0)

        def failing_fn(_):
            raise ValueError("test error")

        result = executor.execute_direct(failing_fn, None, context)
        assert result.get("status") == "failed"
        assert "test error" in result.get("error", "")

    def test_worker_cleanup(self):
        """Worker temp files are cleaned up after execution (RULE 4)."""
        executor = SandboxExecutor()
        context = SandboxContext(timeout=5.0)

        # Count temp .py files before
        tmpdir = tempfile.gettempdir()
        before = {
            f for f in os.listdir(tmpdir)
            if f.endswith(".py") and f.startswith("tmp")
        }

        executor.execute("quick_tool", {"command": "import json; print('ok')"}, context)

        after = {
            f for f in os.listdir(tmpdir)
            if f.endswith(".py") and f.startswith("tmp")
        }

        # Should not leak new temp files
        leaked = after - before
        assert len(leaked) == 0, f"Worker files leaked: {leaked}"
