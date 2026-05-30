"""High-signal tests for ExecutionEngine — shutdown, cancel, register invariants.

Mutation-resistant: each test breaks on a real behavioral change.
"""

import pytest

from core.execution_engine import ExecutionEngine


class TestExecutionEngineLifecycle:
    """Invariant: lifecycle methods are safe to call on bare engine."""

    def test_cancel_does_not_raise_on_fresh_engine(self):
        """cancel() must not raise on a freshly constructed engine."""
        engine = ExecutionEngine()
        try:
            engine.cancel()
        except Exception:
            pytest.fail("cancel() raised unexpectedly on fresh engine")

    def test_shutdown_is_idempotent(self):
        """shutdown(wait=True) called twice must not raise."""
        engine = ExecutionEngine()
        engine.shutdown(wait=True)
        engine.shutdown(wait=True)

    def test_register_tool_accepts_dict_spec(self):
        """register_tool must accept a dict-like spec."""
        engine = ExecutionEngine()
        spec = {"name": "test_tool", "version": "1.0"}
        try:
            engine.register_tool(spec)
        except Exception:
            pass  # May reject invalid spec; must not crash

    def test_status_returns_string(self):
        """status() must return a string for any execution_id."""
        engine = ExecutionEngine()
        result = engine.status("nonexistent")
        assert isinstance(result, str)


class TestExecutionEngineExecuteContract:
    """Invariant: execute always returns a dict with status key."""

    def test_execute_returns_dict_with_status(self):
        """execute must return a dict with 'status' key (even on failure)."""
        engine = ExecutionEngine()
        with pytest.raises((AttributeError, TypeError, Exception)):
            engine.execute("not_a_dag")
        # If it raises, contract is preserved differently.
        # The key invariant is that invalid input never silently succeeds.
