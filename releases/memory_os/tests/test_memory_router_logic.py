"""Task 2 — Memory Router logic: 10 tests.

Classification precision, scope selection, budget allocation, routing pipeline.
"""

import tempfile

import pytest

from releases.memory_os.core.memory.hierarchy import MemoryHierarchy
from releases.memory_os.core.memory.memory_router import (
    MemoryRouter,
    QueryClass,
    TokenBudgetExceeded,
)


@pytest.fixture
def router():
    tmp = tempfile.mkdtemp(prefix="router_")
    h = MemoryHierarchy(base_dir=tmp)
    h.store("episodic", "project_plan", {"plan": "sprint 1"}, "t1", "p1", "a1", "ct1")
    h.store("semantic", "api_doc", {"endpoint": "/users"}, "t1", "p1", "a1", "ct1")
    h.store("procedural", "deploy_steps", {"steps": ["build", "push"]}, "t1", "p1", "a1", "ct1")
    r = MemoryRouter(hierarchy=h, tenant_id="t1", project_id="p1", agent_id="a1", cognitive_trace_id="ct1")
    yield r


class TestQueryClassification:
    def test_project_keyword_detected(self, router):
        cls = router.classify_query("show me the project plan for this feature")
        assert cls == QueryClass.PROJECT

    def test_agent_keyword_detected(self, router):
        cls = router.classify_query("what did the agent say in the last session")
        assert cls == QueryClass.AGENT

    def test_global_keyword_detected(self, router):
        cls = router.classify_query("global settings for all projects")
        assert cls == QueryClass.GLOBAL

    def test_empty_query_returns_unknown(self, router):
        cls = router.classify_query("")
        assert cls == QueryClass.UNKNOWN

    def test_mixed_keywords_defaults_to_highest_score(self, router):
        cls = router.classify_query("project repo feature agent")
        assert cls == QueryClass.PROJECT


class TestBudgetAllocation:
    def test_default_budget(self, router):
        budget = router.allocate_budget("short query", scope=None)
        from releases.memory_os.core.models.memory import MemoryScope
        base = 4096
        assert budget <= base
        assert budget >= 128

    def test_long_query_reduces_budget(self, router):
        long_q = "word " * 60
        short_budget = router.allocate_budget("hi", scope=None)
        long_budget = router.allocate_budget(long_q, scope=None)
        assert long_budget < short_budget

    def test_minimum_budget_floor(self, router):
        tiny = router.allocate_budget("x", scope=None, base=100)
        assert tiny >= 128


class TestRoutingPipeline:
    def test_router_requires_tenant_id_at_init(self):
        with pytest.raises(ValueError, match="tenant_id"):
            MemoryRouter(hierarchy=None, tenant_id="")

    def test_route_and_retrieve_returns_entries(self, router):
        result = router.route_and_retrieve("find project plan", limit=10)
        assert "entries" in result
        assert result["classification"] in ("project", "agent", "global")
        assert result["tenant_id"] == "t1"

    def test_route_and_retrieve_respects_tenant_id(self, router):
        result = router.route_and_retrieve("show project plan", tenant_id="t1", project_id="p1")
        assert result["tenant_id"] == "t1"

    def test_route_and_retrieve_without_tenant_fails(self, router):
        with pytest.raises(ValueError, match="tenant_id"):
            router.route_and_retrieve("test", tenant_id="")

    def test_classification_precision_on_mock_dataset(self, router):
        test_cases = [
            ("project repo codebase", QueryClass.PROJECT),
            ("agent conversation", QueryClass.AGENT),
            ("global config", QueryClass.GLOBAL),
        ]
        correct = 0
        for q, expected in test_cases:
            if router.classify_query(q) == expected:
                correct += 1
        precision = correct / len(test_cases)
        assert precision >= 0.9, f"classification_precision={precision} < 0.9"
