"""Tests for API Compliance Checker — frozen public method enforcement."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import warnings
warnings.filterwarnings("ignore")
import logging
logging.disable(logging.CRITICAL)

from core.api_compliance import verify_frozen_methods, APIViolationError, check_extra_public_methods
from core.execution_engine import ExecutionEngine
from core.orchestrator import QueryPlanner


# ── Engine compliance ─────────────────────────────────────────────

def test_engine_frozen_methods_exist():
    """Every method in the v2 frozen set must be a public method."""
    verify_frozen_methods(
        ExecutionEngine,
        ExecutionEngine.FROZEN_PUBLIC_METHODS_V2,
        ExecutionEngine.API_VERSION,
    )
    assert True


def test_engine_api_version_is_2_0_0():
    assert ExecutionEngine.API_VERSION == "2.0.0"


def test_engine_frozen_set_includes_execute_streaming():
    assert "execute_streaming" in ExecutionEngine.FROZEN_PUBLIC_METHODS_V2


def test_engine_frozen_set_exact():
    expected = {"execute", "execute_streaming", "cancel", "shutdown", "register_tool"}
    assert ExecutionEngine.FROZEN_PUBLIC_METHODS_V2 == expected


# ── Planner compliance ────────────────────────────────────────────

def test_planner_frozen_methods_exist():
    """Every method in the v2 frozen set must be a public method."""
    verify_frozen_methods(
        QueryPlanner,
        QueryPlanner.FROZEN_PUBLIC_METHODS_V2,
        QueryPlanner.PLANNER_API_VERSION,
    )
    assert True


def test_planner_api_version_is_2_0_0():
    assert QueryPlanner.PLANNER_API_VERSION == "2.0.0"


def test_planner_frozen_set_exact():
    expected = {"plan", "get_tool_weights", "get_confidence_adjustment"}
    assert QueryPlanner.FROZEN_PUBLIC_METHODS_V2 == expected


# ── Violation detection ───────────────────────────────────────────

def test_missing_method_raises():
    class Fake:
        API_VERSION = "1.0.0"
        FROZEN_PUBLIC_METHODS_V2 = frozenset({"nonexistent_method_xyz"})
    try:
        verify_frozen_methods(Fake, Fake.FROZEN_PUBLIC_METHODS_V2, "1.0.0")
        assert False, "Should have raised"
    except APIViolationError as e:
        assert "nonexistent_method_xyz" in str(e)


def test_extra_public_methods_warns(caplog):
    import logging
    caplog.set_level(logging.WARNING)

    class Fake:
        API_VERSION = "1.0.0"
        FROZEN_PUBLIC_METHODS_V2 = frozenset({"existing_method"})
        def existing_method(self): pass
        def extra_method(self): pass

    check_extra_public_methods(Fake, Fake.FROZEN_PUBLIC_METHODS_V2, "1.0.0")
    assert any("extra_method" in record.message for record in caplog.records)
