"""Task 1 — Memory hierarchy isolation: 10 tests.

Verifies zero cross-tenant/project leakage in store/retrieve/prune.
"""

import tempfile
import uuid

import pytest

from releases.memory_os.core.memory.hierarchy import MemoryHierarchy
from releases.memory_os.core.memory.storage_adapter import IsolationViolation


@pytest.fixture
def hierarchy():
    tmp = tempfile.mkdtemp(prefix="iso_")
    h = MemoryHierarchy(base_dir=tmp)
    yield h


TENANT_A = "tenant-a"
TENANT_B = "tenant-b"
PROJ_1 = "proj-1"
PROJ_2 = "proj-2"
AGENT = "agent-1"
TRACE = "trace-1"


class TestTenantIsolation:
    def test_store_requires_tenant_id(self, hierarchy):
        with pytest.raises(ValueError, match="tenant_id"):
            hierarchy.store(
                layer="episodic", key="k1", payload={"x": 1},
                tenant_id="", project_id=PROJ_1, agent_id=AGENT,
                cognitive_trace_id=TRACE,
            )

    def test_retrieve_requires_tenant_id(self, hierarchy):
        with pytest.raises(ValueError, match="tenant_id"):
            hierarchy.retrieve(
                layer="episodic", query={},
                tenant_id="", project_id=PROJ_1,
                cognitive_trace_id=TRACE,
            )

    def test_prune_requires_tenant_id(self, hierarchy):
        with pytest.raises(ValueError, match="tenant_id"):
            hierarchy.prune(
                layer="episodic", policy="ttl",
                tenant_id="", project_id=PROJ_1,
                cognitive_trace_id=TRACE,
            )

    def test_tenant_a_data_invisible_to_tenant_b(self, hierarchy):
        hierarchy.store("episodic", "secret", {"msg": "a-secret"}, TENANT_A, PROJ_1, AGENT, TRACE)
        results = hierarchy.retrieve("episodic", {}, TENANT_B, PROJ_1, TRACE)
        entries = [r for r in results if r["key"] == "secret"]
        assert len(entries) == 0

    def test_multiple_tenants_no_cross_contamination(self, hierarchy):
        for i in range(5):
            hierarchy.store("episodic", f"k{i}", {"val": i}, TENANT_A, PROJ_1, AGENT, TRACE)
        for i in range(3):
            hierarchy.store("episodic", f"k{i}", {"val": i}, TENANT_B, PROJ_1, AGENT, TRACE)
        rows_a = hierarchy.retrieve("episodic", {}, TENANT_A, PROJ_1, TRACE, limit=100)
        rows_b = hierarchy.retrieve("episodic", {}, TENANT_B, PROJ_1, TRACE, limit=100)
        assert len(rows_a) == 5
        assert len(rows_b) == 3


class TestProjectIsolation:
    def test_project_a_data_invisible_to_project_b(self, hierarchy):
        hierarchy.store("episodic", "secret", {"msg": "p1-secret"}, TENANT_A, PROJ_1, AGENT, TRACE)
        results = hierarchy.retrieve("episodic", {"scope": "project"}, TENANT_A, PROJ_2, TRACE)
        entries = [r for r in results if r["key"] == "secret"]
        assert len(entries) == 0

    def test_store_requires_project_id(self, hierarchy):
        with pytest.raises(ValueError, match="project_id"):
            hierarchy.store(
                layer="episodic", key="k1", payload={},
                tenant_id=TENANT_A, project_id="", agent_id=AGENT,
                cognitive_trace_id=TRACE,
            )

    def test_context_window_requires_project_id(self, hierarchy):
        with pytest.raises(ValueError, match="project_id"):
            hierarchy.get_context_window(
                tenant_id=TENANT_A, project_id="",
                cognitive_trace_id=TRACE,
            )

    def test_prune_respects_tenant_boundary(self, hierarchy):
        hierarchy.store("episodic", "k1", {"x": 1}, TENANT_A, PROJ_1, AGENT, TRACE)
        hierarchy.store("episodic", "k2", {"x": 2}, TENANT_A, PROJ_1, AGENT, TRACE, ttl_seconds=0)
        hierarchy.prune("episodic", "ttl", TENANT_A, PROJ_1, TRACE)
        remaining = hierarchy.retrieve("episodic", {}, TENANT_A, PROJ_1, TRACE, limit=100)
        assert len(remaining) == 1

    def test_tenant_b_prune_does_not_affect_tenant_a(self, hierarchy):
        hierarchy.store("episodic", "a_keep", {"val": "a"}, TENANT_A, PROJ_1, AGENT, TRACE)
        hierarchy.store("episodic", "b_expire", {"val": "b"}, TENANT_B, PROJ_1, AGENT, TRACE, ttl_seconds=0)
        hierarchy.store("episodic", "b_keep", {"val": "b2"}, TENANT_B, PROJ_1, AGENT, TRACE)
        hierarchy.prune("episodic", "ttl", TENANT_B, PROJ_1, TRACE)
        rows_a = hierarchy.retrieve("episodic", {}, TENANT_A, PROJ_1, TRACE, limit=100)
        rows_b = hierarchy.retrieve("episodic", {}, TENANT_B, PROJ_1, TRACE, limit=100)
        assert len(rows_a) == 1
        assert rows_a[0]["key"] == "a_keep"
        assert len(rows_b) == 1
        assert rows_b[0]["key"] == "b_keep"
