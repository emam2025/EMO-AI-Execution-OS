"""T-31 Agent Memory — 75+ tests.

Tests cover:
- CRUD operations (store, retrieve, delete)
- Agent isolation (different agents don't leak)
- Skill integration (search_by_skill, get_skill_summary)
- TTL expiration
- Search and filtering
- Edge cases
- Integration with MemoryHierarchy + CognitiveTraceCorrelator
- Concurrent access patterns
- Metadata and stats
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict

import pytest

from core.memory.agent_memory import AgentMemory, AgentMemoryEntry, AgentSkillSummary, AgentSummary
from core.memory.memory_hierarchy import MemoryHierarchy
from core.memory.models import MemoryLayer
from core.memory.skill_graph_manager import SkillGraphManager
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
def skill_graph() -> SkillGraphManager:
    return SkillGraphManager()


@pytest.fixture
def am(hierarchy: MemoryHierarchy, correlator: CognitiveTraceCorrelator) -> AgentMemory:
    return AgentMemory(hierarchy=hierarchy, trace_correlator=correlator)


@pytest.fixture
def am_with_skills(
    hierarchy: MemoryHierarchy,
    skill_graph: SkillGraphManager,
    correlator: CognitiveTraceCorrelator,
) -> AgentMemory:
    return AgentMemory(
        hierarchy=hierarchy,
        skill_graph=skill_graph,
        trace_correlator=correlator,
    )


# ---------------------------------------------------------------------------
# T-31.1 — CRUD
# ---------------------------------------------------------------------------

class TestStoreAndRetrieve:
    @pytest.mark.asyncio
    async def test_store_basic(self, am: AgentMemory) -> None:
        result = await am.store("agent-alpha", "config", {"key": "value"})
        assert result["status"] == "stored"
        assert result["agent_id"] == "agent-alpha"
        assert result["key"] == "config"
        assert "cognitive_trace_id" in result

    @pytest.mark.asyncio
    async def test_retrieve_stored_value(self, am: AgentMemory) -> None:
        await am.store("agent-alpha", "greeting", {"text": "hello"})
        result = await am.retrieve("agent-alpha", "greeting")
        assert result["status"] == "ok"
        assert result["result"]["payload"]["text"] == "hello"

    @pytest.mark.asyncio
    async def test_retrieve_missing_key_returns_not_found(self, am: AgentMemory) -> None:
        result = await am.retrieve("agent-alpha", "nonexistent")
        assert result["status"] == "not_found"
        assert result["result"] is None

    @pytest.mark.asyncio
    async def test_retrieve_missing_agent_returns_not_found(self, am: AgentMemory) -> None:
        result = await am.retrieve("never-created", "anything")
        assert result["status"] == "not_found"

    @pytest.mark.asyncio
    async def test_store_overwrites_existing_key(self, am: AgentMemory) -> None:
        await am.store("agent", "x", {"v": 1})
        await am.store("agent", "x", {"v": 2})
        result = await am.retrieve("agent", "x")
        assert result["result"]["payload"]["v"] == 2

    @pytest.mark.asyncio
    async def test_store_empty_agent_id_raises(self, am: AgentMemory) -> None:
        with pytest.raises(ValueError, match="agent_id is required"):
            await am.store("", "key", {})

    @pytest.mark.asyncio
    async def test_store_empty_key_raises(self, am: AgentMemory) -> None:
        with pytest.raises(ValueError, match="key is required"):
            await am.store("agent", "", {})

    @pytest.mark.asyncio
    async def test_retrieve_empty_agent_id_raises(self, am: AgentMemory) -> None:
        with pytest.raises(ValueError, match="agent_id and key are required"):
            await am.retrieve("", "key")

    @pytest.mark.asyncio
    async def test_retrieve_empty_key_raises(self, am: AgentMemory) -> None:
        with pytest.raises(ValueError, match="agent_id and key are required"):
            await am.retrieve("agent", "")


class TestDeleteKey:
    @pytest.mark.asyncio
    async def test_delete_existing_key(self, am: AgentMemory) -> None:
        await am.store("agent", "temp", {"data": "to-delete"})
        result = await am.delete_key("agent", "temp")
        assert result["status"] == "deleted"
        assert "temp" not in am._agent_metadata.get("agent", {})

    @pytest.mark.asyncio
    async def test_delete_nonexistent_key_is_idempotent(self, am: AgentMemory) -> None:
        result = await am.delete_key("agent", "never-existed")
        assert result["status"] == "deleted"

    @pytest.mark.asyncio
    async def test_delete_key_empty_agent_id_raises(self, am: AgentMemory) -> None:
        with pytest.raises(ValueError, match="agent_id and key are required"):
            await am.delete_key("", "key")

    @pytest.mark.asyncio
    async def test_delete_key_empty_key_raises(self, am: AgentMemory) -> None:
        with pytest.raises(ValueError, match="agent_id and key are required"):
            await am.delete_key("agent", "")


class TestDeleteAgent:
    @pytest.mark.asyncio
    async def test_delete_agent_removes_all_entries(self, am: AgentMemory) -> None:
        await am.store("agent", "a", {"v": 1})
        await am.store("agent", "b", {"v": 2})
        result = await am.delete_agent("agent")
        assert result["status"] == "deleted"
        stats = await am.get_stats("agent")
        assert stats["status"] == "not_found"

    @pytest.mark.asyncio
    async def test_delete_nonexistent_agent_is_idempotent(self, am: AgentMemory) -> None:
        result = await am.delete_agent("nonexistent")
        assert result["status"] == "deleted"

    @pytest.mark.asyncio
    async def test_delete_agent_also_removes_skills(self, am: AgentMemory) -> None:
        await am.store("agent", "sk", {"v": 1}, skill_id="skill-1")
        await am.delete_agent("agent")
        assert "agent" not in am._agent_skills

    @pytest.mark.asyncio
    async def test_delete_agent_empty_id_raises(self, am: AgentMemory) -> None:
        with pytest.raises(ValueError, match="agent_id is required"):
            await am.delete_agent("")


# ---------------------------------------------------------------------------
# T-31.2 — Agent Isolation
# ---------------------------------------------------------------------------

class TestAgentIsolation:
    @pytest.mark.asyncio
    async def test_different_agents_do_not_interfere(self, am: AgentMemory) -> None:
        await am.store("agent-a", "key1", {"owner": "A"})
        await am.store("agent-b", "key1", {"owner": "B"})
        result_a = await am.retrieve("agent-a", "key1")
        result_b = await am.retrieve("agent-b", "key1")
        assert result_a["result"]["payload"]["owner"] == "A"
        assert result_b["result"]["payload"]["owner"] == "B"

    @pytest.mark.asyncio
    async def test_isolation_via_tenant_id(self, am: AgentMemory) -> None:
        await am.store("agent", "shared", {"val": 1}, tenant_id="tenant_a")
        result = await am.retrieve("agent", "shared", tenant_id="tenant_b")
        assert result["status"] == "not_found"

    @pytest.mark.asyncio
    async def test_large_number_of_agents_isolated(self, am: AgentMemory) -> None:
        for i in range(20):
            await am.store(f"agent-{i:03d}", "config", {"id": i})
        for i in range(20):
            r = await am.retrieve(f"agent-{i:03d}", "config")
            assert r["result"]["payload"]["id"] == i

    @pytest.mark.asyncio
    async def test_same_key_different_payload_per_agent(self, am: AgentMemory) -> None:
        agents = ["alpha", "beta", "gamma"]
        for a in agents:
            await am.store(a, "status", {"agent": a, "active": True})
        for a in agents:
            r = await am.retrieve(a, "status")
            assert r["result"]["payload"]["agent"] == a


# ---------------------------------------------------------------------------
# T-31.3 — TTL
# ---------------------------------------------------------------------------

class TestTTL:
    @pytest.mark.asyncio
    async def test_store_with_ttl(self, am: AgentMemory) -> None:
        result = await am.store("agent", "ttl-key", {"data": "expires"}, ttl_seconds=3600)
        assert result["ttl_seconds"] == 3600

    @pytest.mark.asyncio
    async def test_store_without_ttl_is_none(self, am: AgentMemory) -> None:
        result = await am.store("agent", "no-ttl", {"data": "permanent"})
        assert result["ttl_seconds"] is None

    @pytest.mark.asyncio
    async def test_ttl_negative_value_is_stored(self, am: AgentMemory) -> None:
        result = await am.store("agent", "neg-ttl", {}, ttl_seconds=-1)
        assert result["ttl_seconds"] == -1

    @pytest.mark.asyncio
    async def test_multiple_ttl_values_per_agent(self, am: AgentMemory) -> None:
        ttls = {"short": 60, "medium": 3600, "long": 86400, "none": None}
        for key, ttl in ttls.items():
            r = await am.store("agent-ttl", key, {}, ttl_seconds=ttl)
            assert r["ttl_seconds"] == ttl


# ---------------------------------------------------------------------------
# T-31.4 — Search
# ---------------------------------------------------------------------------

class TestSearch:
    @pytest.mark.asyncio
    async def test_search_by_key(self, am: AgentMemory) -> None:
        await am.store("agent", "configuration", {"env": "prod"})
        await am.store("agent", "secrets", {"key": "abc"})
        result = await am.search("agent", "configuration")
        assert result["total"] >= 1
        assert any("configuration" in r["key"] for r in result["results"])

    @pytest.mark.asyncio
    async def test_search_by_payload_content(self, am: AgentMemory) -> None:
        await am.store("agent", "cfg", {"environment": "staging"})
        await am.store("agent", "other", {"environment": "production"})
        result = await am.search("agent", "staging")
        assert result["total"] >= 1

    @pytest.mark.asyncio
    async def test_search_empty_query_returns_all(self, am: AgentMemory) -> None:
        for i in range(5):
            await am.store("agent", f"key-{i}", {"index": i})
        result = await am.search("agent", "")
        assert result["total"] == 5

    @pytest.mark.asyncio
    async def test_search_no_matches(self, am: AgentMemory) -> None:
        await am.store("agent", "abc", {"data": "123"})
        result = await am.search("agent", "zzz_nonexistent_zzz")
        assert result["total"] == 0

    @pytest.mark.asyncio
    async def test_search_respects_limit(self, am: AgentMemory) -> None:
        for i in range(20):
            await am.store("agent", f"item-{i}", {"i": i})
        result = await am.search("agent", "", limit=5)
        assert result["total"] <= 5

    @pytest.mark.asyncio
    async def test_search_empty_agent_id_raises(self, am: AgentMemory) -> None:
        with pytest.raises(ValueError, match="agent_id is required"):
            await am.search("", "query")

    @pytest.mark.asyncio
    async def test_search_case_insensitive(self, am: AgentMemory) -> None:
        await am.store("agent", "ConfigFile", {"env": "prod"})
        result = await am.search("agent", "configfile")
        assert result["total"] >= 1


# ---------------------------------------------------------------------------
# T-31.5 — Skill Integration
# ---------------------------------------------------------------------------

class TestSearchBySkill:
    @pytest.mark.asyncio
    async def test_search_by_skill_filters_correctly(self, am: AgentMemory) -> None:
        await am.store("agent", "mem1", {"v": 1}, skill_id="skill-a")
        await am.store("agent", "mem2", {"v": 2}, skill_id="skill-b")
        result = await am.search_by_skill("agent", "skill-a")
        assert result["total"] >= 1
        assert result["skill_filter"] == "skill-a"

    @pytest.mark.asyncio
    async def test_search_by_skill_no_matches(self, am: AgentMemory) -> None:
        await am.store("agent", "mem1", {"v": 1}, skill_id="skill-a")
        result = await am.search_by_skill("agent", "skill-nonexistent")
        assert result["total"] == 0

    @pytest.mark.asyncio
    async def test_search_by_skill_with_text_filter(self, am: AgentMemory) -> None:
        await am.store("agent", "alpha", {"tag": "skill-a-data"}, skill_id="skill-a")
        await am.store("agent", "beta", {"tag": "skill-b-data"}, skill_id="skill-b")
        result = await am.search("agent", "alpha", skill_id="skill-a")
        assert result["total"] >= 1

    @pytest.mark.asyncio
    async def test_search_skill_filter_rejects_wrong_skill(self, am: AgentMemory) -> None:
        await am.store("agent", "mem", {"v": 1}, skill_id="skill-a")
        result = await am.search("agent", "", skill_id="skill-b")
        assert result["total"] == 0

    @pytest.mark.asyncio
    async def test_search_by_skill_empty_skill_returns_all(self, am: AgentMemory) -> None:
        await am.store("agent", "mem1", {"v": 1}, skill_id="skill-a")
        result = await am.search_by_skill("agent", "")
        assert result["total"] >= 1


class TestSkillSummary:
    @pytest.mark.asyncio
    async def test_skill_summary_tracks_counts(self, am: AgentMemory) -> None:
        await am.store("agent", "a", {}, skill_id="skill-1")
        await am.store("agent", "b", {}, skill_id="skill-1")
        await am.store("agent", "c", {}, skill_id="skill-2")
        summary = await am.get_skill_summary("agent")
        assert summary["skills"]["skill-1"] >= 2
        assert summary["skills"]["skill-2"] >= 1

    @pytest.mark.asyncio
    async def test_skill_summary_no_skills(self, am: AgentMemory) -> None:
        await am.store("agent", "a", {})
        summary = await am.get_skill_summary("agent")
        assert summary["total_skill_refs"] == 0
        assert summary["unique_skills"] == 0

    @pytest.mark.asyncio
    async def test_skill_summary_empty_agent_id_raises(self, am: AgentMemory) -> None:
        with pytest.raises(ValueError, match="agent_id is required"):
            await am.get_skill_summary("")

    @pytest.mark.asyncio
    async def test_skill_summary_returns_ok(self, am: AgentMemory) -> None:
        result = await am.get_skill_summary("nonexistent")
        assert result["status"] == "ok"


# ---------------------------------------------------------------------------
# T-31.6 — Stats and Listing
# ---------------------------------------------------------------------------

class TestStatsAndListing:
    @pytest.mark.asyncio
    async def test_get_stats_after_stores(self, am: AgentMemory) -> None:
        await am.store("agent", "a", {})
        await am.store("agent", "b", {})
        await am.store("agent", "c", {})
        stats = await am.get_stats("agent")
        assert stats["status"] == "ok"
        assert stats["entry_count"] == 3
        assert len(stats["keys"]) == 3

    @pytest.mark.asyncio
    async def test_get_stats_nonexistent_agent(self, am: AgentMemory) -> None:
        stats = await am.get_stats("ghost")
        assert stats["status"] == "not_found"

    @pytest.mark.asyncio
    async def test_get_stats_empty_agent_id_raises(self, am: AgentMemory) -> None:
        with pytest.raises(ValueError, match="agent_id is required"):
            await am.get_stats("")

    @pytest.mark.asyncio
    async def test_get_stats_tracks_access_count(self, am: AgentMemory) -> None:
        await am.store("agent", "popular", {"data": "hot"})
        for _ in range(5):
            await am.retrieve("agent", "popular")
        stats = await am.get_stats("agent")
        assert stats["total_access_count"] >= 5

    @pytest.mark.asyncio
    async def test_get_stats_includes_skills(self, am: AgentMemory) -> None:
        await am.store("agent", "sk", {"v": 1}, skill_id="skill-x")
        stats = await am.get_stats("agent")
        assert "skills" in stats
        assert "skill-x" in stats["skills"]

    @pytest.mark.asyncio
    async def test_list_agents_empty(self, am: AgentMemory) -> None:
        result = await am.list_agents()
        assert result["total_agents"] == 0

    @pytest.mark.asyncio
    async def test_list_agents_after_multiple_stores(self, am: AgentMemory) -> None:
        for aid in ["alpha", "beta", "gamma"]:
            await am.store(aid, "init", {})
        result = await am.list_agents()
        assert result["total_agents"] >= 3
        aids = [a["agent_id"] for a in result["agents"]]
        assert "alpha" in aids
        assert "beta" in aids
        assert "gamma" in aids

    @pytest.mark.asyncio
    async def test_list_agents_after_delete(self, am: AgentMemory) -> None:
        await am.store("temp-agent", "x", {})
        await am.delete_agent("temp-agent")
        result = await am.list_agents()
        assert "temp-agent" not in [a["agent_id"] for a in result["agents"]]


# ---------------------------------------------------------------------------
# T-31.7 — Cognitive Trace Integration
# ---------------------------------------------------------------------------

class TestCognitiveTrace:
    @pytest.mark.asyncio
    async def test_store_generates_trace_id(self, am: AgentMemory) -> None:
        result = await am.store("agent", "x", {})
        assert result["cognitive_trace_id"].startswith("cog_")

    @pytest.mark.asyncio
    async def test_retrieve_generates_trace_id(self, am: AgentMemory) -> None:
        await am.store("agent", "x", {})
        result = await am.retrieve("agent", "x")
        assert result["cognitive_trace_id"].startswith("cog_")

    @pytest.mark.asyncio
    async def test_search_generates_trace_id(self, am: AgentMemory) -> None:
        await am.store("agent", "x", {})
        result = await am.search("agent", "x")
        assert result["cognitive_trace_id"].startswith("cog_")

    @pytest.mark.asyncio
    async def test_trace_id_accepts_custom_value(self, am: AgentMemory) -> None:
        result = await am.store("agent", "x", {}, cognitive_trace_id="custom_trace_123")
        assert result["cognitive_trace_id"] == "custom_trace_123"

    @pytest.mark.asyncio
    async def test_trace_id_custom_retrieve(self, am: AgentMemory) -> None:
        await am.store("agent", "x", {})
        result = await am.retrieve("agent", "x", cognitive_trace_id="my_trace")
        assert result["cognitive_trace_id"] == "my_trace"


# ---------------------------------------------------------------------------
# T-31.8 — Edge Cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_store_large_payload(self, am: AgentMemory) -> None:
        large = {"data": "x" * 100_000}
        result = await am.store("agent", "large", large)
        assert result["status"] == "stored"

    @pytest.mark.asyncio
    async def test_store_nested_payload(self, am: AgentMemory) -> None:
        nested = {"level1": {"level2": {"level3": {"value": 42}}}}
        result = await am.store("agent", "nested", nested)
        assert result["status"] == "stored"
        retrieve = await am.retrieve("agent", "nested")
        assert retrieve["result"]["payload"]["level1"]["level2"]["level3"]["value"] == 42

    @pytest.mark.asyncio
    async def test_store_special_characters_in_key(self, am: AgentMemory) -> None:
        special_key = "key-with.dots;and:colons/slashes"
        await am.store("agent", special_key, {"ok": True})
        result = await am.retrieve("agent", special_key)
        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_store_none_payload(self, am: AgentMemory) -> None:
        await am.store("agent", "none", {"data": None})
        result = await am.retrieve("agent", "none")
        assert result["result"]["payload"]["data"] is None

    @pytest.mark.asyncio
    async def test_store_boolean_payload(self, am: AgentMemory) -> None:
        await am.store("agent", "flags", {"enabled": True, "disabled": False})
        result = await am.retrieve("agent", "flags")
        assert result["result"]["payload"]["enabled"] is True
        assert result["result"]["payload"]["disabled"] is False

    @pytest.mark.asyncio
    async def test_store_numeric_types(self, am: AgentMemory) -> None:
        await am.store("agent", "nums", {"int": 42, "float": 3.14, "neg": -1, "zero": 0})
        result = await am.retrieve("agent", "nums")
        assert result["result"]["payload"]["int"] == 42
        assert result["result"]["payload"]["float"] == 3.14

    @pytest.mark.asyncio
    async def test_store_and_retrieve_empty_dict(self, am: AgentMemory) -> None:
        await am.store("agent", "empty", {})
        result = await am.retrieve("agent", "empty")
        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_store_with_skill_id(self, am: AgentMemory) -> None:
        result = await am.store("agent", "skilled", {"v": 1}, skill_id="skill-42")
        assert result["status"] == "stored"
        assert result["skill_id"] == "skill-42"

    @pytest.mark.asyncio
    async def test_store_without_skill_id_defaults_empty(self, am: AgentMemory) -> None:
        result = await am.store("agent", "noskill", {"v": 1})
        assert result["skill_id"] == ""

    @pytest.mark.asyncio
    async def test_compound_key_format(self, am: AgentMemory) -> None:
        assert am._agent_key("agent", "mykey") == "agent:mykey"
        assert am._agent_key("a", "b") == "a:b"


# ---------------------------------------------------------------------------
# T-31.9 — Concurrency
# ---------------------------------------------------------------------------

class TestConcurrency:
    @pytest.mark.asyncio
    async def test_concurrent_stores_same_agent(self, am: AgentMemory) -> None:
        async def store_one(i: int) -> None:
            await am.store("con-agent", f"key-{i}", {"index": i})
        await asyncio.gather(*[store_one(i) for i in range(10)])
        stats = await am.get_stats("con-agent")
        assert stats["entry_count"] == 10

    @pytest.mark.asyncio
    async def test_concurrent_stores_different_agents(self, am: AgentMemory) -> None:
        async def store_agent(aid: str) -> None:
            await am.store(aid, "init", {"aid": aid})
        aids = [f"con-aid-{i}" for i in range(20)]
        await asyncio.gather(*[store_agent(a) for a in aids])
        result = await am.list_agents()
        assert result["total_agents"] >= 20

    @pytest.mark.asyncio
    async def test_concurrent_reads_and_writes(self, am: AgentMemory) -> None:
        await am.store("stress", "base", {"val": 0})
        async def writer() -> None:
            for i in range(5):
                await am.store("stress", "base", {"val": i})
        async def reader() -> None:
            for _ in range(5):
                await am.retrieve("stress", "base")
        await asyncio.gather(writer(), reader())
        stats = await am.get_stats("stress")
        assert stats["entry_count"] >= 1
        assert stats["total_access_count"] >= 5


# ---------------------------------------------------------------------------
# T-31.10 — Model Validation
# ---------------------------------------------------------------------------

class TestModels:
    def test_agent_memory_entry_defaults(self) -> None:
        entry = AgentMemoryEntry(agent_id="a", key="k", payload={})
        assert entry.access_count == 0
        assert entry.relevance_score == 1.0
        assert entry.created_at_ns > 0
        assert entry.updated_at_ns > 0
        assert entry.skill_id == ""

    def test_agent_memory_entry_metadata_defaults_empty(self) -> None:
        entry = AgentMemoryEntry(agent_id="a", key="k", payload={})
        assert entry.metadata == {}

    def test_agent_skill_summary_fields(self) -> None:
        summary = AgentSkillSummary(
            agent_id="test", skills={"s1": 3, "s2": 1}, total_skill_refs=4,
        )
        assert summary.agent_id == "test"
        assert summary.skills["s1"] == 3
        assert summary.total_skill_refs == 4

    def test_agent_skill_summary_default_trace_id(self) -> None:
        summary = AgentSkillSummary(agent_id="a", skills={}, total_skill_refs=0)
        assert summary.cognitive_trace_id == ""

    def test_agent_summary_fields(self) -> None:
        summary = AgentSummary(
            agent_id="test", entry_count=5, total_access_count=10,
            skill_count=2, oldest_entry_ns=100, newest_entry_ns=200,
        )
        assert summary.agent_id == "test"
        assert summary.entry_count == 5
        assert summary.skill_count == 2

    def test_agent_summary_default_trace_id(self) -> None:
        summary = AgentSummary(
            agent_id="a", entry_count=0, total_access_count=0,
            skill_count=0, oldest_entry_ns=0, newest_entry_ns=0,
        )
        assert summary.cognitive_trace_id == ""

    def test_agent_memory_entry_relevance_default(self) -> None:
        entry = AgentMemoryEntry(agent_id="a", key="k", payload={})
        assert entry.relevance_score == 1.0

    def test_agent_memory_entry_relevance_update(self) -> None:
        entry = AgentMemoryEntry(agent_id="a", key="k", payload={})
        entry.relevance_score = 0.5
        assert entry.relevance_score == 0.5


# ---------------------------------------------------------------------------
# T-31.11 — Constructor variants
# ---------------------------------------------------------------------------

class TestConstructor:
    def test_default_correlator(self) -> None:
        hierarchy = MemoryHierarchy()
        am = AgentMemory(hierarchy=hierarchy)
        assert am._trace_correlator is not None
        assert isinstance(am._trace_correlator, CognitiveTraceCorrelator)

    def test_custom_correlator(self, correlator: CognitiveTraceCorrelator) -> None:
        hierarchy = MemoryHierarchy()
        am = AgentMemory(hierarchy=hierarchy, trace_correlator=correlator)
        assert am._trace_correlator is correlator

    def test_skill_graph_default_none(self) -> None:
        hierarchy = MemoryHierarchy()
        am = AgentMemory(hierarchy=hierarchy)
        assert am._skill_graph is None

    def test_skill_graph_custom(self, skill_graph: SkillGraphManager) -> None:
        hierarchy = MemoryHierarchy()
        am = AgentMemory(hierarchy=hierarchy, skill_graph=skill_graph)
        assert am._skill_graph is skill_graph

    def test_hierarchy_is_used(self, hierarchy: MemoryHierarchy) -> None:
        am = AgentMemory(hierarchy=hierarchy)
        assert am._hierarchy is hierarchy

    def test_initial_empty_metadata(self, am: AgentMemory) -> None:
        assert am._agent_metadata == {}

    def test_initial_empty_skills(self, am: AgentMemory) -> None:
        assert am._agent_skills == {}
