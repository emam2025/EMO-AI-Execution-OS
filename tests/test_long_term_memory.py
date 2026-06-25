"""T-32 Long-Term Memory — 75+ tests.

Tests cover:
- CRUD operations (store, retrieve, delete)
- PERSISTENCE (store -> close -> reopen -> retrieve) — KEY T-32 FEATURE
- Agent isolation
- TTL and cleanup
- Search with text and tags
- Semantic search via VectorDB
- Stats and listing
- Cognitive trace propagation
- Edge cases
- Concurrency
- Models
- Constructor variants
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
from typing import Any, Dict, List, Optional

import pytest

from core.memory.memory_hierarchy import MemoryHierarchy
from core.memory.models import MemoryLayer
from core.memory.long_term_memory import LongTermMemory, LongTermMemoryEntry
from core.memory.trace_correlator import CognitiveTraceCorrelator


@pytest.fixture
def hierarchy() -> MemoryHierarchy:
    return MemoryHierarchy()


@pytest.fixture
def correlator() -> CognitiveTraceCorrelator:
    return CognitiveTraceCorrelator()


@pytest.fixture
def ltm(hierarchy: MemoryHierarchy, correlator: CognitiveTraceCorrelator) -> LongTermMemory:
    mem = LongTermMemory(hierarchy=hierarchy, trace_correlator=correlator)
    return mem


@pytest.fixture
async def ltm_with_db(tmp_path) -> LongTermMemory:
    from core.db_backend import _SQLiteBackend
    db_path = str(tmp_path / "test_ltm.db")
    backend = _SQLiteBackend(db_path)
    hierarchy = MemoryHierarchy()
    mem = LongTermMemory(hierarchy=hierarchy, db=backend, trace_correlator=CognitiveTraceCorrelator())
    await mem.initialize()
    return mem


@pytest.fixture
def sample_payload() -> Dict[str, Any]:
    return {"name": "test_agent", "status": "active", "version": 1}


class TestStoreAndRetrieve:
    @pytest.mark.asyncio
    async def test_store_basic(self, ltm: LongTermMemory) -> None:
        result = await ltm.store("agent-alpha", "config", {"key": "value"})
        assert result["status"] == "stored"
        assert result["agent_id"] == "agent-alpha"
        assert result["key"] == "config"
        assert "entry_id" in result
        assert "cognitive_trace_id" in result

    @pytest.mark.asyncio
    async def test_retrieve_stored_value(self, ltm: LongTermMemory) -> None:
        await ltm.store("agent-alpha", "greeting", {"text": "hello"})
        result = await ltm.retrieve("agent-alpha", "greeting")
        assert result["status"] == "ok"
        assert result["result"]["payload"]["text"] == "hello"

    @pytest.mark.asyncio
    async def test_retrieve_missing_key_returns_not_found(self, ltm: LongTermMemory) -> None:
        result = await ltm.retrieve("agent-alpha", "nonexistent")
        assert result["status"] == "not_found"
        assert result["result"] is None

    @pytest.mark.asyncio
    async def test_retrieve_missing_agent_returns_not_found(self, ltm: LongTermMemory) -> None:
        result = await ltm.retrieve("never-created", "anything")
        assert result["status"] == "not_found"

    @pytest.mark.asyncio
    async def test_store_overwrites_existing_key(self, ltm: LongTermMemory) -> None:
        await ltm.store("agent", "x", {"v": 1})
        await ltm.store("agent", "x", {"v": 2})
        result = await ltm.retrieve("agent", "x")
        assert result["result"]["payload"]["v"] == 2

    @pytest.mark.asyncio
    async def test_store_empty_agent_id_raises(self, ltm: LongTermMemory) -> None:
        with pytest.raises(ValueError, match="agent_id is required"):
            await ltm.store("", "k", {})

    @pytest.mark.asyncio
    async def test_store_empty_key_raises(self, ltm: LongTermMemory) -> None:
        with pytest.raises(ValueError, match="key is required"):
            await ltm.store("agent", "", {})

    @pytest.mark.asyncio
    async def test_retrieve_empty_agent_id_raises(self, ltm: LongTermMemory) -> None:
        with pytest.raises(ValueError, match="agent_id and key are required"):
            await ltm.retrieve("", "k")

    @pytest.mark.asyncio
    async def test_retrieve_empty_key_raises(self, ltm: LongTermMemory) -> None:
        with pytest.raises(ValueError, match="agent_id and key are required"):
            await ltm.retrieve("agent", "")

    @pytest.mark.asyncio
    async def test_store_with_tags(self, ltm: LongTermMemory) -> None:
        result = await ltm.store("agent", "tagged", {"v": 1}, tags=["important", "critical"])
        assert result["tags"] == ["important", "critical"]


class TestPersistence:
    @pytest.mark.asyncio
    async def test_store_then_reload(self, tmp_path) -> None:
        from core.db_backend import _SQLiteBackend
        db_path = str(tmp_path / "test_persist.db")
        backend = _SQLiteBackend(db_path)

        hierarchy1 = MemoryHierarchy()
        mem1 = LongTermMemory(hierarchy=hierarchy1, db=backend, trace_correlator=CognitiveTraceCorrelator())
        await mem1.initialize()
        await mem1.store("agent_1", "important_fact", {"fact": "The sky is blue"})
        await mem1.store("agent_1", "number", {"value": 42})
        del mem1

        hierarchy2 = MemoryHierarchy()
        backend2 = _SQLiteBackend(db_path)
        mem2 = LongTermMemory(hierarchy=hierarchy2, db=backend2, trace_correlator=CognitiveTraceCorrelator())
        await mem2.initialize()

        result = await mem2.retrieve("agent_1", "important_fact")
        assert result["status"] == "ok"
        assert result["result"]["payload"]["fact"] == "The sky is blue"

        result2 = await mem2.retrieve("agent_1", "number")
        assert result2["status"] == "ok"
        assert result2["result"]["payload"]["value"] == 42

    @pytest.mark.asyncio
    async def test_store_then_reload_with_tags(self, tmp_path) -> None:
        from core.db_backend import _SQLiteBackend
        db_path = str(tmp_path / "test_tags.db")
        backend = _SQLiteBackend(db_path)

        hierarchy1 = MemoryHierarchy()
        mem1 = LongTermMemory(hierarchy=hierarchy1, db=backend, trace_correlator=CognitiveTraceCorrelator())
        await mem1.initialize()
        await mem1.store("agent", "tagged", {"v": 1}, tags=["a", "b"])
        del mem1

        backend2 = _SQLiteBackend(db_path)
        mem2 = LongTermMemory(hierarchy=MemoryHierarchy(), db=backend2, trace_correlator=CognitiveTraceCorrelator())
        await mem2.initialize()
        result = await mem2.retrieve("agent", "tagged")
        assert result["result"]["tags"] == ["a", "b"]

    @pytest.mark.asyncio
    async def test_persistence_across_connections(self, tmp_path) -> None:
        from core.db_backend import _SQLiteBackend
        db_path = str(tmp_path / "test_shared.db")
        backend1 = _SQLiteBackend(db_path)
        mem1 = LongTermMemory(hierarchy=MemoryHierarchy(), db=backend1, trace_correlator=CognitiveTraceCorrelator())
        await mem1.initialize()
        await mem1.store("agent_a", "shared", {"value": "from_a"})
        await mem1.store("agent_b", "shared", {"value": "from_b"})

        backend2 = _SQLiteBackend(db_path)
        mem2 = LongTermMemory(hierarchy=MemoryHierarchy(), db=backend2, trace_correlator=CognitiveTraceCorrelator())
        await mem2.initialize()

        ra = await mem2.retrieve("agent_a", "shared")
        rb = await mem2.retrieve("agent_b", "shared")
        assert ra["status"] == "ok"
        assert rb["status"] == "ok"
        assert ra["result"]["payload"]["value"] == "from_a"
        assert rb["result"]["payload"]["value"] == "from_b"

    @pytest.mark.asyncio
    async def test_no_db_stores_in_hierarchy(self, tmp_path) -> None:
        mem = LongTermMemory(hierarchy=MemoryHierarchy())
        await mem.store("agent", "k", {"v": 1})
        result = await mem.retrieve("agent", "k")
        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_persistence_after_delete_then_reload(self, tmp_path) -> None:
        from core.db_backend import _SQLiteBackend
        db_path = str(tmp_path / "test_del.db")
        backend = _SQLiteBackend(db_path)

        mem1 = LongTermMemory(hierarchy=MemoryHierarchy(), db=backend, trace_correlator=CognitiveTraceCorrelator())
        await mem1.initialize()
        await mem1.store("agent", "keep", {"v": 1})
        await mem1.store("agent", "remove", {"v": 2})
        await mem1.delete("agent", "remove")
        del mem1

        backend2 = _SQLiteBackend(db_path)
        mem2 = LongTermMemory(hierarchy=MemoryHierarchy(), db=backend2, trace_correlator=CognitiveTraceCorrelator())
        await mem2.initialize()

        r1 = await mem2.retrieve("agent", "keep")
        assert r1["status"] == "ok"
        r2 = await mem2.retrieve("agent", "remove")
        assert r2["status"] == "not_found"


class TestDeleteKey:
    @pytest.mark.asyncio
    async def test_delete_existing_key(self, ltm: LongTermMemory) -> None:
        await ltm.store("agent", "del_me", {"v": 1})
        result = await ltm.delete("agent", "del_me")
        assert result["status"] == "deleted"
        retrieve = await ltm.retrieve("agent", "del_me")
        assert retrieve["status"] == "not_found"

    @pytest.mark.asyncio
    async def test_delete_nonexistent_key_is_idempotent(self, ltm: LongTermMemory) -> None:
        result = await ltm.delete("agent", "nonexistent")
        assert result["status"] == "deleted"

    @pytest.mark.asyncio
    async def test_delete_key_empty_agent_id_raises(self, ltm: LongTermMemory) -> None:
        with pytest.raises(ValueError, match="agent_id and key are required"):
            await ltm.delete("", "k")

    @pytest.mark.asyncio
    async def test_delete_key_empty_key_raises(self, ltm: LongTermMemory) -> None:
        with pytest.raises(ValueError, match="agent_id and key are required"):
            await ltm.delete("agent", "")


class TestDeleteAgent:
    @pytest.mark.asyncio
    async def test_delete_agent_removes_all_entries(self, ltm: LongTermMemory) -> None:
        await ltm.store("agent_x", "k1", {"v": 1})
        await ltm.store("agent_x", "k2", {"v": 2})
        result = await ltm.delete_agent("agent_x")
        assert result["status"] == "deleted"
        r1 = await ltm.retrieve("agent_x", "k1")
        assert r1["status"] == "not_found"

    @pytest.mark.asyncio
    async def test_delete_nonexistent_agent_is_idempotent(self, ltm: LongTermMemory) -> None:
        result = await ltm.delete_agent("ghost")
        assert result["status"] == "deleted"

    @pytest.mark.asyncio
    async def test_delete_agent_empty_id_raises(self, ltm: LongTermMemory) -> None:
        with pytest.raises(ValueError, match="agent_id is required"):
            await ltm.delete_agent("")

    @pytest.mark.asyncio
    async def test_delete_agent_does_not_affect_others(self, ltm: LongTermMemory) -> None:
        await ltm.store("a", "k", {"v": 1})
        await ltm.store("b", "k", {"v": 2})
        await ltm.delete_agent("a")
        rb = await ltm.retrieve("b", "k")
        assert rb["status"] == "ok"


class TestAgentIsolation:
    @pytest.mark.asyncio
    async def test_different_agents_do_not_interfere(self, ltm: LongTermMemory) -> None:
        await ltm.store("agent_a", "key", {"value": "from_a"})
        await ltm.store("agent_b", "key", {"value": "from_b"})
        ra = await ltm.retrieve("agent_a", "key")
        rb = await ltm.retrieve("agent_b", "key")
        assert ra["result"]["payload"]["value"] == "from_a"
        assert rb["result"]["payload"]["value"] == "from_b"

    @pytest.mark.asyncio
    async def test_same_key_different_payload_per_agent(self, ltm: LongTermMemory) -> None:
        await ltm.store("a1", "shared_key", {"num": 1})
        await ltm.store("a2", "shared_key", {"num": 2})
        r1 = await ltm.retrieve("a1", "shared_key")
        r2 = await ltm.retrieve("a2", "shared_key")
        assert r1["result"]["payload"]["num"] == 1
        assert r2["result"]["payload"]["num"] == 2


class TestTTL:
    @pytest.mark.asyncio
    async def test_store_with_ttl(self, ltm: LongTermMemory) -> None:
        result = await ltm.store("agent", "ttl_key", {"v": 1}, ttl_seconds=3600)
        assert result["ttl_seconds"] == 3600

    @pytest.mark.asyncio
    async def test_store_without_ttl_is_none(self, ltm: LongTermMemory) -> None:
        result = await ltm.store("agent", "no_ttl", {"v": 1})
        assert result["ttl_seconds"] is None

    @pytest.mark.asyncio
    async def test_multiple_ttl_values_per_agent(self, ltm: LongTermMemory) -> None:
        await ltm.store("agent", "k1", {"v": 1}, ttl_seconds=60)
        await ltm.store("agent", "k2", {"v": 2}, ttl_seconds=86400)
        r1 = await ltm.retrieve("agent", "k1")
        r2 = await ltm.retrieve("agent", "k2")
        assert r1["status"] == "ok"
        assert r2["status"] == "ok"


class TestSearch:
    @pytest.mark.asyncio
    async def test_search_by_key(self, ltm: LongTermMemory) -> None:
        await ltm.store("agent", "hello_world", {"v": 1})
        result = await ltm.search("agent", "hello")
        assert result["total"] >= 1

    @pytest.mark.asyncio
    async def test_search_by_payload_content(self, ltm: LongTermMemory) -> None:
        await ltm.store("agent", "mem1", {"text": "important data here"})
        result = await ltm.search("agent", "important")
        assert result["total"] >= 1

    @pytest.mark.asyncio
    async def test_search_empty_query_returns_results(self, ltm: LongTermMemory) -> None:
        await ltm.store("agent", "a", {"v": 1})
        await ltm.store("agent", "b", {"v": 2})
        result = await ltm.search("agent", "")
        assert result["total"] >= 2

    @pytest.mark.asyncio
    async def test_search_no_matches(self, ltm: LongTermMemory) -> None:
        result = await ltm.search("agent", "zzzzz_nonexistent")
        assert result["total"] == 0

    @pytest.mark.asyncio
    async def test_search_respects_limit(self, ltm: LongTermMemory) -> None:
        for i in range(10):
            await ltm.store("agent", f"k{i}", {"i": i})
        result = await ltm.search("agent", "", limit=3)
        assert len(result["results"]) <= 3

    @pytest.mark.asyncio
    async def test_search_empty_agent_id_raises(self, ltm: LongTermMemory) -> None:
        with pytest.raises(ValueError, match="agent_id is required"):
            await ltm.search("", "text")


class TestSearchWithDB:
    @pytest.mark.asyncio
    async def test_search_with_db(self, ltm_with_db: LongTermMemory) -> None:
        mem = ltm_with_db
        await mem.store("agent", "alpha", {"role": "explorer"})
        await mem.store("agent", "beta", {"role": "builder"})
        r = await mem.search("agent", "explorer")
        assert r["total"] >= 1

    @pytest.mark.asyncio
    async def test_search_with_tags(self, ltm_with_db: LongTermMemory) -> None:
        mem = ltm_with_db
        await mem.store("agent", "critical_item", {"v": 1}, tags=["critical", "urgent"])
        await mem.store("agent", "normal_item", {"v": 2}, tags=["normal"])
        r = await mem.search("agent", "", tags=["critical"])
        assert r["total"] >= 1

    @pytest.mark.asyncio
    async def test_search_tags_no_match(self, ltm_with_db: LongTermMemory) -> None:
        mem = ltm_with_db
        await mem.store("agent", "item", {"v": 1}, tags=["normal"])
        r = await mem.search("agent", "", tags=["impossible_tag"])
        assert r["total"] == 0


class TestSemanticSearch:
    @pytest.mark.asyncio
    async def test_semantic_search_not_configured(self, ltm: LongTermMemory) -> None:
        result = await ltm.semantic_search("agent", [0.1, 0.2, 0.3])
        assert result["status"] == "error"
        assert "VectorDB not configured" in result["error"]

    @pytest.mark.asyncio
    async def test_semantic_search_with_vdb(self, ltm: LongTermMemory) -> None:
        from core.vector_db import InMemoryVectorDB
        vdb = InMemoryVectorDB()
        ltm._vector_db = vdb
        await ltm.store("agent", "mem1", {"text": "hello world"})
        vec = [0.1] * 384
        result = await ltm.semantic_search("agent", vec)
        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_semantic_search_with_db_and_vdb(self, tmp_path) -> None:
        from core.db_backend import _SQLiteBackend
        from core.vector_db import InMemoryVectorDB
        db_path = str(tmp_path / "test_sem.db")
        backend = _SQLiteBackend(db_path)
        vdb = InMemoryVectorDB()
        mem = LongTermMemory(
            hierarchy=MemoryHierarchy(),
            db=backend,
            vector_db=vdb,
            trace_correlator=CognitiveTraceCorrelator(),
        )
        await mem.initialize()
        await mem.store("agent", "sem_item", {"data": "test"})
        vec = [0.1] * 384
        result = await mem.semantic_search("agent", vec)
        assert result["status"] == "ok"


class TestStatsAndListing:
    @pytest.mark.asyncio
    async def test_get_stats_after_stores(self, ltm: LongTermMemory) -> None:
        await ltm.store("agent", "k1", {"v": 1})
        await ltm.store("agent", "k2", {"v": 2})
        stats = await ltm.get_stats("agent")
        assert stats["status"] == "ok"

    @pytest.mark.asyncio
    async def test_get_stats_nonexistent_agent(self, ltm: LongTermMemory) -> None:
        stats = await ltm.get_stats("ghost")
        assert stats["status"] == "ok"

    @pytest.mark.asyncio
    async def test_get_stats_with_db(self, ltm_with_db: LongTermMemory) -> None:
        await ltm_with_db.store("agent", "k1", {"v": 1})
        await ltm_with_db.store("agent", "k2", {"v": 2})
        stats = await ltm_with_db.get_stats("agent")
        assert stats["total_entries"] == 2

    @pytest.mark.asyncio
    async def test_get_stats_global(self, ltm_with_db: LongTermMemory) -> None:
        await ltm_with_db.store("a", "k1", {"v": 1})
        await ltm_with_db.store("b", "k2", {"v": 2})
        stats = await ltm_with_db.get_stats()
        assert stats["total_agents"] >= 2

    @pytest.mark.asyncio
    async def test_get_stats_tracks_access_count(self, ltm_with_db: LongTermMemory) -> None:
        await ltm_with_db.store("agent", "hit", {"v": 1})
        await ltm_with_db.retrieve("agent", "hit")
        await ltm_with_db.retrieve("agent", "hit")
        await ltm_with_db.retrieve("agent", "hit")
        stats = await ltm_with_db.get_stats("agent")
        assert stats["total_access_count"] >= 3

    @pytest.mark.asyncio
    async def test_get_stats_empty(self, ltm: LongTermMemory) -> None:
        stats = await ltm.get_stats()
        assert stats["status"] == "ok"


class TestCognitiveTrace:
    @pytest.mark.asyncio
    async def test_store_generates_trace_id(self, ltm: LongTermMemory) -> None:
        result = await ltm.store("agent", "mem", {"v": 1})
        assert "cognitive_trace_id" in result
        assert len(result["cognitive_trace_id"]) > 0

    @pytest.mark.asyncio
    async def test_retrieve_generates_trace_id(self, ltm: LongTermMemory) -> None:
        await ltm.store("agent", "mem", {"v": 1})
        result = await ltm.retrieve("agent", "mem")
        assert "cognitive_trace_id" in result
        assert len(result["cognitive_trace_id"]) > 0

    @pytest.mark.asyncio
    async def test_search_generates_trace_id(self, ltm: LongTermMemory) -> None:
        result = await ltm.search("agent", "test")
        assert "cognitive_trace_id" in result

    @pytest.mark.asyncio
    async def test_delete_generates_trace_id(self, ltm: LongTermMemory) -> None:
        await ltm.store("agent", "mem", {"v": 1})
        result = await ltm.delete("agent", "mem")
        assert "cognitive_trace_id" in result

    @pytest.mark.asyncio
    async def test_trace_id_accepts_custom_value(self, ltm: LongTermMemory) -> None:
        result = await ltm.store("agent", "mem", {"v": 1}, cognitive_trace_id="custom-trace-123")
        assert result["cognitive_trace_id"] == "custom-trace-123"

    @pytest.mark.asyncio
    async def test_trace_id_custom_retrieve(self, ltm: LongTermMemory) -> None:
        await ltm.store("agent", "mem", {"v": 1})
        result = await ltm.retrieve("agent", "mem", cognitive_trace_id="custom-retrieve")
        assert result["cognitive_trace_id"] == "custom-retrieve"


class TestCleanupExpired:
    @pytest.mark.asyncio
    async def test_cleanup_expired_without_db(self, ltm: LongTermMemory) -> None:
        result = await ltm.cleanup_expired()
        assert result["deleted_count"] == 0

    @pytest.mark.asyncio
    async def test_cleanup_expired_with_db(self, ltm_with_db: LongTermMemory) -> None:
        mem = ltm_with_db
        await mem.store("agent", "expires_soon", {"v": 1}, ttl_seconds=1)
        await mem.store("agent", "persists", {"v": 2}, ttl_seconds=999999)
        await asyncio.sleep(2)
        result = await mem.cleanup_expired()
        assert result["deleted_count"] >= 1

    @pytest.mark.asyncio
    async def test_cleanup_expired_none_expired(self, ltm_with_db: LongTermMemory) -> None:
        mem = ltm_with_db
        await mem.store("agent", "k1", {"v": 1}, ttl_seconds=999999)
        result = await mem.cleanup_expired()
        assert result["deleted_count"] == 0


class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_store_large_payload(self, ltm: LongTermMemory) -> None:
        large = {"data": "x" * 100000}
        result = await ltm.store("agent", "large", large)
        assert result["status"] == "stored"

    @pytest.mark.asyncio
    async def test_store_nested_payload(self, ltm: LongTermMemory) -> None:
        nested = {"level1": {"level2": {"level3": "deep"}}}
        result = await ltm.store("agent", "nested", nested)
        assert result["status"] == "stored"
        r = await ltm.retrieve("agent", "nested")
        assert r["result"]["payload"]["level1"]["level2"]["level3"] == "deep"

    @pytest.mark.asyncio
    async def test_store_none_payload(self, ltm: LongTermMemory) -> None:
        result = await ltm.store("agent", "null_val", {"v": None})
        assert result["status"] == "stored"
        r = await ltm.retrieve("agent", "null_val")
        assert r["result"]["payload"]["v"] is None

    @pytest.mark.asyncio
    async def test_store_boolean_payload(self, ltm: LongTermMemory) -> None:
        await ltm.store("agent", "flag", {"enabled": True, "disabled": False})
        r = await ltm.retrieve("agent", "flag")
        assert r["result"]["payload"]["enabled"] is True
        assert r["result"]["payload"]["disabled"] is False

    @pytest.mark.asyncio
    async def test_store_numeric_types(self, ltm: LongTermMemory) -> None:
        await ltm.store("agent", "nums", {"int": 42, "float": 3.14})
        r = await ltm.retrieve("agent", "nums")
        assert r["result"]["payload"]["int"] == 42
        assert r["result"]["payload"]["float"] == 3.14

    @pytest.mark.asyncio
    async def test_store_and_retrieve_empty_dict(self, ltm: LongTermMemory) -> None:
        await ltm.store("agent", "empty", {})
        r = await ltm.retrieve("agent", "empty")
        assert r["status"] == "ok"
        assert r["result"]["payload"] == {}

    @pytest.mark.asyncio
    async def test_special_characters_in_key(self, ltm: LongTermMemory) -> None:
        await ltm.store("agent", "key with spaces & symbols!@#", {"v": 1})
        r = await ltm.retrieve("agent", "key with spaces & symbols!@#")
        assert r["status"] == "ok"


class TestConcurrency:
    @pytest.mark.asyncio
    async def test_concurrent_stores_same_agent(self, ltm: LongTermMemory) -> None:
        async def store_i(i: int) -> None:
            await ltm.store("agent", f"k{i}", {"i": i})

        await asyncio.gather(*[store_i(i) for i in range(20)])
        for i in range(20):
            r = await ltm.retrieve("agent", f"k{i}")
            assert r["status"] == "ok"

    @pytest.mark.asyncio
    async def test_concurrent_stores_different_agents(self, ltm: LongTermMemory) -> None:
        async def store_agent(aid: str) -> None:
            await ltm.store(aid, "key", {"agent": aid})

        agents = [f"agent_{i}" for i in range(20)]
        await asyncio.gather(*[store_agent(a) for a in agents])

    @pytest.mark.asyncio
    async def test_concurrent_reads_and_writes(self, ltm: LongTermMemory) -> None:
        async def writer() -> None:
            for i in range(10):
                await ltm.store("agent", f"w{i}", {"i": i})

        async def reader() -> None:
            for i in range(10):
                await ltm.search("agent", str(i))

        await asyncio.gather(writer(), reader())

    @pytest.mark.asyncio
    async def test_concurrent_db_stores(self, ltm_with_db: LongTermMemory) -> None:
        mem = ltm_with_db
        async def store_i(i: int) -> None:
            await mem.store("agent", f"c{i}", {"i": i})

        await asyncio.gather(*[store_i(i) for i in range(15)])
        for i in range(15):
            r = await mem.retrieve("agent", f"c{i}")
            assert r["status"] == "ok"


class TestModels:
    def test_long_term_memory_entry_defaults(self) -> None:
        entry = LongTermMemoryEntry(entry_id="e1", agent_id="a", key="k", payload={})
        assert entry.entry_id == "e1"
        assert entry.agent_id == "a"
        assert entry.key == "k"
        assert entry.payload == {}
        assert entry.ttl_seconds is None
        assert entry.access_count == 0
        assert entry.tags == []
        assert entry.cognitive_trace_id == ""

    def test_long_term_memory_entry_with_fields(self) -> None:
        entry = LongTermMemoryEntry(
            entry_id="e1",
            agent_id="agent",
            key="my_key",
            payload={"data": 1},
            ttl_seconds=3600,
            access_count=5,
            tags=["important"],
            cognitive_trace_id="trace-123",
        )
        assert entry.ttl_seconds == 3600
        assert entry.access_count == 5
        assert entry.tags == ["important"]
        assert entry.cognitive_trace_id == "trace-123"

    def test_long_term_memory_entry_create_at_field(self) -> None:
        now = "2026-06-24T10:00:00"
        entry = LongTermMemoryEntry(
            entry_id="e1", agent_id="a", key="k", payload={}, created_at=now,
        )
        assert entry.created_at == now


class TestConstructor:
    @pytest.mark.asyncio
    async def test_default_constructor(self) -> None:
        mem = LongTermMemory(hierarchy=MemoryHierarchy())
        assert mem._hierarchy is not None
        assert mem._db is None
        assert mem._vector_db is None

    @pytest.mark.asyncio
    async def test_constructor_with_db(self, tmp_path) -> None:
        from core.db_backend import _SQLiteBackend
        backend = _SQLiteBackend(str(tmp_path / "test_con.db"))
        mem = LongTermMemory(hierarchy=MemoryHierarchy(), db=backend)
        await mem.initialize()
        assert mem._db is backend
        assert mem._initialized is True

    @pytest.mark.asyncio
    async def test_constructor_with_vector_db(self) -> None:
        from core.vector_db import InMemoryVectorDB
        vdb = InMemoryVectorDB()
        mem = LongTermMemory(hierarchy=MemoryHierarchy(), vector_db=vdb)
        assert mem._vector_db is vdb

    @pytest.mark.asyncio
    async def test_default_correlator(self) -> None:
        mem = LongTermMemory(hierarchy=MemoryHierarchy())
        assert mem._trace_correlator is not None

    @pytest.mark.asyncio
    async def test_custom_correlator(self) -> None:
        corr = CognitiveTraceCorrelator()
        mem = LongTermMemory(hierarchy=MemoryHierarchy(), trace_correlator=corr)
        assert mem._trace_correlator is corr

    @pytest.mark.asyncio
    async def test_initialize_idempotent(self, tmp_path) -> None:
        from core.db_backend import _SQLiteBackend
        backend = _SQLiteBackend(str(tmp_path / "test_idem.db"))
        mem = LongTermMemory(hierarchy=MemoryHierarchy(), db=backend)
        await mem.initialize()
        await mem.initialize()

    @pytest.mark.asyncio
    async def test_initial_not_initialized(self) -> None:
        mem = LongTermMemory(hierarchy=MemoryHierarchy())
        assert mem._initialized is False


class TestAccessCount:
    @pytest.mark.asyncio
    async def test_access_count_increments(self, ltm_with_db: LongTermMemory) -> None:
        mem = ltm_with_db
        await mem.store("agent", "popular", {"v": 1})
        stats_before = await mem.get_stats("agent")
        before = stats_before["total_access_count"]

        for _ in range(5):
            await mem.retrieve("agent", "popular")

        stats_after = await mem.get_stats("agent")
        assert stats_after["total_access_count"] >= before + 5


class TestInitialize:
    @pytest.mark.asyncio
    async def test_initialize_creates_table(self, tmp_path) -> None:
        from core.db_backend import _SQLiteBackend
        db_path = str(tmp_path / "test_init.db")
        backend = _SQLiteBackend(db_path)
        mem = LongTermMemory(hierarchy=MemoryHierarchy(), db=backend)
        await mem.initialize()
        conn = await backend.connect()
        try:
            rows = await conn.fetchall(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                ("long_term_memory",),
            )
            assert len(rows) == 1
        finally:
            await conn.close()

    @pytest.mark.asyncio
    async def test_initialize_twice_no_error(self, tmp_path) -> None:
        from core.db_backend import _SQLiteBackend
        backend = _SQLiteBackend(str(tmp_path / "test_init2.db"))
        mem = LongTermMemory(hierarchy=MemoryHierarchy(), db=backend)
        await mem.initialize()
        await mem.initialize()
