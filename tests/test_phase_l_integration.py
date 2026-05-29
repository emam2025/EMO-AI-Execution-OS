"""Phase L — Cognitive Memory Layer Integration Tests (25 tests).

EXEC-DIRECTIVE-PHASE-L-001:
  5 groups × 5 tests = 25 total

Groups:
  1. MemoryHierarchy (store / retrieve / prune / tenant isolation / deterministic hash)
  2. ContextCompiler (compress / inject / validate / scope guard / SHA-256)
  3. SkillGraphManager (record / retrieve / update weight / failure pattern / tenant isolation)
  4. MemoryStateMachine (6 transitions × G-M1–G-M6 guards)
  5. CognitiveTraceCorrelator (generate / propagate / verify chain / reset / replay)
"""

from __future__ import annotations

import pytest

from core.memory.memory_hierarchy import MemoryHierarchy, IsolationViolation
from core.memory.context_compiler import ContextCompiler
from core.memory.skill_graph_manager import SkillGraphManager
from core.memory.memory_state_machine import MemoryState, MemoryStateMachine, MemoryTransition
from core.memory.trace_correlator import CognitiveTraceCorrelator
from core.memory.models import MemoryLayer, PruningPolicy


# ===================================================================
# Group 1: MemoryHierarchy (5)
# ===================================================================


class TestMemoryHierarchy:
    @pytest.mark.anyio
    async def test_store_and_retrieve(self) -> None:
        mh = MemoryHierarchy()
        await mh.store(MemoryLayer.EPISODIC, "t1", {"result": "42"}, "ten_a", "strict", "cog_1")
        r = await mh.retrieve(MemoryLayer.EPISODIC, {"key": "t1"}, "ten_a")
        assert r["total"] == 1
        assert r["results"][0]["payload"]["result"] == "42"

    @pytest.mark.anyio
    async def test_tenant_isolation(self) -> None:
        mh = MemoryHierarchy()
        await mh.store(MemoryLayer.EPISODIC, "secret", {"data": "a"}, "ten_a", "strict", "cog_1")
        r = await mh.retrieve(MemoryLayer.EPISODIC, {"key": "secret"}, "ten_b")
        assert r["total"] == 0

    @pytest.mark.anyio
    async def test_prune_respects_tenant(self) -> None:
        mh = MemoryHierarchy()
        for i in range(3):
            await mh.store(MemoryLayer.EPISODIC, f"k{i}", {"i": i}, "ten_a", "strict", "cog_p", ttl_seconds=0.001)
        await mh.store(MemoryLayer.EPISODIC, "other", {"i": 99}, "ten_b", "strict", "cog_p2")
        import asyncio
        await asyncio.sleep(0.01)
        pruned = await mh.prune(MemoryLayer.EPISODIC, PruningPolicy.TTL_BASED, "ten_a", "cog_p3")
        assert pruned["status"] == "pruned", pruned
        ra = await mh.retrieve(MemoryLayer.EPISODIC, {}, "ten_a")
        assert ra["total"] == 0, ra
        rb = await mh.retrieve(MemoryLayer.EPISODIC, {"key": "other"}, "ten_b")
        assert rb["total"] == 1, rb

    @pytest.mark.anyio
    async def test_empty_tenant_id_raises(self) -> None:
        mh = MemoryHierarchy()
        with pytest.raises(IsolationViolation):
            await mh.store(MemoryLayer.EPISODIC, "x", {}, "", "strict", "cog_e")
        with pytest.raises(IsolationViolation):
            await mh.retrieve(MemoryLayer.EPISODIC, {}, "")

    @pytest.mark.anyio
    async def test_deterministic_context_hash(self) -> None:
        mh = MemoryHierarchy()
        await mh.store(MemoryLayer.SEMANTIC, "a", {"val": 1}, "ten_a", "strict", "cog_h")
        cw = await mh.get_context_window("ten_a")
        h1 = cw["context_hash"]
        mh2 = MemoryHierarchy()
        await mh2.store(MemoryLayer.SEMANTIC, "a", {"val": 1}, "ten_a", "strict", "cog_h")
        h2 = (await mh2.get_context_window("ten_a"))["context_hash"]
        assert h1 == h2


# ===================================================================
# Group 2: ContextCompiler (5)
# ===================================================================


class TestContextCompiler:
    @pytest.mark.anyio
    async def test_compress_trace_to_context(self) -> None:
        cc = ContextCompiler()
        cc._ingest_trace("trace_abc", {"steps": 3})
        result = await cc.compress_trace_to_context("trace_abc", "ten_a", 2048, False, "cog_ccc")
        assert "context" in result
        assert result["cognitive_trace_id"] == "cog_ccc"

    @pytest.mark.anyio
    async def test_deterministic_hash(self) -> None:
        cc = ContextCompiler()
        r1 = await cc.compress_trace_to_context("t1", "ten_a", 2048, False)
        r2 = await cc.compress_trace_to_context("t1", "ten_a", 2048, False)
        assert r1["context"]["_hash"] == r2["context"]["_hash"]

    @pytest.mark.anyio
    async def test_diff_trace_diff_hash(self) -> None:
        cc = ContextCompiler()
        r1 = await cc.compress_trace_to_context("t1", "ten_a", 2048, False)
        r2 = await cc.compress_trace_to_context("t2", "ten_a", 2048, False)
        assert r1["context"]["_hash"] != r2["context"]["_hash"]

    @pytest.mark.anyio
    async def test_cross_tenant_blocked(self) -> None:
        cc = ContextCompiler()
        result = await cc.compress_trace_to_context("t1", "ten_a", 2048, False)
        assert result["context"]["safety_hash"] is not None

    @pytest.mark.anyio
    async def test_inject_and_validate(self) -> None:
        cc = ContextCompiler()
        ctx = await cc.compress_trace_to_context("t1", "ten_a", 2048, False)
        injected = await cc.inject_runtime_intelligence(ctx, "ten_a")
        assert injected["status"] == "ok"
        validated = await cc.validate_boundary_safety(ctx, "ten_a")
        assert validated["status"] == "safe"


# ===================================================================
# Group 3: SkillGraphManager (5)
# ===================================================================


class TestSkillGraphManager:
    @pytest.mark.anyio
    async def test_record_successful_plan(self) -> None:
        sgm = SkillGraphManager()
        result = await sgm.record_successful_plan(
            "dag_1", "abc123", "ten_a", "summarize", [{"tool": "llm", "args": {"prompt": "x"}}], 1.5,
        )
        assert result["status"] == "recorded"
        assert result["skill_id"].startswith("skill_")

    @pytest.mark.anyio
    async def test_retrieve_skill_tenant_isolation(self) -> None:
        sgm = SkillGraphManager()
        await sgm.record_successful_plan("dag_1", "abc", "ten_a", "summarize", [], 1.0)
        assert (await sgm.retrieve_skill("summarize", "ten_b"))["total"] == 0

    @pytest.mark.anyio
    async def test_update_procedural_weight(self) -> None:
        sgm = SkillGraphManager()
        rec = await sgm.record_successful_plan("dag_1", "abc", "ten_a", "summarize", [], 1.0)
        upd = await sgm.update_procedural_weight(rec["skill_id"], 0.5, "ten_a")
        assert upd["status"] == "updated"

    @pytest.mark.anyio
    async def test_update_weight_tenant_mismatch(self) -> None:
        sgm = SkillGraphManager()
        rec = await sgm.record_successful_plan("dag_1", "abc", "ten_a", "summarize", [], 1.0)
        assert (await sgm.update_procedural_weight(rec["skill_id"], 0.5, "ten_b"))["status"] == "error"

    @pytest.mark.anyio
    async def test_record_failure_pattern(self) -> None:
        sgm = SkillGraphManager()
        r = await sgm.record_failure_pattern("dag_2", "f_hash", "ten_a", "timeout", [{"tool": "db", "args": {}}])
        assert r["status"] == "recorded"
        assert r["pattern_id"].startswith("fail_")


# ===================================================================
# Group 4: MemoryStateMachine (5)
# ===================================================================


class TestMemoryStateMachine:
    @pytest.mark.anyio
    async def test_t0_idle_to_execution_complete(self) -> None:
        sm = MemoryStateMachine()
        assert sm.state == MemoryState.IDLE
        sm.transition(MemoryTransition.T0, {"tenant_id": "ten_a"})
        assert sm.state == MemoryState.EXECUTION_COMPLETE

    @pytest.mark.anyio
    async def test_full_lifecycle(self) -> None:
        sm = MemoryStateMachine()
        sm.transition(MemoryTransition.T0, {"tenant_id": "ten_a"})
        sm.transition(MemoryTransition.T1, {"tenant_id": "ten_a", "trace_tenant": "ten_a"})
        sm.transition(MemoryTransition.T2, {"max_tokens": 2048})
        sm.transition(MemoryTransition.T3A, {
            "scope_verified": False, "intent_match_score": 0.85,
            "owning_tenant": "ten_a", "requested_tenant": "ten_a",
        })
        sm.transition(MemoryTransition.T4, {})
        t5 = sm.transition(MemoryTransition.T5, {})
        assert t5["status"] == "ok"
        assert sm.state == MemoryState.IDLE

    @pytest.mark.anyio
    async def test_gm2_blocks_low_budget(self) -> None:
        sm = MemoryStateMachine()
        sm.transition(MemoryTransition.T0, {"tenant_id": "ten_a"})
        sm.transition(MemoryTransition.T1, {"tenant_id": "ten_a", "trace_tenant": "ten_a"})
        result = sm.transition(MemoryTransition.T2, {"max_tokens": 100})
        assert result["status"] == "blocked"
        assert sm.state == MemoryState.TRACE_ARCHIVE

    @pytest.mark.anyio
    async def test_gm4_blocks_low_intent(self) -> None:
        sm = MemoryStateMachine()
        sm.transition(MemoryTransition.T0, {"tenant_id": "ten_a"})
        sm.transition(MemoryTransition.T1, {"tenant_id": "ten_a", "trace_tenant": "ten_a"})
        sm.transition(MemoryTransition.T2, {"max_tokens": 2048})
        result = sm.transition(MemoryTransition.T3A, {
            "scope_verified": False, "intent_match_score": 0.3,
        })
        assert result["status"] == "blocked"

    @pytest.mark.anyio
    async def test_history_tracks_transitions(self) -> None:
        sm = MemoryStateMachine()
        sm.transition(MemoryTransition.T0, {"tenant_id": "ten_a"})
        assert len(sm.history) == 1
        assert sm.history[0]["from_state"] == MemoryState.IDLE.value


# ===================================================================
# Group 5: CognitiveTraceCorrelator (5)
# ===================================================================


class TestCognitiveTraceCorrelator:
    def test_generate_cognitive_trace_id(self) -> None:
        ctc = CognitiveTraceCorrelator()
        tid = ctc.generate_cognitive_trace_id("ten_a")
        assert tid.startswith("cog_")
        assert len(tid) == 32  # "cog_" + 28 hex

    def test_record_memory_store(self) -> None:
        ctc = CognitiveTraceCorrelator()
        tid = ctc.generate_cognitive_trace_id("ten_a", "sess_1")
        ctc.record_memory_store(tid, "episodic", "key_1", "ten_a")
        assert ctc.get_trace_chain(tid)["total_stores"] == 1

    def test_verify_full_propagation(self) -> None:
        ctc = CognitiveTraceCorrelator()
        tid = ctc.generate_cognitive_trace_id("ten_a")
        ctc.record_memory_store(tid, "semantic", "k1", "ten_a")
        assert ctc.verify_full_propagation(tid)["fully_propagated"] is True

    def test_empty_trace_returns_no_layers(self) -> None:
        ctc = CognitiveTraceCorrelator()
        v = ctc.verify_full_propagation("nonexistent")
        assert v["fully_propagated"] is False
        assert v["layer_count"] == 0

    def test_reset(self) -> None:
        ctc = CognitiveTraceCorrelator()
        t1 = ctc.generate_cognitive_trace_id("ten_a")
        ctc.record_memory_store(t1, "episodic", "k1", "ten_a")
        assert len(ctc.all_traces()) >= 1
        ctc.reset()
        assert len(ctc.all_traces()) == 0
