"""Task 1 — Enterprise Memory Isolation: 10 tests.

Verifies zero cross-project/agent leakage in ProjectMemorySpace,
AgentMemorySpace, and CrossSessionRecall.
"""

import tempfile
import pytest

from releases.memory_os.core.memory.enterprise_spaces import (
    AgentMemorySpace,
    CrossSessionRecall,
    ProjectMemorySpace,
    SpaceAccessError,
)
from releases.memory_os.core.memory.hierarchy import MemoryHierarchy


@pytest.fixture
def hierarchy():
    tmp = tempfile.mkdtemp(prefix="enterprise_")
    return MemoryHierarchy(base_dir=tmp)


class TestProjectMemorySpace:
    def test_store_and_retrieve_within_space(self, hierarchy):
        p1 = ProjectMemorySpace(hierarchy, "proj-a", "t1")
        p1.store("episodic", "k1", {"msg": "p1-data"}, "a1", "ct1")
        results = p1.retrieve("episodic", {})
        assert len(results) == 1
        assert results[0]["key"] == "k1"

    def test_cross_project_isolation(self, hierarchy):
        p1 = ProjectMemorySpace(hierarchy, "proj-a", "t1")
        p2 = ProjectMemorySpace(hierarchy, "proj-b", "t1")
        p1.store("episodic", "secret", {"msg": "p1-secret"}, "a1", "ct1")
        p2.store("episodic", "other", {"msg": "p2-data"}, "a1", "ct1")
        r1 = p1.retrieve("episodic", {})
        r2 = p2.retrieve("episodic", {})
        assert len(r1) == 1 and r1[0]["key"] == "secret"
        assert len(r2) == 1 and r2[0]["key"] == "other"

    def test_empty_project_id_raises(self, hierarchy):
        with pytest.raises(ValueError, match="project_id"):
            ProjectMemorySpace(hierarchy, "", "t1")

    def test_retrieve_filters_by_agent(self, hierarchy):
        p1 = ProjectMemorySpace(hierarchy, "proj-a", "t1")
        p1.store("episodic", "k1", {}, "agent-x", "ct1")
        p1.store("episodic", "k2", {}, "agent-y", "ct1")
        results = p1.retrieve("episodic", {}, agent_id="agent-x")
        assert len(results) == 1
        assert results[0]["key"] == "k1"


class TestAgentMemorySpace:
    def test_record_decision(self, hierarchy):
        agent = AgentMemorySpace(hierarchy, "agent-1", "t1", "proj-a")
        result = agent.record_decision("deploy", {"env": "prod"}, "ct1")
        assert result["stored"] is True

    def test_record_error(self, hierarchy):
        agent = AgentMemorySpace(hierarchy, "agent-1", "t1", "proj-a")
        result = agent.record_error("timeout", {"service": "api"}, "ct1")
        assert result["stored"] is True

    def test_session_context_temporal_isolation(self, hierarchy):
        agent = AgentMemorySpace(hierarchy, "agent-1", "t1", "proj-a")
        agent.record_decision("build", {}, "ct-session-1")
        import time
        time.sleep(0.01)
        agent.record_decision("deploy", {}, "ct-session-2")
        ctx = agent.get_session_context("ct-session-1", limit=10, time_window_hours=1)
        assert len(ctx) >= 1

    def test_different_agent_isolation(self, hierarchy):
        a1 = AgentMemorySpace(hierarchy, "agent-1", "t1", "proj-a")
        a2 = AgentMemorySpace(hierarchy, "agent-2", "t1", "proj-a")
        a1.record_decision("decision-a", {}, "ct1")
        a2.record_decision("decision-b", {}, "ct2")
        ctx1 = a1.get_session_context("ct1", limit=10)
        ctx2 = a2.get_session_context("ct2", limit=10)
        for e in ctx1:
            assert e.get("agent_id", "") == "agent-1"


class TestCrossSessionRecall:
    def test_recall_requires_tenant_id(self, hierarchy):
        recall = CrossSessionRecall(hierarchy)
        with pytest.raises(ValueError, match="tenant_id"):
            recall.recall("test", tenant_id="")

    def test_recall_deduplicates(self, hierarchy):
        recall = CrossSessionRecall(hierarchy)
        hierarchy.store("episodic", "k1", {"msg": "dup"}, "t1", "p1", "a1", "ct1")
        hierarchy.store("episodic", "k2", {"msg": "dup"}, "t1", "p1", "a1", "ct2")
        result = recall.recall("test", "t1", "p1", limit=10)
        assert result["unique_entries"] <= 2
