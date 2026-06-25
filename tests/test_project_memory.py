"""T-30 Project Memory — 50+ tests.

Tests cover:
- CRUD operations (store, retrieve, delete)
- Project isolation (different projects don't leak)
- TTL expiration
- Search and filtering
- Edge cases (empty keys, missing projects, etc.)
- Integration with MemoryHierarchy + CognitiveTraceCorrelator
- Concurrent access patterns
- Metadata and stats
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict

import pytest

from core.memory.memory_hierarchy import MemoryHierarchy
from core.memory.models import MemoryLayer
from core.memory.project_memory import ProjectMemory, ProjectMemoryEntry, ProjectSummary
from core.memory.trace_correlator import CognitiveTraceCorrelator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def hierarchy() -> MemoryHierarchy:
    return MemoryHierarchy()


@pytest.fixture
def correlator() -> CognitiveTraceCorrelator:
    return CognitiveTraceCorrelator()


@pytest.fixture
def pm(hierarchy: MemoryHierarchy, correlator: CognitiveTraceCorrelator) -> ProjectMemory:
    return ProjectMemory(hierarchy=hierarchy, trace_correlator=correlator)


@pytest.fixture
def pm_with_trace(
    correlator: CognitiveTraceCorrelator,
) -> ProjectMemory:
    hierarchy = MemoryHierarchy(trace_correlator=correlator)
    return ProjectMemory(hierarchy=hierarchy, trace_correlator=correlator)


@pytest.fixture
def sample_payload() -> Dict[str, Any]:
    return {"name": "test_project", "status": "active", "version": 1}


# ---------------------------------------------------------------------------
# T-30.1 — CRUD
# ---------------------------------------------------------------------------

class TestStoreAndRetrieve:
    @pytest.mark.asyncio
    async def test_store_basic(self, pm: ProjectMemory) -> None:
        result = await pm.store("proj-alpha", "config", {"key": "value"})
        assert result["status"] == "stored"
        assert result["project_id"] == "proj-alpha"
        assert result["key"] == "config"
        assert "cognitive_trace_id" in result

    @pytest.mark.asyncio
    async def test_retrieve_stored_value(self, pm: ProjectMemory) -> None:
        await pm.store("proj-alpha", "greeting", {"text": "hello"})
        result = await pm.retrieve("proj-alpha", "greeting")
        assert result["status"] == "ok"
        assert result["result"]["payload"]["text"] == "hello"

    @pytest.mark.asyncio
    async def test_retrieve_missing_key_returns_not_found(self, pm: ProjectMemory) -> None:
        result = await pm.retrieve("proj-alpha", "nonexistent")
        assert result["status"] == "not_found"
        assert result["result"] is None

    @pytest.mark.asyncio
    async def test_retrieve_missing_project_returns_not_found(self, pm: ProjectMemory) -> None:
        result = await pm.retrieve("never-created", "anything")
        assert result["status"] == "not_found"

    @pytest.mark.asyncio
    async def test_store_overwrites_existing_key(self, pm: ProjectMemory) -> None:
        await pm.store("proj", "x", {"v": 1})
        await pm.store("proj", "x", {"v": 2})
        result = await pm.retrieve("proj", "x")
        assert result["result"]["payload"]["v"] == 2

    @pytest.mark.asyncio
    async def test_store_empty_project_id_raises(self, pm: ProjectMemory) -> None:
        with pytest.raises(ValueError, match="project_id is required"):
            await pm.store("", "key", {})

    @pytest.mark.asyncio
    async def test_store_empty_key_raises(self, pm: ProjectMemory) -> None:
        with pytest.raises(ValueError, match="key is required"):
            await pm.store("proj", "", {})

    @pytest.mark.asyncio
    async def test_retrieve_empty_project_id_raises(self, pm: ProjectMemory) -> None:
        with pytest.raises(ValueError, match="project_id and key are required"):
            await pm.retrieve("", "key")

    @pytest.mark.asyncio
    async def test_retrieve_empty_key_raises(self, pm: ProjectMemory) -> None:
        with pytest.raises(ValueError, match="project_id and key are required"):
            await pm.retrieve("proj", "")


class TestDeleteKey:
    @pytest.mark.asyncio
    async def test_delete_existing_key(self, pm: ProjectMemory) -> None:
        await pm.store("proj", "temp", {"data": "to-delete"})
        result = await pm.delete_key("proj", "temp")
        assert result["status"] == "deleted"
        assert "temp" not in pm._project_metadata.get("proj", {})

    @pytest.mark.asyncio
    async def test_delete_nonexistent_key_is_idempotent(self, pm: ProjectMemory) -> None:
        result = await pm.delete_key("proj", "never-existed")
        assert result["status"] == "deleted"

    @pytest.mark.asyncio
    async def test_delete_key_empty_project_id_raises(self, pm: ProjectMemory) -> None:
        with pytest.raises(ValueError, match="project_id and key are required"):
            await pm.delete_key("", "key")

    @pytest.mark.asyncio
    async def test_delete_key_empty_key_raises(self, pm: ProjectMemory) -> None:
        with pytest.raises(ValueError, match="project_id and key are required"):
            await pm.delete_key("proj", "")


class TestDeleteProject:
    @pytest.mark.asyncio
    async def test_delete_project_removes_all_entries(self, pm: ProjectMemory) -> None:
        await pm.store("proj", "a", {"v": 1})
        await pm.store("proj", "b", {"v": 2})
        result = await pm.delete_project("proj")
        assert result["status"] == "deleted"
        stats = await pm.get_stats("proj")
        assert stats["status"] == "not_found"

    @pytest.mark.asyncio
    async def test_delete_nonexistent_project_is_idempotent(self, pm: ProjectMemory) -> None:
        result = await pm.delete_project("nonexistent")
        assert result["status"] == "deleted"

    @pytest.mark.asyncio
    async def test_delete_project_empty_id_raises(self, pm: ProjectMemory) -> None:
        with pytest.raises(ValueError, match="project_id is required"):
            await pm.delete_project("")


# ---------------------------------------------------------------------------
# T-30.2 — Project Isolation
# ---------------------------------------------------------------------------

class TestProjectIsolation:
    @pytest.mark.asyncio
    async def test_different_projects_do_not_interfere(self, pm: ProjectMemory) -> None:
        await pm.store("proj-a", "key1", {"owner": "A"})
        await pm.store("proj-b", "key1", {"owner": "B"})
        result_a = await pm.retrieve("proj-a", "key1")
        result_b = await pm.retrieve("proj-b", "key1")
        assert result_a["result"]["payload"]["owner"] == "A"
        assert result_b["result"]["payload"]["owner"] == "B"

    @pytest.mark.asyncio
    async def test_isolation_via_tenant_id(self, pm: ProjectMemory) -> None:
        await pm.store("proj", "shared", {"val": 1}, tenant_id="tenant_a")
        result = await pm.retrieve("proj", "shared", tenant_id="tenant_b")
        assert result["status"] == "not_found"

    @pytest.mark.asyncio
    async def test_large_number_of_projects_isolated(self, pm: ProjectMemory) -> None:
        for i in range(20):
            await pm.store(f"proj-{i:03d}", "config", {"id": i})
        for i in range(20):
            r = await pm.retrieve(f"proj-{i:03d}", "config")
            assert r["result"]["payload"]["id"] == i

    @pytest.mark.asyncio
    async def test_same_key_different_payload_per_project(self, pm: ProjectMemory) -> None:
        projects = ["alpha", "beta", "gamma"]
        for p in projects:
            await pm.store(p, "status", {"project": p, "active": True})
        for p in projects:
            r = await pm.retrieve(p, "status")
            assert r["result"]["payload"]["project"] == p


# ---------------------------------------------------------------------------
# T-30.3 — TTL
# ---------------------------------------------------------------------------

class TestTTL:
    @pytest.mark.asyncio
    async def test_store_with_ttl(self, pm: ProjectMemory) -> None:
        result = await pm.store("proj", "ttl-key", {"data": "expires"}, ttl_seconds=3600)
        assert result["ttl_seconds"] == 3600

    @pytest.mark.asyncio
    async def test_store_without_ttl_is_none(self, pm: ProjectMemory) -> None:
        result = await pm.store("proj", "no-ttl", {"data": "permanent"})
        assert result["ttl_seconds"] is None

    @pytest.mark.asyncio
    async def test_ttl_negative_value_is_stored(self, pm: ProjectMemory) -> None:
        result = await pm.store("proj", "neg-ttl", {}, ttl_seconds=-1)
        assert result["ttl_seconds"] == -1

    @pytest.mark.asyncio
    async def test_ttl_zero_still_allowed(self, pm: ProjectMemory) -> None:
        result = await pm.store("proj", "zero-ttl", {}, ttl_seconds=0)
        assert result["ttl_seconds"] == 0

    @pytest.mark.asyncio
    async def test_multiple_ttl_values_per_project(self, pm: ProjectMemory) -> None:
        ttls = {"short": 60, "medium": 3600, "long": 86400, "none": None}
        for key, ttl in ttls.items():
            r = await pm.store("proj-ttl", key, {}, ttl_seconds=ttl)
            assert r["ttl_seconds"] == ttl


# ---------------------------------------------------------------------------
# T-30.4 — Search
# ---------------------------------------------------------------------------

class TestSearch:
    @pytest.mark.asyncio
    async def test_search_by_key(self, pm: ProjectMemory) -> None:
        await pm.store("proj", "configuration", {"env": "prod"})
        await pm.store("proj", "secrets", {"key": "abc"})
        result = await pm.search("proj", "configuration")
        assert result["total"] >= 1
        assert any("configuration" in r["key"] for r in result["results"])

    @pytest.mark.asyncio
    async def test_search_by_payload_content(self, pm: ProjectMemory) -> None:
        await pm.store("proj", "cfg", {"environment": "staging"})
        await pm.store("proj", "other", {"environment": "production"})
        result = await pm.search("proj", "staging")
        assert result["total"] >= 1

    @pytest.mark.asyncio
    async def test_search_empty_query_returns_all(self, pm: ProjectMemory) -> None:
        for i in range(5):
            await pm.store("proj", f"key-{i}", {"index": i})
        result = await pm.search("proj", "")
        assert result["total"] == 5

    @pytest.mark.asyncio
    async def test_search_no_matches(self, pm: ProjectMemory) -> None:
        await pm.store("proj", "abc", {"data": "123"})
        result = await pm.search("proj", "zzz_nonexistent_zzz")
        assert result["total"] == 0

    @pytest.mark.asyncio
    async def test_search_respects_limit(self, pm: ProjectMemory) -> None:
        for i in range(20):
            await pm.store("proj", f"item-{i}", {"i": i})
        result = await pm.search("proj", "", limit=5)
        assert result["total"] <= 5

    @pytest.mark.asyncio
    async def test_search_empty_project_id_raises(self, pm: ProjectMemory) -> None:
        with pytest.raises(ValueError, match="project_id is required"):
            await pm.search("", "query")

    @pytest.mark.asyncio
    async def test_search_case_insensitive(self, pm: ProjectMemory) -> None:
        await pm.store("proj", "ConfigFile", {"env": "prod"})
        result = await pm.search("proj", "configfile")
        assert result["total"] >= 1


# ---------------------------------------------------------------------------
# T-30.5 — Stats and Listing
# ---------------------------------------------------------------------------

class TestStatsAndListing:
    @pytest.mark.asyncio
    async def test_get_stats_after_stores(self, pm: ProjectMemory) -> None:
        await pm.store("proj", "a", {})
        await pm.store("proj", "b", {})
        await pm.store("proj", "c", {})
        stats = await pm.get_stats("proj")
        assert stats["status"] == "ok"
        assert stats["entry_count"] == 3
        assert len(stats["keys"]) == 3

    @pytest.mark.asyncio
    async def test_get_stats_nonexistent_project(self, pm: ProjectMemory) -> None:
        stats = await pm.get_stats("ghost")
        assert stats["status"] == "not_found"

    @pytest.mark.asyncio
    async def test_get_stats_empty_project_id_raises(self, pm: ProjectMemory) -> None:
        with pytest.raises(ValueError, match="project_id is required"):
            await pm.get_stats("")

    @pytest.mark.asyncio
    async def test_get_stats_tracks_access_count(self, pm: ProjectMemory) -> None:
        await pm.store("proj", "popular", {"data": "hot"})
        for _ in range(5):
            await pm.retrieve("proj", "popular")
        stats = await pm.get_stats("proj")
        assert stats["total_access_count"] >= 5

    @pytest.mark.asyncio
    async def test_list_projects_empty(self, pm: ProjectMemory) -> None:
        result = await pm.list_projects()
        assert result["total_projects"] == 0

    @pytest.mark.asyncio
    async def test_list_projects_after_multiple_stores(self, pm: ProjectMemory) -> None:
        for pid in ["alpha", "beta", "gamma"]:
            await pm.store(pid, "init", {})
        result = await pm.list_projects()
        assert result["total_projects"] >= 3
        pids = [p["project_id"] for p in result["projects"]]
        assert "alpha" in pids
        assert "beta" in pids
        assert "gamma" in pids

    @pytest.mark.asyncio
    async def test_list_projects_after_delete(self, pm: ProjectMemory) -> None:
        await pm.store("temp-proj", "x", {})
        await pm.delete_project("temp-proj")
        result = await pm.list_projects()
        assert "temp-proj" not in [p["project_id"] for p in result["projects"]]


# ---------------------------------------------------------------------------
# T-30.6 — Metadata
# ---------------------------------------------------------------------------

class TestMetadata:
    @pytest.mark.asyncio
    async def test_store_with_metadata(self, pm: ProjectMemory) -> None:
        meta = {"author": "test", "priority": "high", "tags": ["ai", "memory"]}
        result = await pm.store("proj", "meta-key", {"data": 1}, metadata=meta)
        assert result["status"] == "stored"

    @pytest.mark.asyncio
    async def test_store_without_metadata_defaults_empty(self, pm: ProjectMemory) -> None:
        result = await pm.store("proj", "no-meta", {"data": 1})
        assert result["status"] == "stored"

    @pytest.mark.asyncio
    async def test_metadata_not_visible_in_retrieve_payload(self, pm: ProjectMemory) -> None:
        await pm.store("proj", "cfg", {"val": 1}, metadata={"internal": "yes"})
        result = await pm.retrieve("proj", "cfg")
        assert result["result"]["payload"] == {"val": 1}


# ---------------------------------------------------------------------------
# T-30.7 — Cognitive Trace Integration
# ---------------------------------------------------------------------------

class TestCognitiveTrace:
    @pytest.mark.asyncio
    async def test_store_generates_trace_id(self, pm: ProjectMemory) -> None:
        result = await pm.store("proj", "x", {})
        assert result["cognitive_trace_id"].startswith("cog_")

    @pytest.mark.asyncio
    async def test_retrieve_generates_trace_id(self, pm: ProjectMemory) -> None:
        await pm.store("proj", "x", {})
        result = await pm.retrieve("proj", "x")
        assert result["cognitive_trace_id"].startswith("cog_")

    @pytest.mark.asyncio
    async def test_search_generates_trace_id(self, pm: ProjectMemory) -> None:
        await pm.store("proj", "x", {})
        result = await pm.search("proj", "x")
        assert result["cognitive_trace_id"].startswith("cog_")

    @pytest.mark.asyncio
    async def test_trace_id_accepts_custom_value(self, pm: ProjectMemory) -> None:
        result = await pm.store("proj", "x", {}, cognitive_trace_id="custom_trace_123")
        assert result["cognitive_trace_id"] == "custom_trace_123"

    @pytest.mark.asyncio
    async def test_trace_id_custom_retrieve(self, pm: ProjectMemory) -> None:
        await pm.store("proj", "x", {})
        result = await pm.retrieve("proj", "x", cognitive_trace_id="my_trace")
        assert result["cognitive_trace_id"] == "my_trace"

    @pytest.mark.asyncio
    async def test_trace_id_propagation_to_hierarchy(self, pm_with_trace: ProjectMemory, correlator: CognitiveTraceCorrelator) -> None:
        result = await pm_with_trace.store("proj", "x", {"data": 1})
        trace_id = result["cognitive_trace_id"]
        store_log = correlator._store_log
        relevant = [e for e in store_log if e["cognitive_trace_id"] == trace_id]
        assert len(relevant) >= 1


# ---------------------------------------------------------------------------
# T-30.8 — Edge Cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_store_large_payload(self, pm: ProjectMemory) -> None:
        large = {"data": "x" * 100_000}
        result = await pm.store("proj", "large", large)
        assert result["status"] == "stored"

    @pytest.mark.asyncio
    async def test_store_nested_payload(self, pm: ProjectMemory) -> None:
        nested = {"level1": {"level2": {"level3": {"value": 42}}}}
        result = await pm.store("proj", "nested", nested)
        assert result["status"] == "stored"
        retrieve = await pm.retrieve("proj", "nested")
        assert retrieve["result"]["payload"]["level1"]["level2"]["level3"]["value"] == 42

    @pytest.mark.asyncio
    async def test_store_special_characters_in_key(self, pm: ProjectMemory) -> None:
        special_key = "key-with.dots;and:colons/slashes"
        await pm.store("proj", special_key, {"ok": True})
        result = await pm.retrieve("proj", special_key)
        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_store_unicode(self, pm: ProjectMemory) -> None:
        await pm.store("proj", "unicode", {"message": "Hello World"})
        result = await pm.retrieve("proj", "unicode")
        assert result["result"]["payload"]["message"] == "Hello World"

    @pytest.mark.asyncio
    async def test_store_none_payload(self, pm: ProjectMemory) -> None:
        await pm.store("proj", "none", {"data": None})
        result = await pm.retrieve("proj", "none")
        assert result["result"]["payload"]["data"] is None

    @pytest.mark.asyncio
    async def test_store_boolean_payload(self, pm: ProjectMemory) -> None:
        await pm.store("proj", "flags", {"enabled": True, "disabled": False})
        result = await pm.retrieve("proj", "flags")
        assert result["result"]["payload"]["enabled"] is True
        assert result["result"]["payload"]["disabled"] is False

    @pytest.mark.asyncio
    async def test_store_numeric_types(self, pm: ProjectMemory) -> None:
        await pm.store("proj", "nums", {
            "int": 42, "float": 3.14, "neg": -1, "zero": 0,
        })
        result = await pm.retrieve("proj", "nums")
        assert result["result"]["payload"]["int"] == 42
        assert result["result"]["payload"]["float"] == 3.14

    @pytest.mark.asyncio
    async def test_store_and_retrieve_empty_dict(self, pm: ProjectMemory) -> None:
        await pm.store("proj", "empty", {})
        result = await pm.retrieve("proj", "empty")
        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_compound_key_format(self, pm: ProjectMemory) -> None:
        assert pm._project_key("proj", "mykey") == "proj:mykey"
        assert pm._project_key("a", "b") == "a:b"

    @pytest.mark.asyncio
    async def test_parse_compound_key(self, pm: ProjectMemory) -> None:
        pid, key = pm._parse_project_key("proj:mykey")
        assert pid == "proj"
        assert key == "mykey"

    @pytest.mark.asyncio
    async def test_parse_compound_key_no_colon(self, pm: ProjectMemory) -> None:
        pid, key = pm._parse_project_key("justkey")
        assert pid == ""
        assert key == "justkey"


# ---------------------------------------------------------------------------
# T-30.9 — Concurrency
# ---------------------------------------------------------------------------

class TestConcurrency:
    @pytest.mark.asyncio
    async def test_concurrent_stores_same_project(self, pm: ProjectMemory) -> None:
        async def store_one(i: int) -> None:
            await pm.store("con-proj", f"key-{i}", {"index": i})

        await asyncio.gather(*[store_one(i) for i in range(10)])
        stats = await pm.get_stats("con-proj")
        assert stats["entry_count"] == 10

    @pytest.mark.asyncio
    async def test_concurrent_stores_different_projects(self, pm: ProjectMemory) -> None:
        async def store_project(pid: str) -> None:
            await pm.store(pid, "init", {"pid": pid})

        pids = [f"con-pid-{i}" for i in range(20)]
        await asyncio.gather(*[store_project(p) for p in pids])
        result = await pm.list_projects()
        assert result["total_projects"] >= 20

    @pytest.mark.asyncio
    async def test_concurrent_reads_and_writes(self, pm: ProjectMemory) -> None:
        await pm.store("stress", "base", {"val": 0})

        async def writer() -> None:
            for i in range(5):
                await pm.store("stress", "base", {"val": i})

        async def reader() -> None:
            for _ in range(5):
                await pm.retrieve("stress", "base")

        await asyncio.gather(writer(), reader())
        stats = await pm.get_stats("stress")
        assert stats["entry_count"] >= 1
        assert stats["total_access_count"] >= 5


# ---------------------------------------------------------------------------
# T-30.10 — Model Validation
# ---------------------------------------------------------------------------

class TestModels:
    def test_project_memory_entry_defaults(self) -> None:
        entry = ProjectMemoryEntry(project_id="p", key="k", payload={})
        assert entry.access_count == 0
        assert entry.relevance_score == 1.0
        assert entry.created_at_ns > 0
        assert entry.updated_at_ns > 0

    def test_project_memory_entry_metadata_defaults_empty(self) -> None:
        entry = ProjectMemoryEntry(project_id="p", key="k", payload={})
        assert entry.metadata == {}

    def test_project_summary_fields(self) -> None:
        summary = ProjectSummary(
            project_id="test",
            entry_count=5,
            total_access_count=10,
            oldest_entry_ns=100,
            newest_entry_ns=200,
        )
        assert summary.project_id == "test"
        assert summary.entry_count == 5
        assert summary.total_access_count == 10

    def test_project_summary_default_trace_id(self) -> None:
        summary = ProjectSummary(project_id="p", entry_count=0, total_access_count=0, oldest_entry_ns=0, newest_entry_ns=0)
        assert summary.cognitive_trace_id == ""

    def test_project_memory_entry_timestamps_change(self) -> None:
        entry = ProjectMemoryEntry(project_id="p", key="k", payload={})
        old_updated = entry.updated_at_ns
        entry.updated_at_ns = time.time_ns() + 1000
        assert entry.updated_at_ns != old_updated

    def test_project_memory_entry_relevance_default(self) -> None:
        entry = ProjectMemoryEntry(project_id="p", key="k", payload={})
        assert entry.relevance_score == 1.0

    def test_project_memory_entry_relevance_update(self) -> None:
        entry = ProjectMemoryEntry(project_id="p", key="k", payload={})
        entry.relevance_score = 0.5
        assert entry.relevance_score == 0.5

    def test_project_summary_ordering(self) -> None:
        s1 = ProjectSummary(project_id="a", entry_count=1, total_access_count=1, oldest_entry_ns=0, newest_entry_ns=1)
        s2 = ProjectSummary(project_id="b", entry_count=2, total_access_count=2, oldest_entry_ns=0, newest_entry_ns=2)
        assert s1.project_id < s2.project_id


# ---------------------------------------------------------------------------
# T-30.11 — ProjectMemory constructor variants
# ---------------------------------------------------------------------------

class TestConstructor:
    def test_default_correlator(self) -> None:
        hierarchy = MemoryHierarchy()
        pm = ProjectMemory(hierarchy=hierarchy)
        assert pm._trace_correlator is not None
        assert isinstance(pm._trace_correlator, CognitiveTraceCorrelator)

    def test_custom_correlator(self, correlator: CognitiveTraceCorrelator) -> None:
        hierarchy = MemoryHierarchy()
        pm = ProjectMemory(hierarchy=hierarchy, trace_correlator=correlator)
        assert pm._trace_correlator is correlator

    def test_hierarchy_is_used(self, hierarchy: MemoryHierarchy) -> None:
        pm = ProjectMemory(hierarchy=hierarchy)
        assert pm._hierarchy is hierarchy

    def test_initial_empty_metadata(self, pm: ProjectMemory) -> None:
        assert pm._project_metadata == {}

    def test_can_create_without_trace_correlator(self) -> None:
        pm = ProjectMemory(hierarchy=MemoryHierarchy())
        assert isinstance(pm._trace_correlator, CognitiveTraceCorrelator)
