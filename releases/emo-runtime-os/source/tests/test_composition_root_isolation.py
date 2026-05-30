"""Phase 4.5 — CompositionRoot LAW 13 enforcement tests.

Tests:
  - RuntimeError when build_execution_engine() called without IsolationRuntime
  - Successful build when IsolationRuntime is set
  - Property access and mutation of isolation_runtime

Ref: DEVELOPER.md §15.15b §4.5
Ref: Canon LAW 13 (No direct service calls)
Ref: Canon RULE 1 (No Direct Execution)
"""

import pytest

from core.composition.root import CompositionRoot


class TestCompositionRootEnforcesIsolation:
    """Task 5: test_composition_root_enforces_isolation.py"""

    def test_rejects_without_isolation_runtime(self):
        """LAW 13: RuntimeError when building ExecutionEngine without isolation.

        CompositionRoot MUST refuse to build an ExecutionEngine unless
        isolation_runtime has been set (in strict_isolation mode).
        """
        root = CompositionRoot(strict_isolation=True)
        with pytest.raises(RuntimeError) as exc_info:
            root.build_execution_engine()
        assert "LAW 13" in str(exc_info.value)
        assert "IsolationRuntime" in str(exc_info.value)

    def test_property_defaults_to_none(self):
        """isolation_runtime property defaults to None."""
        root = CompositionRoot()
        assert root.isolation_runtime is None

    def test_property_setter(self):
        """isolation_runtime can be set after construction."""
        root = CompositionRoot()
        root.isolation_runtime = "mock_isolation"
        assert root.isolation_runtime == "mock_isolation"

    def test_can_build_after_setting_isolation(self):
        """build_execution_engine() succeeds when isolation_runtime is set."""
        root = CompositionRoot()
        root.isolation_runtime = object()
        engine = root.build_execution_engine()
        assert engine is not None

    def test_singleton_after_setting_isolation(self):
        """build_execution_engine() returns the same instance."""
        root = CompositionRoot()
        root.isolation_runtime = object()
        engine1 = root.build_execution_engine()
        engine2 = root.build_execution_engine()
        assert engine1 is engine2

    def test_rejects_none_after_set_strict(self):
        """strict_isolation raises even after setting isolation to None."""
        root = CompositionRoot(strict_isolation=True)
        with pytest.raises(RuntimeError):
            root.build_execution_engine()
