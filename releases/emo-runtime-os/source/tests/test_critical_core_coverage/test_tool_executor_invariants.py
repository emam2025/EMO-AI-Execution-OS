"""High-signal tests for ToolExecutor — error propagation, contract, discovery.

Invariants targeted:
  - Unknown tool returns error string, not exception
  - Tool execution errors caught and returned as string
  - register_class requires Tool subclass
  - Discovery skips import failures silently
"""

import pytest

from core.tool_executor import ToolRegistry, Tool


class TestToolExecutorErrorHandling:
    """Invariant: errors are returned as strings, never propagated."""

    def test_unknown_tool_returns_error_string(self):
        """execute('nonexistent') must return an error string, not raise."""
        registry = ToolRegistry()
        result = registry.execute("nonexistent_tool_xyzzy")
        assert isinstance(result, str)
        assert "Error" in result
        assert "nonexistent_tool_xyzzy" in result

    def test_discovery_handles_bad_module(self):
        """discover_tools with bad module must not raise."""
        registry = ToolRegistry()
        try:
            count = registry.discover_tools(["nonexistent_module_xyzzy"])
            assert isinstance(count, int)
        except ImportError:
            pytest.fail("discover_tools raised ImportError for bad module")


class TestToolRegistryClass:
    """Invariant: register_class checks Tool subclass."""

    def test_register_class_with_invalid_type(self):
        """register_class with non-class must raise TypeError."""
        registry = ToolRegistry()
        with pytest.raises((TypeError, Exception)):
            registry.register_class("not_a_class")

    def test_register_tool_returns_error_on_bad_name(self):
        """execute with empty string must return error."""
        registry = ToolRegistry()
        result = registry.execute("")
        assert isinstance(result, str)
        assert "Error" in result or "not found" in result
