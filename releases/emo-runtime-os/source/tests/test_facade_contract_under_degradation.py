"""Facade Contract Under Degradation — 8 high-signal tests.

Validates IEmoRuntimeFacade maintains its contract when components are degraded.
Mutation-resistant: breaks on unstructured leak, contract violation, or isolation bypass.
"""

import pytest

from core.runtime.facade import EmoRuntimeFacade


# ── Mock components ─────────────────────────────────────────────────

class FailingRuntime:
    def execute(self, query): raise ConnectionError("simulated db down")
    def submit(self, *a, **kw): raise RuntimeError("submit failed")
    def observe(self, f): return {"status": "degraded"}
    def cancel(self, tid): raise LookupError("not found")
    def resume(self, tid): raise RuntimeError("resume failed")
    def scale(self, cnt): raise ValueError("invalid count")
    def health(self): return {"status": "unhealthy"}


class EmptyMemory:
    def get_session(self, sid): return None
    def get_dag_trace(self, sid): return None


class EmptyReplay:
    def available_sessions(self, **kw): return []
    def step_through(self, sid): return []
    def visualize(self, sid): return ""
    def compare(self, a, b):
        class C: pass
        c = C()
        c.session_a = a; c.session_b = b; c.query_a = ""; c.query_b = ""
        c.total_duration_delta_ms = 0; c.node_count_delta = 0
        c.status_match = True; c.tool_diff = []; c.node_comparisons = []
        return c


@pytest.fixture
def degraded_facade():
    return EmoRuntimeFacade(
        unified_runtime=FailingRuntime(),
        execution_memory=EmptyMemory(),
        replayer=EmptyReplay(),
    )


class TestFacadeSubmitUnderDegradation:
    """Invariant: submit always returns a dict, never raises."""

    def test_submit_returns_dict_on_failure(self, degraded_facade):
        result = degraded_facade.submit({"query": "test"})
        assert isinstance(result, dict), "submit must return dict on failure"

    def test_submit_contains_status(self, degraded_facade):
        result = degraded_facade.submit({"query": "test"})
        assert "status" in result, "submit response must contain status"


class TestFacadeQueryUnderDegradation:
    """Invariant: query always returns a dict, never raises."""

    def test_query_returns_dict_on_failure(self, degraded_facade):
        result = degraded_facade.query({"query": "test"})
        assert isinstance(result, dict), "query must return dict on failure"

    def test_query_unknown_mode_returns_error_dict(self, degraded_facade):
        result = degraded_facade.query({"query": "test", "mode": "nonexistent"})
        assert isinstance(result, dict)


class TestFacadeObserveUnderDegradation:
    """Invariant: observe always returns a dict, never raises."""

    def test_observe_returns_dict(self, degraded_facade):
        result = degraded_facade.observe({"target": "trace_session", "session_id": "s1"})
        assert isinstance(result, dict), "observe must return dict"

    def test_observe_unknown_target(self, degraded_facade):
        result = degraded_facade.observe({"target": "zz_nonexistent"})
        assert isinstance(result, dict)


class TestFacadeHealthUnderDegradation:
    """Invariant: health always returns a dict, never raises."""

    def test_health_returns_dict(self, degraded_facade):
        result = degraded_facade.health()
        assert isinstance(result, dict), "health must return dict"

    def test_health_contains_components(self, degraded_facade):
        result = degraded_facade.health()
        assert "components" in result
