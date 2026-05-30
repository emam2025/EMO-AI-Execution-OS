"""High-signal tests for QueryPlanner — constants, frozen API, exports.

Tests target exposed invariants without requiring full construction.
"""

import pytest

from core.orchestrator import (
    QueryPlanner,
    PLANNER_FROZEN_PUBLIC_METHODS,
    PLANNER_API_VERSION,
    PLANNER_VERSION,
)


class TestQueryPlannerConstants:
    """Invariant: frozen API and version are defined."""

    def test_planner_api_version_is_string(self):
        """PLANNER_API_VERSION must be a string."""
        assert isinstance(PLANNER_API_VERSION, str)
        assert len(PLANNER_API_VERSION) > 0

    def test_planner_version_is_string(self):
        """PLANNER_VERSION must be a string."""
        assert isinstance(PLANNER_VERSION, str)
        assert len(PLANNER_VERSION) > 0


class TestQueryPlannerAPICompliance:
    """Invariant: frozen public methods must exist on QueryPlanner."""

    def test_frozen_methods_exist(self):
        """Frozen methods must all exist on QueryPlanner."""
        for method in PLANNER_FROZEN_PUBLIC_METHODS:
            assert hasattr(QueryPlanner, method), (
                f"Frozen method '{method}' missing from QueryPlanner"
            )

    def test_frozen_methods_is_frozenset(self):
        """PLANNER_FROZEN_PUBLIC_METHODS must be a frozenset."""
        assert isinstance(PLANNER_FROZEN_PUBLIC_METHODS, frozenset)

    def test_frozen_methods_contains_plan(self):
        """Frozen methods must include 'plan'."""
        assert "plan" in PLANNER_FROZEN_PUBLIC_METHODS
