"""Task 5 — Integration tests: 20 tests across all R2-A components.

Suites:
  - TestTenantIsolationInStorage        (5)
  - TestMemoryRouterClassification      (5)
  - TestContextWindowBudgetEnforcement   (5)
  - TestStorageLatency                   (5)
Total: 20 tests — 0 external dependencies.
"""

import tempfile
import time

import pytest

from releases.memory_os.core.memory.hierarchy import MemoryHierarchy
from releases.memory_os.core.memory.memory_router import MemoryRouter
from releases.memory_os.core.memory.storage_adapter import IsolationViolation, SQLiteStorage
from releases.memory_os.core.models.memory import MemoryEntry, MemoryLayer, MemoryScope


# ── fixtures ──────────────────────────────────────────────────

@pytest.fixture
def storage():
    tmp = tempfile.mkdtemp(prefix="int_")
    s = SQLiteStorage(base_dir=tmp)
    yield s
    s.close()


@pytest.fixture
def hierarchy():
    tmp = tempfile.mkdtemp(prefix="int_h_")
    h = MemoryHierarchy(base_dir=tmp)
    for i in range(3):
        h.store("episodic", f"k{i}", {"data": i}, "t1", "p1", "a1", "ct1")
    yield h


@pytest.fixture
def router(hierarchy):
    return MemoryRouter(
        hierarchy=hierarchy,
        tenant_id="t1",
        project_id="p1",
        agent_id="a1",
        cognitive_trace_id="ct1",
    )


# ── TestTenantIsolationInStorage (5 tests) ────────────────────

class TestTenantIsolationInStorage:
    def test_insert_requires_tenant_id(self, storage):
        with pytest.raises((ValueError, IsolationViolation), match="tenant_id"):
            storage.insert(
                MemoryEntry(
                    entry_id="e1", tenant_id="", project_id="p1", agent_id="a1",
                    layer=MemoryLayer.EPISODIC, key="k1", content_hash="h1",
                    payload={}, scope=MemoryScope.PROJECT,
                )
            )

    def test_select_requires_tenant_id(self, storage):
        with pytest.raises(IsolationViolation, match="tenant_id"):
            storage.select("", "p1", MemoryScope.PROJECT)

    def test_delete_requires_tenant_id(self, storage):
        with pytest.raises(IsolationViolation, match="tenant_id"):
            storage.delete("e1", "")

    def test_count_requires_tenant_id(self, storage):
        with pytest.raises(IsolationViolation, match="tenant_id"):
            storage.delete_expired("")

    def test_cross_tenant_isolation_enforced(self, storage):
        e1 = MemoryEntry(
            entry_id="e1", tenant_id="t1", project_id="p1", agent_id="a1",
            layer=MemoryLayer.EPISODIC, key="k1", content_hash="h1",
            payload={"secret": "t1-data"}, scope=MemoryScope.PROJECT,
        )
        e2 = MemoryEntry(
            entry_id="e2", tenant_id="t2", project_id="p1", agent_id="a1",
            layer=MemoryLayer.EPISODIC, key="k1", content_hash="h1",
            payload={"secret": "t2-data"}, scope=MemoryScope.PROJECT,
        )
        storage.insert(e1)
        storage.insert(e2)
        rows_t1 = storage.select("t1", "p1", MemoryScope.PROJECT)
        rows_t2 = storage.select("t2", "p1", MemoryScope.PROJECT)
        assert len(rows_t1) == 1
        assert len(rows_t2) == 1
        assert rows_t1[0]["tenant_id"] == "t1"
        assert rows_t2[0]["tenant_id"] == "t2"


# ── TestMemoryRouterClassification (5 tests) ──────────────────

class TestMemoryRouterClassification:
    def test_project_classification(self, router):
        result = router.route_and_retrieve("project repo codebase feature")
        assert result["classification"] == "project"

    def test_agent_classification(self, router):
        result = router.route_and_retrieve("agent conversation session")
        assert result["classification"] == "agent"

    def test_global_classification(self, router):
        result = router.route_and_retrieve("global settings for all")
        assert result["classification"] == "global"

    def test_unknown_defaults_to_project(self, router):
        result = router.route_and_retrieve("xyzzy")
        assert result["classification"] in ("project", "unknown")
        assert result["scope"] in ("project",)

    def test_classification_returns_entries(self, router):
        result = router.route_and_retrieve("find project plan")
        assert isinstance(result["entries"], list)


# ── TestContextWindowBudgetEnforcement (5 tests) ──────────────

class TestContextWindowBudgetEnforcement:
    def test_budget_never_below_minimum(self, router):
        budget = router.allocate_budget("x" * 500, scope=MemoryScope.GLOBAL, base=50)
        assert budget >= 128

    def test_global_scope_gets_smaller_budget(self, router):
        proj_budget = router.allocate_budget("test", scope=MemoryScope.PROJECT, base=4096)
        global_budget = router.allocate_budget("test", scope=MemoryScope.GLOBAL, base=1024)
        assert global_budget <= proj_budget

    def test_budget_returned_in_route_result(self, router):
        result = router.route_and_retrieve("project query")
        assert result["token_budget_allocated"] >= 128

    def test_entries_limited_by_budget(self, router):
        result = router.route_and_retrieve("test", limit=1)
        assert result["entries_returned"] <= 1

    def test_budget_allocated_is_positive(self, router):
        budget = router.allocate_budget("short query")
        assert budget > 0


# ── TestStorageLatency (5 tests) ──────────────────────────────

class TestStorageLatency:
    def test_insert_latency_under_10ms(self, storage):
        entry = MemoryEntry(
            entry_id="lat-e1", tenant_id="t1", project_id="p1", agent_id="a1",
            layer=MemoryLayer.EPISODIC, key="lat-k1", content_hash="h1",
            payload={"data": "x" * 100}, scope=MemoryScope.PROJECT,
        )
        start = time.perf_counter()
        for _ in range(50):
            storage.insert(entry)
        elapsed = (time.perf_counter() - start) / 50
        assert elapsed < 0.01, f"avg insert latency {elapsed*1000:.2f}ms >= 10ms"

    def test_select_latency_under_10ms(self, storage):
        for i in range(100):
            storage.insert(MemoryEntry(
                entry_id=f"lat-e{i}", tenant_id="t1", project_id="p1", agent_id="a1",
                layer=MemoryLayer.EPISODIC, key=f"lat-k{i}", content_hash="h1",
                payload={"i": i}, scope=MemoryScope.PROJECT,
            ))
        start = time.perf_counter()
        for _ in range(20):
            storage.select("t1", "p1", MemoryScope.PROJECT, limit=10)
        elapsed = (time.perf_counter() - start) / 20
        assert elapsed < 0.01, f"avg select latency {elapsed*1000:.2f}ms >= 10ms"

    def test_multitenant_select_latency_under_10ms(self, storage):
        for t in ["t1", "t2", "t3"]:
            for i in range(20):
                storage.insert(MemoryEntry(
                    entry_id=f"lat-{t}-e{i}", tenant_id=t, project_id="p1", agent_id="a1",
                    layer=MemoryLayer.EPISODIC, key=f"lat-{t}-k{i}", content_hash="h1",
                    payload={"t": t, "i": i}, scope=MemoryScope.PROJECT,
                ))
        start = time.perf_counter()
        for _ in range(20):
            storage.select("t2", "p1", MemoryScope.PROJECT, limit=10)
        elapsed = (time.perf_counter() - start) / 20
        assert elapsed < 0.01, f"avg multi-tenant select latency {elapsed*1000:.2f}ms >= 10ms"

    def test_delete_latency_under_10ms(self, storage):
        entry = MemoryEntry(
            entry_id="lat-del", tenant_id="t1", project_id="p1", agent_id="a1",
            layer=MemoryLayer.EPISODIC, key="lat-del-k", content_hash="h1",
            payload={}, scope=MemoryScope.PROJECT,
        )
        storage.insert(entry)
        start = time.perf_counter()
        storage.delete("lat-del", "t1")
        elapsed = time.perf_counter() - start
        assert elapsed < 0.01, f"delete latency {elapsed*1000:.2f}ms >= 10ms"

    def test_bulk_insert_budget_not_exceeded(self, storage):
        start = time.perf_counter()
        for i in range(200):
            storage.insert(MemoryEntry(
                entry_id=f"bulk-e{i}", tenant_id="t1", project_id="p1", agent_id="a1",
                layer=MemoryLayer.EPISODIC, key=f"bulk-k{i}", content_hash="h1",
                payload={"i": i}, scope=MemoryScope.PROJECT,
            ))
        total = time.perf_counter() - start
        avg = total / 200
        assert avg < 0.01, f"avg bulk insert latency {avg*1000:.2f}ms >= 10ms"
